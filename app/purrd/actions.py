"""What PurrOS does for each intent. Everything shows up as protocol messages for the screen."""
import getpass
import glob
import os
import platform
import shutil
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from . import brain, fsutil, pictures, safety, settings, shell
from .router import Intent, route

VERSION = "0.1"
TRASH = ".local/share/Trash"
BRAIN_DOWN = "my brain is napping right now (a game may be running). plain commands still work."
PROTECTED = ("chromium", "chrome", "cage", "purrd", "python", "python3", "seatd", "init")
HELP_TIPS = ["show all files", "open cabin", "play beach-sunset.mp4", "draw a fox asleep in a teacup",
             "edit notes.txt", "delete grocery-list.txt", "what's running", "how much space do i have",
             "theme amber", "settings"]


class Ctx:
    def __init__(self, home: Path, emit, confirm, open_term, settings_path: Path, cwd: Path | None = None,
                 conf: dict | None = None):
        self.home = Path(home)
        self.cwd = Path(cwd or home)
        self._emit, self.confirm, self._open_term = emit, confirm, open_term
        self.settings_path = Path(settings_path)
        self.settings = conf if conf is not None else settings.load(self.settings_path)
        self.history: list[str] = []
        self.pending: str | None = None
        self.last_mood = "idle"
        self.holding = False
        self.noted = False

    async def emit(self, msg: dict) -> None:
        if msg.get("t") == "mood":
            self.last_mood = msg["mood"]
        await self._emit(msg)

    async def mood(self, mood: str, word: str) -> None:
        await self.emit({"t": "mood", "mood": mood, "word": word})

    async def line(self, text: str, cls: str = "") -> None:
        await self.emit({"t": "line", "text": text, "cls": cls})

    async def ran(self, cmd: str) -> None:
        await self.line("ran: " + cmd, "ran")

    async def open_term(self, argv: list[str], title: str) -> None:
        self.holding = True
        await self._open_term(argv, title)

    async def set_settings(self, changes: dict) -> None:
        self.settings = settings.patch(self.settings, changes)
        settings.save(self.settings_path, self.settings)
        await self.emit({"t": "settings", "settings": self.settings})

    def pretty(self, p: Path) -> str:
        return fsutil.pretty(p, self.home)


async def do(intent: Intent, ctx: Ctx) -> None:
    ctx.holding = False
    ctx.noted = bool(intent.note)
    handler = HANDLERS.get(intent.action)
    if handler is None:
        return
    if intent.note:
        await ctx.line(intent.note, "ran")
    await handler(ctx, **intent.args)
    if not ctx.holding and ctx.last_mood not in ("idle", "done", "oops", "playing", "sleeping"):
        await ctx.mood("idle", "ready")


# helpers

def _url(p: Path) -> str:
    return "/file?path=" + quote(str(p))


def _folder_label(ctx: Ctx, p: Path) -> str:
    return "your home folder" if p == ctx.home else ctx.pretty(p).removeprefix("~/")


async def _not_found(ctx: Ctx, name: str) -> None:
    await ctx.mood("oops", "hmm")
    s = fsutil.suggest(Path(name).name, ctx.home)
    if s:
        ctx.pending = "open " + str(s)
        await ctx.line(f"I can't find {name}. There's a {s.name} in {_folder_label(ctx, s.parent)}. Want that one?", "dim")
    else:
        await ctx.line(f"I can't find {name}.", "dim")


def _find(ctx: Ctx, name: str) -> Path | None:
    return fsutil.find(name, ctx.cwd, ctx.home)


def _target(ctx: Ctx, name: str) -> Path:
    """Where a new or destination path lands: ~ and absolute paths as given, others under the current folder."""
    p = Path(os.path.expanduser(name.replace("~", str(ctx.home), 1) if name.startswith("~") else name))
    return p if p.is_absolute() else ctx.cwd / p


def _dest(ctx: Ctx, name: str) -> Path:
    """A destination is matched exactly (any case), never by a guess: a wrong guess would move files somewhere odd."""
    p = _target(ctx, name)
    if not p.exists() and p.parent.is_dir():
        for e in p.parent.iterdir():
            if e.name.lower() == p.name.lower():
                return e
    return p


