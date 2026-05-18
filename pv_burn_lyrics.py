from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path


FPS_FALLBACK = 24.0

_FFMPEG_CANDIDATES = [
    r"C:\Users\hana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]

_FFPROBE_CANDIDATES = [
    r"C:\Users\hana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffprobe.exe",
    r"C:\ffmpeg\bin\ffprobe.exe",
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\yumindb.ttf",
    r"C:\Windows\Fonts\yumin.ttf",
    r"C:\Windows\Fonts\BIZ-UDMinchoM.ttc",
    r"C:\Windows\Fonts\msmincho.ttc",
]


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for c in _FFMPEG_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def find_ffprobe() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    for c in _FFPROBE_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def find_font() -> str | None:
    for c in FONT_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def resolve_video(project_dir: Path, project: dict) -> Path:
    def is_generated(p: Path) -> bool:
        n = p.name.lower()
        return "lyrics_burn" in n or "lyrics_preview" in n

    rel = project.get("assets", {}).get("videoPreview") or ""
    if rel:
        p = (project_dir / rel).resolve()
        if p.exists() and not is_generated(p):
            return p
    for glob in ["sauce/*.mp4", "*.mp4"]:
        matches = [p for p in sorted(project_dir.glob(glob)) if not is_generated(p)]
        if matches:
            return matches[0].resolve()
    raise FileNotFoundError("PV video not found")


def get_video_info(ffprobe: str, source: Path) -> tuple[int, int, float]:
    r = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "v:0", str(source)],
        capture_output=True, text=True
    )
    info = json.loads(r.stdout)
    stream = info["streams"][0]
    w = int(stream["width"])
    h = int(stream["height"])
    fps_raw = stream.get("r_frame_rate", "25/1")
    num, den = fps_raw.split("/")
    fps = float(num) / float(den)
    return w, h, fps


