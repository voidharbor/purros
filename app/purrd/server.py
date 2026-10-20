"""purrd's front door: the page, files for the viewers, and one WebSocket session per screen."""
import asyncio
import itertools
import os
from pathlib import Path

from aiohttp import WSMsgType, web

from . import actions, fsutil
from .actions import Ctx
from .router import route
from .shell import Pty

STATIC = Path(__file__).resolve().parent.parent / "static"
LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]"}
YES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "please", "do it", "yes please"}


@web.middleware
async def local_only(req, handler):
    """Only PurrOS's own page may talk to purrd: a local Host (no DNS rebinding) and, when a browser sends an
    Origin, that same address. Without this any web page on the PC could drive the VM through the port relay."""
    h = req.host or ""
    name = h[:h.index("]") + 1] if h.startswith("[") and "]" in h else h.split(":")[0]
    origin = req.headers.get("Origin")
    if name not in LOCAL_NAMES or (origin and origin != "http://" + h):
        raise web.HTTPForbidden(text="PurrOS only talks to its own screen.")
    return await handler(req)


async def index(_req):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def health(_req):
    return web.json_response({"ok": True})


async def serve_file(req):
    p = Path(req.query.get("path", ""))
    if not p.is_absolute() or not p.is_file() or not os.access(p, os.R_OK):
        raise web.HTTPNotFound()
    return web.FileResponse(p)


class Session:
    def __init__(self, ws: web.WebSocketResponse, home: Path):
        self.ws = ws
        self.out: asyncio.Queue = asyncio.Queue()
        self.runs: asyncio.Queue = asyncio.Queue()
        self.ids = itertools.count(1)
        self.asks: dict[str, asyncio.Future] = {}
        self.ptys: dict[str, Pty] = {}
        self.current: asyncio.Task | None = None
        self.ctx = Ctx(home=home, emit=self.emit, confirm=self.confirm, open_term=self.open_term,
                       settings_path=home / ".config/purros/settings.json")

    async def emit(self, msg: dict) -> None:
        self.out.put_nowait(msg)

    async def confirm(self, question: str, cmd: str) -> bool:
        qid = f"q{next(self.ids)}"
        fut = asyncio.get_running_loop().create_future()
        self.asks[qid] = fut
        await self.emit({"t": "ask", "id": qid, "question": question, "cmd": cmd})
        try:
            return await fut
        finally:
            self.asks.pop(qid, None)

    async def open_term(self, argv: list[str], title: str) -> None:
        sid = f"p{next(self.ids)}"

        def on_exit(_code):
            self.ptys.pop(sid, None)
            self.out.put_nowait({"t": "term_exit", "sid": sid})
            self.out.put_nowait({"t": "mood", "mood": "idle", "word": "ready"})
        pty = Pty(argv, self.ctx.cwd, 100, 24, on_data=lambda d: self.out.put_nowait({"t": "term_out", "sid": sid, "data": d}),
                  on_exit=on_exit)
        self.ptys[sid] = pty
        await self.emit({"t": "term_open", "sid": sid, "title": title})
        try:
            pty.start()
        except OSError as e:
            self.ptys.pop(sid, None)
            await self.emit({"t": "term_exit", "sid": sid})
            await self.ctx.mood("oops", "hmm")
            await self.ctx.line(f"couldn't start {argv[0]}: {e.strerror or e}", "dim")

    async def sender(self) -> None:
        while True:
            msg = await self.out.get()
            if self.ws.closed:
                return
            await self.ws.send_json(msg)

    async def worker(self) -> None:
        while True:
            rid, text = await self.runs.get()
            ctx = self.ctx
            word = text.strip().lower().rstrip(".!")
            if ctx.pending and word in YES:
                text = ctx.pending
            ctx.pending = None
            if text.strip():
                ctx.history.append(text.strip())
            self.current = asyncio.create_task(actions.do(route(text), ctx))
            try:
                await self.current
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():  # the screen went away: end the worker, not just the run
                    raise
                await ctx.line("(stopped)", "dim")
                await ctx.mood("idle", "ready")
            except Exception as e:  # one bad command must not end the session
                await ctx.mood("oops", "hmm")
                await ctx.line(f"something went wrong: {e}", "dim")
            finally:
                self.current = None
            await self.emit({"t": "end", "id": rid})

    def complete(self, text: str) -> list[str]:
        last = text.split(" ")[-1] if text else ""
        folder, _, stem = last.rpartition("/")
        base = fsutil.find(folder, self.ctx.cwd, self.ctx.home) if folder else self.ctx.cwd
        if base is None or not base.is_dir():
            return []
        out = []
        for i in fsutil.listdir(base):
            if i["name"].lower().startswith(stem.lower()):
                out.append((folder + "/" if folder else "") + i["name"] + ("/" if i["dir"] else ""))
        return out[:30]

    async def handle(self, m: dict) -> None:
        t = m.get("t")
        if t == "run":
            self.runs.put_nowait((m.get("id"), str(m.get("text", ""))))
        elif t == "stop":
            if self.current:
                self.current.cancel()
        elif t == "confirm":
            fut = self.asks.get(m.get("id"))
            if fut and not fut.done():
                fut.set_result(bool(m.get("yes")))
        elif t == "term_in":
            p = self.ptys.get(m.get("sid"))
            if p:
                p.write(str(m.get("data", "")))
        elif t == "term_resize":
            p = self.ptys.get(m.get("sid"))
            if p:
                p.resize(int(m.get("cols", 80)), int(m.get("rows", 24)))
        elif t == "term_close":
            p = self.ptys.get(m.get("sid"))
            if p:
                p.close()
        elif t == "settings":
            try:
                await self.ctx.set_settings(m.get("patch") or {})
            except ValueError as e:
                await self.ctx.line(str(e) + ".", "dim")
        elif t == "complete":
            await self.emit({"t": "completions", "id": m.get("id"), "items": self.complete(str(m.get("text", "")))})

    def close(self) -> None:
        for p in list(self.ptys.values()):
            p.close()
        for f in self.asks.values():
            if not f.done():
                f.cancel()
        if self.current:
            self.current.cancel()


async def ws_handler(req):
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=4 * 1024 * 1024)
    await ws.prepare(req)
    s = Session(ws, req.app["home"])
    await s.emit({"t": "hello", "settings": s.ctx.settings, "cwd": s.ctx.pretty(s.ctx.cwd), "version": actions.VERSION})
    tasks = [asyncio.create_task(s.sender()), asyncio.create_task(s.worker())]
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = msg.json()
                except ValueError:
                    continue
                if isinstance(data, dict):
                    await s.handle(data)
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        s.close()
        for t in tasks:
            t.cancel()
    return ws


def make_app(home: Path | None = None) -> web.Application:
    app = web.Application(middlewares=[local_only])
    app["home"] = Path(home or os.environ.get("PURROS_HOME") or Path.home())
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/file", serve_file)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", STATIC)
    return app


def main():
    port = int(os.environ.get("PURROS_PORT", "7777"))
    print(f"purrd listening on 127.0.0.1:{port}", flush=True)
    web.run_app(make_app(), host="127.0.0.1", port=port, print=None)
