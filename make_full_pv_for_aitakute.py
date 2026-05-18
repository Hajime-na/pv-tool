from __future__ import annotations

import json
import math
import shutil
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


TITLE = "会いたくて、今すぐにでも"
SRC_AUDIO = Path(r"C:\Users\hana\Downloads\会いたくて、今すぐにでも.wav")
PROJECT_DIR = Path(r"C:\Codex\PV\会いたくて、今すぐにでも")
SAUCE_DIR = PROJECT_DIR / "sauce"
WORK_DIR = PROJECT_DIR / "work"
OUT = PROJECT_DIR / "会いたくて、今すぐにでも_full_pv.mp4"
SILENT = WORK_DIR / "silent_visual.mp4"
COPIED_AUDIO = SAUCE_DIR / SRC_AUDIO.name
FFMPEG = Path(
    r"C:\Users\hana\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
)

W, H = 720, 1280
FPS = 24


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        r"C:\Windows\Fonts\BIZ-UDGothicB.ttc",
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\meiryob.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
    ]:
        p = Path(path)
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def read_audio() -> tuple[np.ndarray, int, float]:
    with wave.open(str(SRC_AUDIO), "rb") as wav:
        channels = wav.getnchannels()
        sr = wav.getframerate()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    audio = audio.reshape(-1, channels).mean(axis=1)
    duration = len(audio) / sr
    return audio, sr, duration


