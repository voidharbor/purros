"""Running real commands: streamed output with limits, and terminal panes for interactive programs."""
import asyncio
import codecs
import fcntl
import os
import pty
import shlex
import signal
import struct
import subprocess
import termios
from pathlib import Path
from typing import Awaitable, Callable

ALWAYS_INTERACTIVE = {
    "nano", "vim", "vi", "nvim", "emacs", "micro", "htop", "btop", "top", "less", "more", "man", "ssh", "telnet",
    "ftp", "mc", "watch", "tmux", "screen", "nnn", "ranger", "iftop", "alsamixer", "passwd",
}
REPLS = {"python", "python3", "bash", "sh", "zsh", "ash", "node", "lua", "irb", "sqlite3", "bc"}


def is_interactive(cmd: str) -> bool:
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    if not words:
        return False
    prog = words[0].rsplit("/", 1)[-1]
    if prog in ALWAYS_INTERACTIVE:
        return True
    return prog in REPLS and len(words) == 1


def _killpg(proc) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def _drain(proc) -> None:
    """Read the pipe to its end: asyncio only finishes wait() once the pipe closes, and a full buffer pauses it."""
    while await proc.stdout.read(65536):
        pass


async def run(cmd: str, cwd: Path, on_out: Callable[[str], Awaitable], timeout: float = 60,
              max_bytes: int = 200_000) -> int:
    proc = await asyncio.create_subprocess_exec(
        "bash", "-c", cmd, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True)
    dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    sent = 0

    async def pump() -> str | None:
        nonlocal sent
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                return None
            room = max_bytes - sent
            if len(chunk) > room:
                if room > 0:
                    await on_out(dec.decode(chunk[:room]))
                return "(output cut)"
            sent += len(chunk)
            text = dec.decode(chunk)
            if text:
                await on_out(text)

    try:
        why = await asyncio.wait_for(pump(), timeout)
    except asyncio.TimeoutError:
        why = f"(stopped after {timeout:g} s)"
    except asyncio.CancelledError:
        _killpg(proc)
        await _drain(proc)
        await proc.wait()
        raise
    if why:
        _killpg(proc)
        await _drain(proc)
        await on_out(("\n" if sent else "") + why + "\n")
        await proc.wait()
        return proc.returncode if proc.returncode not in (None, 0) else 1
    return await proc.wait()


class Pty:
    """One interactive program in a pseudo terminal. on_data gets text, on_exit gets the exit code once."""

    def __init__(self, argv: list[str], cwd: Path, cols: int, rows: int,
                 on_data: Callable[[str], object], on_exit: Callable[[int], object]):
        self.argv, self.cwd, self.cols, self.rows = argv, cwd, cols, rows
        self.on_data, self.on_exit = on_data, on_exit
        self.proc = None
        self.fd = None
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._done = False

    def start(self) -> None:
        master, slave = pty.openpty()
        self._winsize(slave)
        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")

        def child_setup():
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.proc = subprocess.Popen(self.argv, cwd=str(self.cwd), stdin=slave, stdout=slave, stderr=slave,
                                     env=env, start_new_session=True, preexec_fn=child_setup, close_fds=True)
        os.close(slave)
        self.fd = master
        os.set_blocking(master, False)
        asyncio.get_running_loop().add_reader(master, self._readable)

    def _winsize(self, fd: int) -> None:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.cols, 0, 0))

    def _readable(self) -> None:
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if data:
            text = self._dec.decode(data)
            if text:
                self.on_data(text)
            return
        self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        loop = asyncio.get_running_loop()
        loop.remove_reader(self.fd)
        os.close(self.fd)

        async def reap():
            code = await loop.run_in_executor(None, self.proc.wait)
            self.on_exit(code)
        loop.create_task(reap())

    def write(self, data: str) -> None:
        if not self._done:
            os.write(self.fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        if not self._done:
            self._winsize(self.fd)
            try:
                os.killpg(self.proc.pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass

    def close(self) -> None:
        if self.proc and not self._done:
            try:
                os.killpg(self.proc.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
