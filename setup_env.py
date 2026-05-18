from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys


_FFMPEG_CANDIDATES = [
    r"C:\Users\hana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
]


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _FFMPEG_CANDIDATES:
        from pathlib import Path
        if Path(candidate).exists():
            return candidate
    return None


PYTHON_REQUIREMENTS = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "PIL": "pillow",
}


def run(cmd: list[str]) -> int:
    print("+ " + " ".join(cmd))
    return subprocess.call(cmd)


def missing_python_packages() -> list[str]:
    missing: list[str] = []
    for module, package in PYTHON_REQUIREMENTS.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    return missing


def install_python_packages(packages: list[str]) -> None:
    if not packages:
        return
    print("Installing Python packages: " + ", ".join(packages))
    code = run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    if code != 0:
        raise SystemExit("pip upgrade failed")
    code = run([sys.executable, "-m", "pip", "install", *packages])
    if code != 0:
        raise SystemExit("Python package install failed")


def install_ffmpeg_interactive() -> bool:
    if find_ffmpeg():
        return True
    print("ffmpeg was not found.")
    if not shutil.which("winget"):
        print("winget was not found. Install ffmpeg manually and add it to PATH.")
        return False
    answer = input("Install ffmpeg with winget now? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Skipped ffmpeg install. Burning lyrics needs ffmpeg for audio.")
        return False
    code = run([
        "winget",
        "install",
        "--id",
        "Gyan.FFmpeg",
        "-e",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ])
    return code == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or newer is required.")

    missing = missing_python_packages()
    install_python_packages(missing)

    if find_ffmpeg():
        print("ffmpeg OK")
    elif args.interactive:
        install_ffmpeg_interactive()
    else:
        print("ffmpeg missing")

    print("Environment check complete.")


if __name__ == "__main__":
    main()
