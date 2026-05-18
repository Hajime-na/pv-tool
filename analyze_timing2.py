"""
音声エネルギーピークを使い pv_lyrics_timing.json に per-line タイミングを付与する。
セクション境界は既存値を優先し、セクション内のピーク位置で各行の表示開始秒を決める。
"""
import subprocess, json, math
import numpy as np
from pathlib import Path

FFMPEG  = r"C:\Users\hana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")
WAV     = r"C:\Users\hana\Documents\音楽配信-20260412\夏になるのが早すぎて\PV\夏になるのが早すぎて_BA32.wav"
JSON_IN = r"C:\Users\hana\Documents\音楽配信-20260412\夏になるのが早すぎて\PV\pv_lyrics_timing.json"
LINES_PER_PAGE = 1

# ---- 尺取得 ----
r = subprocess.run([FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
                    "-of", "csv=p=0", WAV], capture_output=True, text=True)
dur = float(r.stdout.strip())
print(f"尺: {dur:.2f}s")

# ---- 音声デコード ----
RATE = 22050  # 解析に十分なサンプルレート
print("音声デコード中...")
proc = subprocess.run(
    [FFMPEG, "-y", "-i", WAV, "-ac", "1", "-ar", str(RATE), "-f", "f32le", "pipe:1"],
    capture_output=True
)
samples = np.frombuffer(proc.stdout, dtype=np.float32)
print(f"サンプル数: {len(samples)}")

# ---- 0.25 秒ごとの RMS (dB) ----
CHUNK = RATE // 4  # 0.25s
n_chunks = len(samples) // CHUNK
rms_db = np.zeros(n_chunks)
for i in range(n_chunks):
    seg = samples[i*CHUNK:(i+1)*CHUNK]
    rms_db[i] = 20 * math.log10(float(np.sqrt(np.mean(seg**2))) + 1e-9)

# ---- 平滑化 (w=2 = 0.5s) ----
def smooth(v, w=2):
    k = np.ones(2*w+1) / (2*w+1)
    return np.convolve(v, k, mode='same')

sm = smooth(rms_db, w=2)

# ---- 差分: 前後 0.5s (±2チャンク) の増加量 ----
DT = 0.25
DIFF_WIN = 2
diffs = np.zeros(n_chunks)
for i in range(DIFF_WIN, n_chunks - DIFF_WIN):
    diffs[i] = sm[i+DIFF_WIN] - sm[i-DIFF_WIN]

# ---- ローカル最大ピークを抽出 ----
#   - MIN_GAP = 1.0s (4チャンク) に短縮して密度アップ
MIN_GAP_CH = 4
peaks = []
for i in range(MIN_GAP_CH, n_chunks - MIN_GAP_CH):
    if diffs[i] <= 0:
        continue
    win = diffs[max(0,i-MIN_GAP_CH):i+MIN_GAP_CH+1]
    if diffs[i] == win.max() and diffs[i] > 0.2:
        peaks.append((i * DT, float(diffs[i])))

print(f"ピーク数: {len(peaks)}")

# ---- timing JSON 読み込み ----
data = json.loads(Path(JSON_IN).read_text(encoding="utf-8"))
timings = data["timings"]

# ---- セクション内ピークで per-line timing を生成 ----
new_timings = []
for item in timings:
    s_start = float(item.get("start") or 0)
    s_end   = float(item.get("end")   or dur)
    lines   = [str(l) for l in item.get("lines", []) if str(l).strip()]
    n_lines = len(lines)

    if n_lines == 0:
        new_timings.append(dict(item))
        continue

    # セクション内のピークを時系列順に抽出
    sect_peaks = [t for t, sc in peaks if s_start <= t < s_end]

    # LINES_PER_PAGE=1 なので n_pages = n_lines
    n_pages = math.ceil(n_lines / LINES_PER_PAGE)

    # ページ開始時刻を決定
    # ─────────────────────────────────────────────
    # LINES_PER_PAGE=1: セクション内のピークを先頭から n_pages 個割り当てる。
    # ピークが足りない場合は最後のピークから均等補完する。
    # ─────────────────────────────────────────────
    if len(sect_peaks) >= n_pages:
        # ピークが十分 → 先頭 n_pages 個を使う
        page_starts = list(sect_peaks[:n_pages])
    elif len(sect_peaks) > 0:
        # ピーク不足 → 使えるピーク + 後半均等補完
        page_starts = list(sect_peaks)
        last_t = page_starts[-1]
        remaining = n_pages - len(page_starts)
        step = (s_end - last_t) / (remaining + 1)
        for k in range(1, remaining + 1):
            page_starts.append(last_t + step * k)
    else:
        # ピークなし → セクション均等割り
        seg_dur  = s_end - s_start
        avg_page = seg_dur / n_pages
        page_starts = [s_start + avg_page * i for i in range(n_pages)]

    # 単調増加を保証
    for pi in range(1, n_pages):
        if page_starts[pi] <= page_starts[pi-1] + 0.3:
            page_starts[pi] = page_starts[pi-1] + 0.5

    MAX_LINE_DUR = 5.0  # 1行の最大表示秒数
    # line_timings に変換
    line_timings = []
    for pi in range(n_pages):
        p_start = page_starts[pi]
        p_end_raw = page_starts[pi+1] if pi+1 < n_pages else s_end
        p_end   = min(p_end_raw, p_start + MAX_LINE_DUR)
        idx0 = pi * LINES_PER_PAGE
        idx1 = min(idx0 + LINES_PER_PAGE, n_lines)
        for li in range(idx0, idx1):
            line_timings.append({"start": round(p_start, 2), "end": round(p_end, 2), "text": lines[li]})

    new_item = dict(item)
    new_item["line_timings"] = line_timings
    new_timings.append(new_item)

    # 表示
    print(f"\n{item['section']} [{s_start:.1f}-{s_end:.1f}]  peaks={sect_peaks}")
    for lt in line_timings:
        print(f"  {lt['start']:6.2f}-{lt['end']:6.2f}  {lt['text']}")

# 全ピークをトップレベルに保存（ツールの「次ピーク」ボタン用）
all_peaks_sorted = sorted([t for t, _ in peaks])
data["phrase_peaks"] = [round(t, 2) for t in all_peaks_sorted]
data["timings"] = new_timings
Path(JSON_IN).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n保存: {JSON_IN}  phrase_peaks={len(all_peaks_sorted)}個")
