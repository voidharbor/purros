#!/usr/bin/env python3
"""purr-host: PurrOS asks the PC for pictures here. POST /draw {prompt, quality} -> PNG, made by Jarvis's
mockup.py with FLUX.2 klein (--managed swaps the text model out and back). Listens on 127.0.0.1:7790 only;
the VM reaches it as 10.0.2.2:7790 through QEMU's user network."""
import json
import os
import random
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
LOCK = threading.Lock()
TIMEOUT = 1500


def mockup_cmd() -> list[str]:
    return shlex.split(os.environ.get("PURR_MOCKUP_CMD") or f"python3 {HOME}/local-ai/bin/mockup.py")


def out_dir() -> Path:
    return Path(os.environ.get("PURR_MOCKUP_DIR") or HOME / "local-ai/samples/mockups")


def friendly(err: str) -> str:
    line = (err.strip().splitlines() or ["the picture maker stopped"])[-1]
    line = line.removeprefix("Image generation stopped: ")
    low = line.lower()
    if "game" in low or "hold" in low:
        return "a game is running, so the GPU is busy. try again after."
    if "another image job" in low:
        return "another picture is being made. try again in a minute."
    return line[:300]


def draw(prompt: str, quality: str) -> bytes:
    name = time.strftime("purros-%Y%m%d-%H%M%S-") + f"{random.randrange(16**4):04x}"
    cmd = mockup_cmd() + ["base", name, "1344", "896", str(random.randrange(1, 2**31)), prompt, "--managed"]
    if quality == "quick":
        cmd += ["--quality", "fast"]
    with LOCK:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    png = out_dir() / (name + ".png")
    if r.returncode != 0 or not png.is_file():
        raise RuntimeError(friendly(r.stderr or r.stdout))
    return png.read_bytes()


class Handler(BaseHTTPRequestHandler):
    def reply(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, b'{"ok": true}', "application/json")
        self.reply(404, b"not here", "text/plain")

    def do_POST(self):
        if self.path != "/draw":
            return self.reply(404, b"not here", "text/plain")
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            prompt = str(data.get("prompt", "")).strip()
        except ValueError:
            prompt = ""
        if not prompt:
            return self.reply(400, b"what should I draw?", "text/plain")
        t0 = time.monotonic()
        try:
            png = draw(prompt[:1500], str(data.get("quality", "careful")))
        except subprocess.TimeoutExpired:
            return self.reply(503, b"the picture took too long, so I stopped it.", "text/plain")
        except Exception as e:  # anything mockup.py says goes back to the screen as words
            return self.reply(503, str(e).encode(), "text/plain")
        self.log_message("drew %r in %.0f s", prompt[:60], time.monotonic() - t0)
        self.reply(200, png, "image/png")

    def log_message(self, fmt, *args):
        sys.stderr.write(time.strftime("%H:%M:%S ") + (fmt % args) + "\n")


def make_server(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    srv = make_server(int(os.environ.get("PURR_HOST_PORT", "7790")))
    print(f"purr-host on 127.0.0.1:{srv.server_address[1]}", flush=True)
    srv.serve_forever()