async def _stream(ctx: Ctx, cmd: str) -> int:
    async def out(text):
        await ctx.emit({"t": "out", "text": text})
    return await shell.run(cmd, ctx.cwd, out)


# handlers

async def a_noop(ctx):
    pass


async def a_list(ctx, path=None, all=False):
    target = ctx.cwd if path is None else _find(ctx, path)
    if target is None:
        return await _not_found(ctx, path)
    if not target.is_dir():
        return await a_open(ctx, str(target))
    await ctx.mood("searching", "looking")
    if not ctx.noted:
        await ctx.ran("ls " + ctx.pretty(target))
    items = fsutil.listdir(target, all)
    n = len(items)
    label = _folder_label(ctx, target)
    if n == 0:
        summary = f"{label} is empty."
    elif target == ctx.home:
        summary = f"{n} {'thing' if n == 1 else 'things'} in your home folder. tap one to open it."
    else:
        summary = f"{n} {'thing' if n == 1 else 'things'} in {label}."
    await ctx.emit({"t": "list", "items": items, "summary": summary})


async def a_cd(ctx, path="~"):
    if path in ("~", ""):
        target = ctx.home
    elif path == "..":
        target = ctx.cwd.parent
    elif path == "-":
        target = ctx.home
    else:
        target = _find(ctx, path)
        if target is None:
            return await _not_found(ctx, path)
        if not target.is_dir():
            await ctx.mood("oops", "hmm")
            return await ctx.line(f"{target.name} is a file, not a folder. try: open {target.name}", "dim")
    ctx.cwd = target
    await ctx.emit({"t": "cwd", "cwd": ctx.pretty(target)})
    await a_list(ctx)


async def a_pwd(ctx):
    await ctx.line(ctx.pretty(ctx.cwd))
    await ctx.ran("pwd")


async def a_open(ctx, path):
    p = _find(ctx, path)
    if p is None:
        return await _not_found(ctx, path)
    if p.is_dir():
        return await a_cd(ctx, str(p))
    k = fsutil.kind(p)
    if k in ("image", "video", "audio", "pdf"):
        await ctx.mood("working", "opening")
        await ctx.ran("open " + ctx.pretty(p))
        await ctx.emit({"t": "media", "kind": k, "name": p.name, "path": str(p), "url": _url(p)})
        if k in ("video", "audio"):
            await ctx.mood("playing", "playing")
    elif k == "text":
        await ctx.mood("working", "reading")
        await ctx.ran("cat " + ctx.pretty(p))
        with open(p, errors="replace") as f:
            lines = f.read(400_000).splitlines()
        await ctx.emit({"t": "text", "name": p.name, "path": str(p), "lines": lines[:400], "more": len(lines) > 400})
    else:
        await ctx.line(f"{p.name} isn't something I can open yet.", "dim")


async def a_edit(ctx, path, editor="nano"):
    p = _find(ctx, path) or _target(ctx, path)
    if p.is_dir():
        await ctx.mood("oops", "hmm")
        return await ctx.line(f"{p.name} is a folder. try: open {p.name}", "dim")
    await ctx.mood("working", "editing")
    await ctx.ran(f"{editor} {ctx.pretty(p)}")
    await ctx.open_term([editor, str(p)], f"{editor} {p.name}")


async def _copy_like(ctx, verb, src, dst):
    s = _find(ctx, src)
    if s is None:
        return await _not_found(ctx, src)
    d = s.parent / dst if verb == "rename" and "/" not in dst else _dest(ctx, dst)
    if d.is_dir():
        d = d / s.name
    if d.exists() and not await ctx.confirm(f"there's already a {d.name} there. replace it?", f"{'cp' if verb == 'copy' else 'mv'} {ctx.pretty(s)} {ctx.pretty(d)}"):
        return await ctx.line("ok, left it alone.", "dim")
    await ctx.mood("working", "working")
    if verb == "copy":
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)
        await ctx.ran(f"cp {'-r ' if s.is_dir() else ''}{ctx.pretty(s)} {ctx.pretty(d)}")
        await ctx.line(f"copied {s.name} to {ctx.pretty(d.parent)}.")
    else:
        shutil.move(str(s), str(d))
        await ctx.ran(f"mv {ctx.pretty(s)} {ctx.pretty(d)}")
        await ctx.line(f"renamed {s.name} to {d.name}." if verb == "rename" else f"moved {s.name} to {ctx.pretty(d.parent)}.")


