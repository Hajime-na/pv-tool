from __future__ import annotations

import mimetypes
import json
import re
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# 焼きこみ進捗管理
_burn_status: dict = {"running": False, "progress": "", "percent": 0, "total_sec": 0, "output_path": ""}
_burn_lock = threading.Lock()


ROOT = Path(__file__).resolve().parent
PV_ROOT = Path(r"C:\Codex\PV").resolve()
MUSIC_ROOT = Path(r"C:\Users\hana\Documents\音楽配信-20260412").resolve()
HOST = "127.0.0.1"
PORT = 8767

# Keep the music project root usable even if older source text was saved with
# mojibake in the literal above.
MUSIC_ROOT = Path(r"C:\Users\hana\Documents\音楽配信-20260412").resolve()


def validate_project_dir(path_text: str) -> Path:
    requested = Path(path_text).resolve()
    parts = {part.lower() for part in requested.parts}
    if "pv-tool" in parts:
        raise ValueError("PVフォルダには pv-tool ではなく曲フォルダを指定してください")
    if not requested.exists() or not requested.is_dir():
        raise ValueError(f"Project folder does not exist: [{requested}]")
    return requested


def is_generated_video(path: Path) -> bool:
    name = path.name.lower()
    return "lyrics_burn" in name or "lyrics_preview" in name or "_lyrics" in name


