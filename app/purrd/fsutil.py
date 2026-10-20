"""Finding files the way a person names them: any case, by stem, close guesses."""
import difflib
import os
from pathlib import Path

KINDS = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"},
    "video": {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"},
    "audio": {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus", ".aac"},
    "pdf": {".pdf"},
    "text": {".txt", ".md", ".py", ".sh", ".json", ".csv", ".log", ".conf", ".cfg", ".ini", ".yaml", ".yml",
             ".toml", ".js", ".ts", ".html", ".css", ".c", ".h", ".rs", ".go", ".xml", ".rc"},
}
WALK_DEPTH = 4


def kind(p: Path) -> str:
    if p.is_dir():
        return "dir"
    ext = p.suffix.lower()
    for k, exts in KINDS.items():
        if ext in exts:
            return k
    if not ext and _looks_like_text(p):
        return "text"
    return "other"


def _looks_like_text(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            chunk = f.read(2048)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def pretty(p: Path, home: Path) -> str:
    try:
        rel = Path(p).relative_to(home)
    except ValueError:
        return str(p)
    return "~" if str(rel) == "." else "~/" + str(rel)


def listdir(p: Path, show_all: bool = False) -> list[dict]:
    items = []
    try:
        with os.scandir(p) as it:
            entries = list(it)
    except OSError:
        return items
    for e in entries:
        if not show_all and e.name.startswith("."):
            continue
        path = Path(e.path)
        isdir = e.is_dir()
        items.append({"name": e.name, "dir": isdir, "kind": "dir" if isdir else kind(path), "path": str(path)})
    items.sort(key=lambda i: (not i["dir"], i["name"].lower()))
    return items


def _walk(home: Path):
    """Every path under home, breadth first, WALK_DEPTH deep, skipping dot folders."""
    level = [home]
    for _ in range(WALK_DEPTH):
        nxt = []
        for d in level:
            try:
                with os.scandir(d) as it:
                    entries = sorted(it, key=lambda e: e.name.lower())
            except OSError:
                continue
            for e in entries:
                if e.name.startswith("."):
                    continue
                yield Path(e.path)
                if e.is_dir(follow_symlinks=False):
                    nxt.append(Path(e.path))
        level = nxt


def _stem(name: str) -> str:
    return Path(name).stem.lower() if "." in name[1:] else name.lower()


def find(name: str, cwd: Path, home: Path) -> Path | None:
    name = name.strip().strip("\"'")
    if not name:
        return None
    direct = Path(os.path.expanduser(name.replace("~", str(home), 1))) if name.startswith("~") else Path(name)
    if not direct.is_absolute():
        direct = cwd / direct
    if direct.exists():
        return direct
    low = name.lower()
    try:
        with os.scandir(cwd) as it:
            for e in it:
                if e.name.lower() == low:
                    return Path(e.path)
    except OSError:
        pass
    paths = list(_walk(home))
    for test in (lambda p: p.name.lower() == low,
                 lambda p: _stem(p.name) == _stem(low),
                 lambda p: _stem(p.name).startswith(low.replace(" ", "-")) or _stem(p.name).startswith(low)):
        hits = [p for p in paths if test(p)]
        if hits:
            return hits[0]
    return None


def suggest(name: str, home: Path) -> Path | None:
    paths = list(_walk(home))
    names = [p.name.lower() for p in paths]
    hit = difflib.get_close_matches(name.lower(), names, n=1, cutoff=0.6)
    return paths[names.index(hit[0])] if hit else None