async def a_copy(ctx, src, dst):
    await _copy_like(ctx, "copy", src, dst)


async def a_move(ctx, src, dst):
    await _copy_like(ctx, "move", src, dst)


async def a_rename(ctx, src, dst):
    await _copy_like(ctx, "rename", src, dst)


async def a_trash(ctx, paths):
    found: list[Path] = []
    for name in paths:
        if any(c in name for c in "*?["):
            found += [Path(p) for p in sorted(glob.glob(str(_target(ctx, name))))]
            continue
        p = _find(ctx, name)
        if p is None:
            return await _not_found(ctx, name)
        found.append(p)
    if not found:
        await ctx.mood("oops", "hmm")
        return await ctx.line("nothing matched that.", "dim")
    for p in found:
        rp = p.resolve()
        if rp == ctx.home.resolve() or rp in ctx.home.resolve().parents:
            await ctx.mood("oops", "hmm")
            return await ctx.line("that's your whole home folder. I won't trash that.", "dim")
        if ctx.home.resolve() not in rp.parents:
            await ctx.mood("oops", "hmm")
            return await ctx.line("that's outside your home folder. I only trash your own stuff.", "dim")
    if len(found) > 3 and not await ctx.confirm(f"move {len(found)} things to the trash?", "mv " + " ".join(ctx.pretty(p) for p in found) + " ~/" + TRASH + "/files/"):
        return await ctx.line("ok, left it alone.", "dim")
    await ctx.mood("working", "tidying")
    files, info = ctx.home / TRASH / "files", ctx.home / TRASH / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    for p in found:
        dest, n = files / p.name, 2
        while dest.exists():
            dest, n = files / f"{p.stem}.{n}{p.suffix}", n + 1
        (info / (dest.name + ".trashinfo")).write_text(
            f"[Trash Info]\nPath={p}\nDeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
        shutil.move(str(p), str(dest))
    await ctx.ran("mv " + " ".join(ctx.pretty(p) for p in found) + " ~/" + TRASH + "/files/")
    if len(found) == 1:
        await ctx.line(f"moved {found[0].name} to the trash. 'empty trash' deletes it for good.")
    else:
        await ctx.line(f"moved {len(found)} things to the trash. 'empty trash' deletes them for good.")


async def a_empty_trash(ctx):
    files = ctx.home / TRASH / "files"
    items = list(files.iterdir()) if files.exists() else []
    if not items:
        return await ctx.line("the trash is already empty.", "dim")
    n = len(items)
    if not await ctx.confirm(f"delete {n} {'thing' if n == 1 else 'things'} in the trash for good?", "rm -rf ~/" + TRASH + "/files/*"):
        return await ctx.line("ok, left it alone.", "dim")
    await ctx.mood("working", "tidying")
    for p in items:
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for p in (ctx.home / TRASH / "info").glob("*.trashinfo"):
        p.unlink()
    await ctx.ran("rm -rf ~/" + TRASH + "/files/*")
    await ctx.line("trash emptied.")


async def a_mkdir(ctx, path):
    d = _target(ctx, path)
    if d.exists():
        await ctx.mood("oops", "hmm")
        return await ctx.line(f"there's already a {d.name} here.", "dim")
    d.mkdir(parents=True)
    await ctx.ran("mkdir " + ctx.pretty(d))
    await ctx.line(f"made a folder called {d.name}.")


async def a_touch(ctx, path):
    f = _target(ctx, path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.touch()
    await ctx.ran("touch " + ctx.pretty(f))
    await ctx.line(f"made {f.name}.")


async def a_find(ctx, query):
    await ctx.mood("searching", "looking")
    q = query.lower()
    qd = q.replace(" ", "-")
    hits = [p for p in fsutil._walk(ctx.home) if q in p.name.lower() or qd in p.name.lower()][:50]
    await ctx.ran(f"find ~ -iname '*{query}*'")
    if not hits:
        await ctx.mood("oops", "hmm")
        return await ctx.line(f"nothing called {query} anywhere in your home folder.", "dim")
    items = [{"name": str(p.relative_to(ctx.home)), "dir": p.is_dir(), "kind": fsutil.kind(p), "path": str(p)} for p in hits]
    await ctx.emit({"t": "list", "items": items, "summary": f"found {len(hits)}."})


async def a_whoami(ctx):
    user = getpass.getuser()
    name = ctx.settings.get("name")
    await ctx.line(f"you're {name}. this computer knows you as {user}." if name else user)
    await ctx.ran("whoami")


async def a_date(ctx):
    now = datetime.now()
    await ctx.line(now.strftime("%A, %B ") + str(now.day) + now.strftime(", %Y. ") + now.strftime("%I:%M %p").lstrip("0").lower())
    await ctx.ran("date")


async def _show(ctx, word, cmd):
    await ctx.mood("working", word)
    await ctx.ran(cmd)
    await _stream(ctx, cmd)


async def a_disk(ctx):
    await _show(ctx, "checking", "df -h /")


async def a_memory(ctx):
    await _show(ctx, "checking", "free -h")


async def a_network(ctx):
    await _show(ctx, "checking", "ip -brief address")


async def a_processes(ctx):
    await _show(ctx, "checking", "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -15")


async def a_top(ctx):
    await ctx.mood("working", "watching")
    prog = "htop" if shutil.which("htop") else "top"
    await ctx.ran(prog)
    await ctx.open_term([prog], prog)


async def a_sysinfo(ctx):
    rel = ""
    try:
        rel = Path("/etc/alpine-release").read_text().strip()
    except OSError:
        pass
    mem = ""
    try:
        kb = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1])
        mem = f"{kb / 1048576:.1f} GB memory"
    except (OSError, StopIteration, ValueError):
        pass
    up = ""
    try:
        secs = int(float(open("/proc/uptime").read().split()[0]))
        up = f"up {secs // 3600} h {secs % 3600 // 60} min" if secs >= 3600 else f"up {secs // 60} min"
    except (OSError, ValueError):
        pass
    await ctx.line(f"PurrOS {VERSION}" + (f" on Alpine Linux {rel}" if rel else ""), "hi")
    await ctx.line(f"linux {platform.release()}, {os.cpu_count()} cores" + (f", {mem}" if mem else "") + (f", {up}" if up else ""))
    await ctx.ran("uname -a")