class RangeRequestHandler(SimpleHTTPRequestHandler):
    def project_base_from_query(self) -> Path:
        query = urlparse(self.path).query
        params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
        raw = unquote(params.get("projectDir", "")).strip()
        if not raw:
            return ROOT
        return validate_project_dir(raw)

    def do_POST(self):
        if urlparse(self.path).path == "/api/save":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                filename = str(payload.get("filename", "")).strip()
                content = payload.get("content", "")
                project_dir_text = str(payload.get("projectDir", "")).strip()
                allowed = {"pv_project.json", "pv_lyrics_timing.json"}
                if filename not in allowed:
                    raise ValueError("Unsupported filename")
                if not project_dir_text:
                    raise ValueError("PVフォルダを指定してください")
                requested = validate_project_dir(project_dir_text)
                base = requested
                target = (base / filename).resolve()
                if not (str(target).lower().startswith(str(ROOT).lower()) or str(target).lower().startswith(str(PV_ROOT).lower()) or str(target).lower().startswith(str(MUSIC_ROOT).lower())):
                    raise ValueError("Blocked path")
                target.write_text(str(content), encoding="utf-8")
                body = json.dumps({"ok": True, "path": str(target)}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path == "/api/burn":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                project_dir_text = str(payload.get("projectDir", "")).strip()
                mode = str(payload.get("mode", "preview")).strip()
                if not project_dir_text:
                    raise ValueError("PVフォルダを指定してください")
                project_dir = validate_project_dir(project_dir_text)
                script = ROOT / "pv_burn_lyrics.py"
                if not script.exists():
                    raise ValueError("pv_burn_lyrics.py not found")
                cmd = [sys.executable, "-u", "-X", "utf8", str(script), "--project", str(project_dir)]
                if mode == "preview":
                    cmd += ["--preview-seconds", str(payload.get("previewSeconds", 35))]
                    cmd += ["--start-seconds", str(payload.get("previewStartSeconds", 0))]
                output = (payload.get("output") or "").strip()
                if output and re.search(r'\.(mp4|mov|avi)$', output, re.IGNORECASE):
                    cmd += ["--output", str((project_dir / output).resolve())]
                settings = payload.get("burnSettings") or {}
                if isinstance(settings, dict):
                    option_map = {
                        "font_scale": "--font-scale",
                        "font_family": "--font-family",
                        "position": "--position",
                        "margin_x": "--margin-x",
                        "margin_bottom": "--margin-bottom",
                        "box_opacity": "--box-opacity",
                        "box_width": "--box-width",
                        "lines_per_page": "--lines-per-page",
                        "timing_offset_start": "--timing-offset-start",
                        "timing_offset_end": "--timing-offset-end",
                    }
                    for key, option in option_map.items():
                        value = settings.get(key)
                        if value is not None and str(value).strip() != "":
                            cmd += [option, str(value)]
                    if settings.get("show_section"):
                        cmd += ["--show-section"]
                total_sec = float(payload.get("totalSec", 0) or 0)
                with _burn_lock:
                    if _burn_status.get("running"):
                        raise ValueError("焼きこみが既に実行中です")
                    _burn_status.update({"running": True, "progress": "開始中...", "percent": 0, "total_sec": total_sec, "error": "", "done": False, "output_path": ""})
                def run_burn():
                    stdout_lines: list[str] = []
                    stderr_lines: list[str] = []
                    try:
                        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
                        def read_stdout():
                            for line in proc.stdout:
                                line = line.strip()
                                if not line:
                                    continue
                                stdout_lines.append(line)
                                try:
                                    current_sec = float(line.rstrip("s"))
                                    pct = int(min(99, current_sec / total_sec * 100)) if total_sec > 0 else 0
                                    with _burn_lock:
                                        _burn_status.update({"progress": f"{current_sec:.0f}s / {total_sec:.0f}s", "percent": pct})
                                except ValueError:
                                    pass
                        def read_stderr():
                            for line in proc.stderr:
                                stderr_lines.append(line.strip())
                        t1 = threading.Thread(target=read_stdout, daemon=True)
                        t2 = threading.Thread(target=read_stderr, daemon=True)
                        t1.start(); t2.start()
                        proc.wait(timeout=1800)
                        t1.join(); t2.join()
                        if proc.returncode != 0:
                            raise RuntimeError("\n".join(stderr_lines) or "\n".join(stdout_lines) or "burn failed")
                        output_name = ""
                        for line in reversed(stdout_lines):
                            p = Path(line.strip())
                            if p.suffix.lower() in {".mp4", ".mov", ".avi"}:
                                output_name = p.name
                                break
                        with _burn_lock:
                            _burn_status.update({"running": False, "progress": "完了", "percent": 100, "done": True, "error": "", "output_path": output_name})
                    except Exception as exc:
                        with _burn_lock:
                            _burn_status.update({"running": False, "progress": "エラー", "percent": 0, "done": True, "error": str(exc)})
                threading.Thread(target=run_burn, daemon=True).start()
                body = json.dumps({"ok": True, "started": True}, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "Not found")

    def do_GET(self):
        if self.serve_project_file():
            return
        if urlparse(self.path).path == "/api/burn-status":
            with _burn_lock:
                status = dict(_burn_status)
            body = json.dumps(status, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path == "/api/projects":
            projects = []
            def proj_mtime(d: Path) -> int:
                # pv_project.json の更新時刻を優先（最後に saveToFolder したプロジェクト = 最後に作業したプロジェクト）
                pj = d / "pv_project.json"
                if pj.exists():
                    return int(pj.stat().st_mtime * 1000)
                tj = d / "pv_lyrics_timing.json"
                return int((tj if tj.exists() else d).stat().st_mtime * 1000)
            if PV_ROOT.exists():
                for path in sorted(PV_ROOT.iterdir()):
                    if not path.is_dir() or path.name.lower() == "pv-tool":
                        continue
                    projects.append({"name": path.name, "path": str(path.resolve()), "lastModified": proj_mtime(path)})
            if MUSIC_ROOT.exists():
                for song_dir in sorted(MUSIC_ROOT.iterdir()):
                    if not song_dir.is_dir():
                        continue
                    pv_dir = song_dir / "PV"
                    if pv_dir.is_dir():
                        projects.append({"name": song_dir.name, "path": str(pv_dir.resolve()), "lastModified": proj_mtime(pv_dir)})
            body = json.dumps({"projects": projects}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path == "/api/files":
            try:
                base = self.project_base_from_query()
            except Exception:
                base = ROOT
            payload = {
                "base": str(base),
                "videos": [str(p.relative_to(base)).replace("\\", "/") for p in sorted(base.glob("**/*.mp4")) if not is_generated_video(p)],
                "lyrics": [str(p.relative_to(base)).replace("\\", "/") for p in sorted(base.glob("**/*.txt"))],
                "json": [str(p.relative_to(base)).replace("\\", "/") for p in sorted(base.glob("*.json"))],
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def serve_project_file(self):
        parsed = urlparse(self.path)
        if parsed.path != "/project-file":
            return False
        params = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
        rel = unquote(params.get("path", "")).strip().lstrip("/\\")
        base = self.project_base_from_query()
        target = (base / rel).resolve()
        if not str(target).lower().startswith(str(base).lower()):
            self.send_error(403, "Blocked path")
            return True
        if not target.exists() or not target.is_file():
            self.send_error(404, "File not found")
            return True
        self.path = "/" + str(target.relative_to(ROOT)).replace("\\", "/") if str(target).lower().startswith(str(ROOT).lower()) else self.path
        self._project_target = target
        self.send_project_file(target)
        return True

    def send_project_file(self, path: Path):
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix.lower() in {".txt", ".json", ".html", ".css", ".js"} and "charset=" not in content_type:
            content_type = f"{content_type}; charset=utf-8"
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start_text, _, end_text = range_header.replace("bytes=", "", 1).partition("-")
            try:
                start = int(start_text) if start_text else 0
                end = int(end_text) if end_text else size - 1
            except ValueError:
                self.send_error(416, "Invalid range")
                return
            start = max(0, min(start, size - 1))
            end = max(start, min(end, size - 1))
            length = end - start + 1
            with path.open("rb") as file_obj:
                file_obj.seek(start)
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                remaining = length
                while remaining > 0:
                    chunk = file_obj.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            return
        with path.open("rb") as file_obj:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.copyfile(file_obj, self.wfile)

    def translate_path(self, path: str) -> str:
        raw = unquote(urlparse(path).path).lstrip("/")
        if not raw:
            raw = "pv_project_tool.html"
        target = (ROOT / raw).resolve()
        if not str(target).lower().startswith(str(ROOT).lower()):
            return str(ROOT / "__blocked__")
        return str(target)

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = path / "pv_project_tool.html"
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return None

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix.lower() in {".txt", ".json", ".html", ".css", ".js"} and "charset=" not in content_type:
            content_type = f"{content_type}; charset=utf-8"
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            start_text, _, end_text = range_header.replace("bytes=", "", 1).partition("-")
            try:
                start = int(start_text) if start_text else 0
                end = int(end_text) if end_text else size - 1
            except ValueError:
                self.send_error(416, "Invalid range")
                return None
            start = max(0, min(start, size - 1))
            end = max(start, min(end, size - 1))
            length = end - start + 1

            file_obj = path.open("rb")
            file_obj.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.range = (start, end)
            return file_obj

        file_obj = path.open("rb")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.range = None
        return file_obj

    def copyfile(self, source, outputfile):
        byte_range = getattr(self, "range", None)
        if not byte_range:
            return super().copyfile(source, outputfile)
        start, end = byte_range
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(1024 * 256, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RangeRequestHandler)
    print(f"Serving {ROOT}")
    print(f"Open http://{HOST}:{PORT}/pv_project_tool.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
