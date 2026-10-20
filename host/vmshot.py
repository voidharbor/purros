#!/usr/bin/env python3
"""Drive the PurrOS VM over QMP: screenshots, keystrokes, power.

  vmshot.py shot out.png          save the screen as PNG
  vmshot.py type "show all files" type text (add a trailing \\n for Enter)
  vmshot.py key ret               press keys: ret, esc, tab, up, ctrl-l, shift-tab ...
  vmshot.py powerdown             clean shutdown (guest agent, then ACPI power button)
  vmshot.py quit                  stop QEMU immediately
  vmshot.py status                print the VM run state

Sockets: $PURROS_QMP or ~/.cache/purros/qmp.sock, and the guest agent at
$PURROS_QGA or ~/.cache/purros/qga.sock ($PURROS_STATE moves both). Stdlib only.
"""
import json
import os
import socket
import struct
import sys
import tempfile
import time
import zlib

STATE = os.environ.get("PURROS_STATE") or os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "purros")
SOCK = os.environ.get("PURROS_QMP") or os.path.join(STATE, "qmp.sock")
QGA = os.environ.get("PURROS_QGA") or os.path.join(STATE, "qga.sock")


class QMP:
    def __init__(self, path=SOCK, timeout=10.0):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        try:
            self.sock.connect(path)
        except OSError as e:
            sys.exit(f"vmshot: cannot reach QMP at {path} ({e.strerror}). Is PurrOS running?")
        self.buf = b""
        self._read()  # greeting
        self.cmd("qmp_capabilities")

    def _read(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QMP closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def cmd(self, name, **args):
        msg = {"execute": name}
        if args:
            msg["arguments"] = args
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        while True:
            reply = self._read()
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                raise RuntimeError(f"{name}: {reply['error'].get('desc', reply['error'])}")
            # anything else is an async event; skip it


def guest_shutdown(path=QGA, timeout=3.0):
    """Ask the guest agent to power off. True if the agent answered."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(path)
        token = int(time.time()) % 100000
        s.sendall(json.dumps({"execute": "guest-sync", "arguments": {"id": token}}).encode() + b"\n")
        buf = b""
        while str(token).encode() not in buf:
            chunk = s.recv(4096)
            if not chunk:
                return False
            buf += chunk
        s.sendall(b'{"execute": "guest-shutdown", "arguments": {"mode": "powerdown"}}\n')
        time.sleep(0.2)
        s.close()
        return True
    except OSError:
        return False


def ppm_to_png(ppm_path, png_path):
    data = open(ppm_path, "rb").read()
    fields, pos = [], 0
    while len(fields) < 4:  # magic, width, height, maxval; '#' comments allowed
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[pos:end])
        pos = end
    pos += 1
    if fields[0] != b"P6" or fields[3] != b"255":
        raise ValueError("unsupported PPM")
    w, h = int(fields[1]), int(fields[2])
    pixels = data[pos:pos + w * h * 3]
    stride = w * 3
    raw = b"".join(b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(h))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(png_path, "wb") as f:
        f.write(png)


def shot(q, out):
    out = os.path.abspath(out)
    try:
        q.cmd("screendump", filename=out, format="png")
        return out
    except RuntimeError:
        pass  # QEMU older than 7.1: no PNG support, go through PPM
    fd, tmp = tempfile.mkstemp(suffix=".ppm", dir=os.path.dirname(out))
    os.close(fd)
    try:
        q.cmd("screendump", filename=tmp)
        ppm_to_png(tmp, out)
    finally:
        os.unlink(tmp)
    return out


# character -> (qcode, needs shift)
KEYS = {" ": ("spc", False), "\n": ("ret", False), "\t": ("tab", False)}
for c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[c] = (c, False)
    KEYS[c.upper()] = (c, True)
for c in "0123456789":
    KEYS[c] = (c, False)
for c, (code, shift) in {
    ".": ("dot", False), ",": ("comma", False), "-": ("minus", False), "/": ("slash", False),
    "_": ("minus", True), "'": ("apostrophe", False), '"': ("apostrophe", True),
    ":": ("semicolon", True), ";": ("semicolon", False), "?": ("slash", True),
    "!": ("1", True), "@": ("2", True), "#": ("3", True), "$": ("4", True), "%": ("5", True),
    "^": ("6", True), "&": ("7", True), "*": ("8", True), "(": ("9", True), ")": ("0", True),
    "=": ("equal", False), "+": ("equal", True), "[": ("bracket_left", False),
    "]": ("bracket_right", False), "{": ("bracket_left", True), "}": ("bracket_right", True),
    "\\": ("backslash", False), "|": ("backslash", True), "`": ("grave_accent", False),
    "~": ("grave_accent", True), "<": ("comma", True), ">": ("dot", True),
}.items():
    KEYS[c] = (code, shift)

ALIASES = {"enter": "ret", "return": "ret", "space": "spc", "escape": "esc", "bs": "backspace",
           "del": "delete", "control": "ctrl", "win": "meta_l", "super": "meta_l"}


def send(q, codes, hold=40):
    q.cmd("send-key", keys=[{"type": "qcode", "data": c} for c in codes], **{"hold-time": hold})
    time.sleep(hold / 1000 + 0.015)


def type_text(q, text):
    for ch in text:
        if ch not in KEYS:
            raise SystemExit(f"vmshot: no key for {ch!r}")
        code, shift = KEYS[ch]
        send(q, ["shift", code] if shift else [code])


def press(q, combos):
    for combo in combos:
        parts = [combo] if len(combo) == 1 else [p for p in combo.replace("+", "-").split("-") if p]
        codes = []
        for p in parts:
            if len(p) == 1 and p in KEYS:
                code, shift = KEYS[p]
                codes += ["shift", code] if shift else [code]
            else:
                codes.append(ALIASES.get(p.lower(), p.lower()))
        send(q, codes, hold=60)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    action, rest = argv[1], argv[2:]
    q = QMP()
    if action == "shot":
        print(shot(q, rest[0] if rest else "purros.png"))
    elif action == "type":
        type_text(q, " ".join(rest).replace("\\n", "\n"))
    elif action == "key":
        press(q, rest or ["ret"])
    elif action == "powerdown":
        if not guest_shutdown():
            q.cmd("system_powerdown")
    elif action == "quit":
        try:
            q.cmd("quit")
        except ConnectionError:
            pass
    elif action == "status":
        print(q.cmd("query-status").get("status"))
    else:
        print(f"vmshot: unknown action {action}\n\n{__doc__.strip()}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