async def a_about(ctx):
    await ctx.line(f"PurrOS {VERSION}", "hi")
    await ctx.line("a small cozy computer. a cat lives in the corner.")
    await ctx.line("plain words work, so do windows, mac and linux commands.", "dim")
    b = ctx.settings["brain"]
    await ctx.line(f"brain: {b['model']} at {b['url']}", "dim")


async def a_history(ctx):
    past = ctx.history[:-1][-20:]
    if not past:
        return await ctx.line("nothing yet.", "dim")
    start = max(1, len(ctx.history) - len(past))
    for i, h in enumerate(past, start):
        await ctx.line(f"{i:>3}  {h}")


async def a_kill(ctx, target):
    if any(target.lower().startswith(p) for p in PROTECTED):
        return await ctx.line("that would close PurrOS itself. I'll leave it running.", "dim")
    cmd = f"kill {target}" if target.isdigit() else f"pkill -f {target.removesuffix('.exe')}"
    if not await ctx.confirm(f"stop {target}?", cmd):
        return await ctx.line("ok, left it alone.", "dim")
    await _show(ctx, "working", cmd)


async def _power(ctx, word, cmd):
    if not await ctx.confirm(f"{word} the computer?", cmd):
        return await ctx.line("ok, staying on.", "dim")
    if not Path("/etc/purros-release").exists():
        return await ctx.line("this isn't the PurrOS computer, so I won't really do that.", "dim")
    await ctx.mood("sleeping", "bye")
    await ctx.line("goodnight.")
    await _stream(ctx, cmd)