def audio_features(audio: np.ndarray, sr: int, frame_count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rms = np.zeros(frame_count, dtype=np.float32)
    bass = np.zeros(frame_count, dtype=np.float32)
    high = np.zeros(frame_count, dtype=np.float32)
    win = 4096
    freqs = np.fft.rfftfreq(win, 1 / sr)
    bass_mask = (freqs >= 40) & (freqs <= 220)
    high_mask = (freqs >= 1800) & (freqs <= 6500)
    for i in range(frame_count):
        center = int(i / FPS * sr)
        start = max(0, center - win // 2)
        seg = audio[start:start + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        windowed = seg * np.hanning(win)
        spectrum = np.abs(np.fft.rfft(windowed))
        rms[i] = math.sqrt(float(np.mean(seg * seg)))
        bass[i] = float(np.mean(spectrum[bass_mask]))
        high[i] = float(np.mean(spectrum[high_mask]))
    def norm(x: np.ndarray) -> np.ndarray:
        q = float(np.quantile(x, 0.96)) or 1.0
        y = np.clip(x / q, 0, 1)
        for j in range(1, len(y)):
            y[j] = 0.72 * y[j - 1] + 0.28 * y[j]
        return y
    return norm(rms), norm(bass), norm(high)


def draw_text_center(draw: ImageDraw.ImageDraw, text: str, y: int, fnt: ImageFont.FreeTypeFont, fill: tuple[int, int, int, int]) -> None:
    bbox = draw.textbbox((0, 0), text, font=fnt, stroke_width=2)
    x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=fnt, fill=(20, 16, 24, fill[3]), stroke_width=4, stroke_fill=(20, 16, 24, fill[3]))
    draw.text((x, y), text, font=fnt, fill=fill, stroke_width=1, stroke_fill=(255, 235, 240, int(fill[3] * 0.45)))


def render() -> None:
    if not SRC_AUDIO.exists():
        raise FileNotFoundError(SRC_AUDIO)
    if not FFMPEG.exists():
        raise FileNotFoundError(FFMPEG)
    SAUCE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_AUDIO, COPIED_AUDIO)

    audio, sr, duration = read_audio()
    frame_count = int(math.ceil(duration * FPS))
    rms, bass, high = audio_features(audio, sr, frame_count)

    writer = cv2.VideoWriter(str(SILENT), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not writer.isOpened():
        raise RuntimeError("Could not open video writer")

    title_font = font(42)
    small_font = font(24)
    credit_font = font(20)
    rng = np.random.default_rng(7)
    particles = rng.random((95, 4), dtype=np.float32)
    particles[:, 0] *= W
    particles[:, 1] *= H
    particles[:, 2] = 0.3 + particles[:, 2] * 1.7
    particles[:, 3] = 0.3 + particles[:, 3] * 1.5

    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]

    for i in range(frame_count):
        t = i / FPS
        p = i / max(1, frame_count - 1)
        e = float(rms[i])
        b = float(bass[i])
        hi = float(high[i])

        hue_a = 0.55 + 0.18 * math.sin(t * 0.045)
        hue_b = 0.84 + 0.10 * math.sin(t * 0.032 + 2.0)
        grad = np.clip(0.52 * yy + 0.48 * xx + 0.08 * math.sin(t * 0.25), 0, 1)
        r = 22 + 70 * grad + 80 * b * (1 - yy)
        g = 18 + 42 * (1 - grad) + 35 * hi * xx
        bl = 42 + 105 * (1 - grad) + 35 * e
        frame = np.dstack([bl, g, r]).astype(np.uint8)

        cx = int(W * (0.50 + 0.08 * math.sin(t * 0.11)))
        cy = int(H * (0.48 + 0.05 * math.cos(t * 0.09)))
        for k in range(7):
            radius = int(80 + k * 74 + 120 * b + 28 * math.sin(t * 0.8 + k))
            alpha = max(0.0, 0.24 - k * 0.022)
            color = (int(220 + 25 * hi), int(120 + 80 * b), int(185 + 55 * e))
            overlay = frame.copy()
            cv2.circle(overlay, (cx, cy), radius, color, 2 + int(3 * e), lineType=cv2.LINE_AA)
            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        for n, part in enumerate(particles):
            x = (part[0] + t * 18 * part[2] + 22 * math.sin(t * 0.3 + n)) % W
            y = (part[1] - t * 38 * part[3] + H) % H
            rad = int(2 + 6 * e + 3 * part[2])
            color = (255, int(170 + 60 * hi), int(210 + 35 * b))
            cv2.circle(frame, (int(x), int(y)), rad, color, -1, lineType=cv2.LINE_AA)

        bars = 44
        bar_w = W // bars
        for k in range(bars):
            idx = max(0, min(frame_count - 1, i - bars + k))
            amp = float(rms[idx])
            h = int(35 + amp * 180 + 18 * math.sin(t * 2 + k))
            x0 = k * bar_w
            cv2.rectangle(frame, (x0, H - h - 42), (x0 + bar_w - 2, H - 42), (235, 205, 255), -1)

        shade = np.zeros_like(frame)
        cv2.rectangle(shade, (0, 0), (W, H), (0, 0, 0), -1)
        frame = cv2.addWeighted(shade, 0.08, frame, 0.92, 0)

        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
        draw = ImageDraw.Draw(pil, "RGBA")
        if t < 9:
            alpha = int(255 * min(1, t / 1.8) * min(1, (9 - t) / 2.5))
            draw_text_center(draw, TITLE, 160, title_font, (255, 245, 250, alpha))
            draw_text_center(draw, "full PV", 224, small_font, (240, 220, 255, int(alpha * 0.9)))
        if p > 0.88:
            alpha = int(230 * min(1, (p - 0.88) / 0.05))
            draw_text_center(draw, TITLE, 1010, small_font, (255, 245, 250, alpha))
        draw.text((28, H - 34), f"{TITLE}  {int(t // 60):02d}:{int(t % 60):02d}", font=credit_font, fill=(255, 245, 250, 140))
        frame = cv2.cvtColor(np.asarray(pil.convert("RGB")), cv2.COLOR_RGB2BGR)

        writer.write(frame)
        if i % (FPS * 10) == 0:
            print(f"{t:.0f}s / {duration:.0f}s")
    writer.release()

    cmd = [
        str(FFMPEG),
        "-hide_banner",
        "-y",
        "-i",
        str(SILENT),
        "-i",
        str(COPIED_AUDIO),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "20",
        "-preset",
        "medium",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(OUT),
    ]
    subprocess.run(cmd, check=True)

    project = {
        "version": 1,
        "title": TITLE,
        "duration": round(duration, 2),
        "format": "9:16 縦長",
        "status": "フルPV作成済み",
        "assets": {
            "audio": f"sauce/{COPIED_AUDIO.name}",
            "videoPreview": OUT.name,
            "projectDir": str(PROJECT_DIR),
            "lyrics": "",
            "background": "",
            "jacket": "",
            "output": OUT.name,
        },
        "concept": "フリーソフトのみで作成した音反応型フルPV。",
        "lyricsText": "",
        "scenes": [],
    }
    (PROJECT_DIR / "pv_project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    render()