def fmt_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = round((s - int(s)) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def prepared_timings(timings: list[dict], source_duration: float, settings: dict) -> list[dict]:
    start_offset = max(-5.0, min(5.0, float(settings.get("timing_offset_start", 0.0))))
    end_offset = max(-5.0, min(5.0, float(settings.get("timing_offset_end", start_offset))))
    prepared = []
    for item in timings:
        start = item.get("start")
        if start is None:
            continue
        new_item = dict(item)
        progress = 0.0 if source_duration <= 0 else max(0.0, min(1.0, float(start) / source_duration))
        offset = start_offset + (end_offset - start_offset) * progress
        new_item["_offset"] = offset
        prepared.append(new_item)
    return sorted(prepared, key=lambda x: float(x.get("start", 0)))


def generate_ass(timings: list[dict], settings: dict, width: int, height: int,
                 preview_start: float, preview_end: float, font_path: str | None) -> str:
    is_vertical = height > width
    font_scale = float(settings.get("font_scale", 1.0))
    font_size = int(max(22, min(80, int(width * (0.052 if is_vertical else 0.036)) * font_scale)))
    position = str(settings.get("position", "bottom"))
    alignment = {"upper": 8, "middle": 5}.get(position, 2)
    margin_x = int(width * float(settings.get("margin_x", 0.08)))
    margin_v = int(height * float(settings.get("margin_bottom", 0.07)))
    box_opacity = float(settings.get("box_opacity", 0.52))
    box_alpha_hex = format(int((1.0 - box_opacity) * 255), "02X")
    lines_per_page = max(1, min(4, int(settings.get("lines_per_page", 2))))
    show_section = bool(settings.get("show_section", False))

    # フォント名はWindowsレジストリ登録名をそのまま使う（Bold=-1不使用）
    font_name = "Yu Mincho Demibold"
    if font_path:
        try:
            import winreg
            fonts_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                       r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
            font_file = Path(font_path).name
            i = 0
            while True:
                try:
                    reg_name, reg_val, _ = winreg.EnumValue(fonts_key, i)
                    if reg_val.lower() == font_file.lower():
                        # "Yu Mincho Demibold (TrueType)" → "Yu Mincho Demibold"
                        font_name = reg_name.replace(" (TrueType)", "").replace(" (OpenType)", "").strip()
                        break
                    i += 1
                except OSError:
                    break
        except Exception:
            try:
                from PIL import ImageFont as _IF
                _f = _IF.truetype(font_path, 12)
                parts = _f.getname()
                font_name = f"{parts[0]} {parts[1]}".strip() if parts[1] not in ("Regular",) else parts[0]
            except Exception:
                pass

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFCF8,&H000000FF,&H001A121E,&H{box_alpha_hex}120A16,0,0,0,0,100,100,0,0,4,2,0,{alignment},{margin_x},{margin_x},{margin_v},1
Style: Section,{font_name},{max(14,font_size//2)},&HB0E2D8FF,&H000000FF,&H001A121E,&H{box_alpha_hex}120A16,0,0,0,0,100,100,0,0,1,1,0,{alignment},{margin_x},{margin_x},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    dialogues: list[str] = []
    for timing in timings:
        raw_start = timing.get("start")
        raw_end = timing.get("end")
        if raw_start is None:
            continue
        raw_start = float(raw_start)
        raw_end = float(raw_end) if raw_end is not None else raw_start + 5.0
        if raw_end <= raw_start:
            continue  # タイミング逆転データをスキップ
        offset = float(timing.get("_offset", 0.0))

        # クリップ範囲外スキップ
        if raw_end <= preview_start or raw_start >= preview_end:
            continue

        lines = [str(l) for l in timing.get("lines", []) if str(l).strip()]
        if not lines:
            continue

        pages = [lines[i:i + lines_per_page] for i in range(0, len(lines), lines_per_page)]
        seg_duration = max(0.1, raw_end - raw_start)
        page_dur = seg_duration / len(pages)

        for pi, page in enumerate(pages):
            p_start = raw_start + page_dur * pi + offset
            p_end = raw_start + page_dur * (pi + 1) + offset
            p_start = max(preview_start, p_start)
            p_end = min(preview_end, p_end)
            if p_end <= p_start:
                continue

            # プレビューオフセット調整
            disp_start = p_start - preview_start
            disp_end = p_end - preview_start

            text = r"\N".join(page)
            if show_section and pi == 0:
                section = str(timing.get("section", ""))
                if section:
                    dialogues.append(
                        f"Dialogue: 0,{fmt_ass_time(disp_start)},{fmt_ass_time(disp_end)},Section,,0,0,0,,{section}"
                    )
            dialogues.append(
                f"Dialogue: 0,{fmt_ass_time(disp_start)},{fmt_ass_time(disp_end)},Default,,0,0,0,,{text}"
            )

    return header + "\n" + "\n".join(dialogues) + "\n"


def burn(project_dir: Path, output: Path | None, preview_seconds: float | None,
         settings: dict | None = None, start_seconds: float = 0.0) -> Path:
    project_path = project_dir / "pv_project.json"
    timing_path = project_dir / "pv_lyrics_timing.json"
    if not timing_path.exists():
        raise FileNotFoundError(timing_path)
    project = json.loads(project_path.read_text(encoding="utf-8-sig")) if project_path.exists() else {}
    timing = json.loads(timing_path.read_text(encoding="utf-8-sig"))
    timings = timing.get("timings", [])
    settings = settings or project.get("burnSettings", {}) or {}
    source = resolve_video(project_dir, project)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    ffprobe = find_ffprobe() or ffmpeg.replace("ffmpeg", "ffprobe")
    font_path = find_font()

    w, h, fps = get_video_info(ffprobe, source)
    source_duration = 0.0
    r = subprocess.run(
        [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(source)],
        capture_output=True, text=True
    )
    try:
        source_duration = float(r.stdout.strip())
    except ValueError:
        pass

    timings = prepared_timings(timings, source_duration, settings)
    start_seconds = max(0.0, float(start_seconds or 0.0))
    preview_end = (start_seconds + preview_seconds) if preview_seconds else source_duration

    if output is None:
        # タイトル: project.jsonのtitle > 曲フォルダ名（PVサブフォルダ構造を考慮）
        _title = (project.get("title") or "").strip()
        if not _title:
            _title = project_dir.parent.name if project_dir.name.lower() == "pv" else project_dir.name
        if preview_seconds:
            # プレビューは上書きOK（確認用の一時ファイル）
            output = project_dir / f"{_title}_lyrics_preview.mp4"
        else:
            # 本番は上書き禁止：既存なら連番を付ける
            base = project_dir / f"{_title}_lyrics_burned.mp4"
            output = base
            n = 2
            while output.exists():
                output = project_dir / f"{_title}_lyrics_burned_{n}.mp4"
                n += 1
    output = output.resolve()
    if output == source:
        raise ValueError("Output path is the same as source")

    ass_content = generate_ass(timings, settings, w, h, start_seconds, preview_end, font_path)

    with tempfile.TemporaryDirectory(prefix="pv_burn_") as tmp:
        ass_file = Path(tmp) / "subtitles.ass"
        ass_file.write_text(ass_content, encoding="utf-8")

        # 相対パスを使うことでWindowsドライブレターのエスケープ問題を回避
        # FFmpegのcwdをtmpに設定 → "subtitles.ass"だけで参照できる
        ass_filter = "ass=subtitles.ass"

        # プレビューのみ -y（上書きOK）。本番は連番で回避済みなので -y 不要
        cmd = [ffmpeg, "-hide_banner", "-y" if preview_seconds else "-n"]
        if start_seconds > 0:
            cmd += ["-ss", str(start_seconds)]
        cmd += ["-i", str(source)]
        if preview_seconds:
            cmd += ["-t", str(preview_seconds)]
        cmd += [
            "-vf", ass_filter,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            str(output)
        ]

        total_frames = int((preview_end - start_seconds) * fps) if preview_seconds else int(source_duration * fps)
        stderr_lines: list[str] = []
        proc = subprocess.Popen(
            cmd, cwd=tmp, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
        )
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())
            if "frame=" in line:
                try:
                    frame_str = line.split("frame=")[1].strip().split()[0]
                    frame = int(frame_str)
                    t = frame / fps
                    print(f"{t:.1f}s", flush=True)
                except (ValueError, IndexError):
                    pass
        proc.wait()
        if proc.returncode != 0:
            tail = "\n".join(stderr_lines[-30:])
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode})\n{tail}")

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Burn PV lyrics using pv_lyrics_timing.json")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    parser.add_argument("--preview-seconds", type=float)
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--font-scale", type=float, default=1.0)
    parser.add_argument("--position", choices=["bottom", "middle", "upper"], default="bottom")
    parser.add_argument("--margin-x", type=float, default=0.08)
    parser.add_argument("--margin-bottom", type=float, default=0.07)
    parser.add_argument("--box-opacity", type=float, default=0.52)
    parser.add_argument("--box-width", type=float)
    parser.add_argument("--lines-per-page", type=int, default=2)
    parser.add_argument("--timing-offset-start", type=float, default=0.0)
    parser.add_argument("--timing-offset-end", type=float, default=0.0)
    parser.add_argument("--show-section", action="store_true")
    args = parser.parse_args()

    project_dir = Path(args.project).resolve()
    output = Path(args.output).resolve() if args.output else None
    settings = {
        "font_scale": args.font_scale,
        "position": args.position,
        "margin_x": args.margin_x,
        "margin_bottom": args.margin_bottom,
        "box_opacity": args.box_opacity,
        "lines_per_page": args.lines_per_page,
        "timing_offset_start": args.timing_offset_start,
        "timing_offset_end": args.timing_offset_end,
        "show_section": args.show_section,
    }
    if args.box_width is not None:
        settings["box_width"] = args.box_width
    result = burn(project_dir, output, args.preview_seconds, settings, args.start_seconds)
    print(result)


if __name__ == "__main__":
    main()