async def a_shutdown(ctx):
    await _power(ctx, "turn off", "doas poweroff")


async def a_reboot(ctx):
    await _power(ctx, "restart", "doas reboot")


async def a_draw(ctx, prompt):
    await ctx.mood("drawing", "drawing")
    await ctx.emit({"t": "progress", "text": "drawing"})
    t0 = time.monotonic()
    try:
        png = await pictures.draw(prompt, ctx.settings["pictures"])
    except pictures.PicturesDown as e:
        await ctx.emit({"t": "progress", "text": ""})
        await ctx.mood("oops", "hmm")
        return await ctx.line(f"I couldn't draw that right now: {e}", "dim")
    await ctx.emit({"t": "progress", "text": ""})
    p = pictures.save_picture(png, prompt, ctx.home)
    await ctx.emit({"t": "media", "kind": "image", "name": p.name, "path": str(p), "url": _url(p), "reveal": True})
    await ctx.mood("done", "done")
    await ctx.line(f"saved to Pictures/{p.name}", "dim")
    await ctx.line(f"took {time.monotonic() - t0:.0f} s", "ran")


async def a_shell(ctx, cmd, typed=True):
    level = safety.classify(cmd)
    if level == "danger" and not await ctx.confirm("this one can do real damage. run it?", cmd):
        return await ctx.line("ok, left it alone.", "dim")
    if level == "change" and not typed and not await ctx.confirm("ok to run this?", cmd):
        return await ctx.line("ok, left it alone.", "dim")
    if shell.is_interactive(cmd):
        await ctx.mood("working", "working")
        return await ctx.open_term(["bash", "-lc", cmd], cmd)
    await ctx.mood("working", "working")
    if not typed:
        await ctx.ran(cmd)
    code = await _stream(ctx, cmd)
    if code not in (0, None):
        await ctx.mood("oops", "hmm")


async def a_brain(ctx, text):
    await ctx.mood("thinking", "thinking")
    info = {"cwd": ctx.pretty(ctx.cwd), "files": [i["name"] for i in fsutil.listdir(ctx.cwd)], "history": ctx.history[-7:-1]}
    try:
        ans = await brain.ask(text, info, ctx.settings["brain"])
    except brain.BrainDown:
        await ctx.mood("oops", "hmm")
        return await ctx.line(BRAIN_DOWN, "dim")
    if ans["say"]:
        await ctx.line(ans["say"])
    if ans["draw"]:
        return await a_draw(ctx, ans["draw"])
    if ans["run"]:
        follow = route(ans["run"])
        if follow.action in ("shell", "brain"):
            return await a_shell(ctx, ans["run"], typed=False)
        return await do(follow, ctx)
    await ctx.mood("idle", "ready")


async def a_help(ctx):
    await ctx.line("plain words work. a few things to try:")
    await ctx.emit({"t": "tips", "items": HELP_TIPS})
    await ctx.line("windows, mac and linux commands work too: dir, ls, ipconfig, open, cls.", "dim")
    await ctx.line("anything underlined can be tapped. ctrl+c stops a command.", "dim")


async def a_clear(ctx):
    await ctx.emit({"t": "clear"})


async def a_settings(ctx):
    await ctx.emit({"t": "panel", "settings": ctx.settings})


async def _set(ctx, key, value):
    try:
        await ctx.set_settings({key: value})
    except ValueError as e:
        await ctx.mood("oops", "hmm")
        return await ctx.line(str(e) + ".", "dim")
    await ctx.line(f"{key} is {value} now.", "dim")


async def a_theme(ctx, value):
    await _set(ctx, "theme", value)


async def a_glow(ctx, value):
    await _set(ctx, "glow", value)


async def a_font(ctx, value):
    await _set(ctx, "font", value)


async def a_name(ctx, value):
    await ctx.set_settings({"name": value})
    await ctx.mood("done", "hi")
    await ctx.line(f"nice to meet you, {value}.")


async def a_refuse(ctx, text):
    await ctx.mood("oops", "hmm")
    await ctx.line(text, "dim")


HANDLERS = {name[2:]: fn for name, fn in globals().items() if name.startswith("a_")}
