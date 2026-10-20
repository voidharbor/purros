"""The phrasebook: plain words and Windows, PowerShell, Mac and Linux commands, all mapped to one set of actions."""
import re
import shlex
import shutil
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Intent:
    action: str
    args: dict = field(default_factory=dict)
    note: str | None = None


SUFFIX = {
    "list": "same list:", "network": "here's the network:", "processes": "here's what's running:",
    "disk": "here's the disk:", "sysinfo": "here's this computer:", "edit": "opening it in nano:",
    "memory": "here's the memory:",
}
REFUSE = "format wipes a whole disk. I won't do that from here."
WIPERS = {"format", "diskpart", "fdisk", "sfdisk", "parted", "wipefs", "gdisk", "cfdisk"}
SHELL_META = re.compile(r"[|><;&`$]")

# first word -> (action, dialect). dialect None = Linux or plain English, no note.
WORDS = {
    "ls": ("list", None), "dir": ("list", "windows"), "gci": ("list", "powershell"), "get-childitem": ("list", "powershell"),
    "explorer": ("list", "windows"),
    "cd": ("cd", None), "chdir": ("cd", None), "set-location": ("cd", "powershell"), "sl": ("cd", "powershell"), "pushd": ("cd", None),
    "pwd": ("pwd", None), "get-location": ("pwd", "powershell"), "gl": ("pwd", "powershell"),
    "cat": ("open", None), "type": ("open", "windows"), "gc": ("open", "powershell"), "get-content": ("open", "powershell"),
    "more": ("open", None), "start": ("open", "windows"), "xdg-open": ("open", None), "invoke-item": ("open", "powershell"),
    "ii": ("open", "powershell"), "open": ("open", None),
    "edit": ("edit", None), "notepad": ("edit", "windows"), "notepad.exe": ("edit", "windows"), "nano": ("edit", None),
    "vim": ("edit", None), "vi": ("edit", None), "nvim": ("edit", None), "code": ("edit", None), "gedit": ("edit", None),
    "textedit": ("edit", "mac"),
    "copy": ("copy", "windows"), "cp": ("copy", None), "copy-item": ("copy", "powershell"), "cpi": ("copy", "powershell"),
    "xcopy": ("copy", "windows"), "robocopy": ("copy", "windows"),
    "move": ("move", "windows"), "mv": ("move", None), "move-item": ("move", "powershell"), "mi": ("move", "powershell"),
    "ren": ("rename", "windows"), "rename": ("rename", None), "rename-item": ("rename", "powershell"), "rni": ("rename", "powershell"),
    "del": ("trash", "windows"), "erase": ("trash", "windows"), "rd": ("trash", "windows"), "rmdir": ("trash", None),
    "rm": ("trash", None), "unlink": ("trash", None), "remove-item": ("trash", "powershell"), "ri": ("trash", "powershell"),
    "trash": ("trash", None),
    "mkdir": ("mkdir", None), "md": ("mkdir", "windows"), "new-item": ("touch", "powershell"), "ni": ("touch", "powershell"),
    "touch": ("touch", None),
    "where": ("find", "windows"), "locate": ("find", None), "mdfind": ("find", "mac"), "find": ("find", None),
    "whoami": ("whoami", None),
    "date": ("date", None), "time": ("date", None), "get-date": ("date", "powershell"),
    "df": ("disk", None), "wmic": ("disk", "windows"), "get-psdrive": ("disk", "powershell"), "gdr": ("disk", "powershell"),
    "diskutil": ("disk", "mac"),
    "free": ("memory", None), "vm_stat": ("memory", "mac"),
    "ipconfig": ("network", "windows"), "ifconfig": ("network", "mac"), "ip": ("network", None),
    "get-netipaddress": ("network", "powershell"), "gip": ("network", "powershell"),
    "tasklist": ("processes", "windows"), "ps": ("processes", None), "get-process": ("processes", "powershell"),
    "gps": ("processes", "powershell"),
    "top": ("top", None), "htop": ("top", None), "taskmgr": ("top", "windows"),
    "systeminfo": ("sysinfo", "windows"), "ver": ("sysinfo", "windows"), "winver": ("sysinfo", "windows"),
    "sw_vers": ("sysinfo", "mac"), "system_profiler": ("sysinfo", "mac"), "uname": ("sysinfo", None),
    "neofetch": ("sysinfo", None), "fastfetch": ("sysinfo", None),
    "history": ("history", None), "doskey": ("history", "windows"), "get-history": ("history", "powershell"), "h": ("history", "powershell"),
    "kill": ("kill", None), "killall": ("kill", None), "pkill": ("kill", None), "taskkill": ("kill", "windows"),
    "stop-process": ("kill", "powershell"), "spps": ("kill", "powershell"),
    "cls": ("clear", None), "clear": ("clear", None), "clear-host": ("clear", None),
    "shutdown": ("shutdown", None), "poweroff": ("shutdown", None), "halt": ("shutdown", None), "stop-computer": ("shutdown", None),
    "reboot": ("reboot", None), "restart-computer": ("reboot", None), "restart": ("reboot", None),
    "help": ("help", None), "settings": ("settings", None), "about": ("about", None),
}

D = r"(?-i:the |my |this |that )?"  # lowercase only: "My Notes.txt" is a name
ENGLISH: list[tuple[str, Callable[[re.Match], Intent]]] = [
    (r"(?:help|\?|what can you do|commands|what do i do)", lambda m: Intent("help")),
    (r"(?:settings|preferences|options|control panel|change (?:the )?theme)", lambda m: Intent("settings")),
    (r"(theme|glow|font)\s+(\w+)", lambda m: Intent(m[1].lower(), {"value": m[2].lower()})),
    (r"(?:call me|my name is)\s+(\w+)", lambda m: Intent("name", {"value": m[1]})),
    (r"(?:clear(?: the)? screen|clean up the screen)", lambda m: Intent("clear")),
    (r"(?:restart|reboot)(?: the computer| now)?|shutdown\s+[/-]r.*", lambda m: Intent("reboot")),
    (r"(?:shut ?down|turn off|power off)(?: the computer| now|\s+[/-][sh].*)?", lambda m: Intent("shutdown")),
    (r"empty (?:the |my )?(?:trash|recycle bin|bin)", lambda m: Intent("empty_trash")),
    (r"(?:please\s+)?(?:draw|paint|sketch|illustrate|imagine)(?:\s+me)?\s+(.+)", lambda m: Intent("draw", {"prompt": m[1]})),
    (r"(?:make|create|generate|give)(?: me)? (?:a |an )?(?:picture|image|drawing|painting|photo|illustration|art)(?: of)?\s+(.+)",
     lambda m: Intent("draw", {"prompt": m[1]})),
    (r"(?:show|list|see|display)(?: me)?(?: all| my| the)*\s+(?:files|stuff|things|folders)(?: here| in here)?",
     lambda m: Intent("list", {"path": None})),
    (r"what(?:'?s| is) (?:in )?(?:here|in this folder|this folder)", lambda m: Intent("list", {"path": None})),
    (r"what(?:'?s| is) in " + D + r"(.+?)(?: folder)?", lambda m: Intent("list", {"path": m[1]})),
    (r"where am i", lambda m: Intent("pwd")),
    (r"what(?:'?s| is) the time|what time is it|what day is it|what(?:'?s| is) the date", lambda m: Intent("date")),
    (r"who am i", lambda m: Intent("whoami")),
    (r"what(?:'?s| is) my ip(?: address)?|my ip(?: address)?|network(?: info)?", lambda m: Intent("network")),
    (r"what(?:'?s| is) running|running (?:programs|apps)|processes", lambda m: Intent("processes")),
    (r"task manager|activity monitor|system monitor", lambda m: Intent("top")),
    (r"about this (?:computer|mac|pc)|system info(?:rmation)?|specs", lambda m: Intent("sysinfo")),
    (r"how much (?:disk )?space(?: do i have| is left)?|disk space|free space|storage", lambda m: Intent("disk")),
    (r"how much (?:memory|ram)(?: do i have)?|memory|ram", lambda m: Intent("memory")),
    (r"go home", lambda m: Intent("cd", {"path": "~"})),
    (r"go (?:back|up)|up", lambda m: Intent("cd", {"path": ".."})),
    (r"(?:go to|open folder|open the folder|enter)\s+" + D + r"(.+?)(?: folder)?", lambda m: Intent("cd", {"path": m[1]})),
    (r"(?:make|create|new)(?: a)? (?:folder|directory)(?: called| named)?\s+(.+)", lambda m: Intent("mkdir", {"path": m[1]})),
    (r"(?:make|create|new)(?: a)? (?:file|text file|note)(?: called| named)?\s+(.+)", lambda m: Intent("touch", {"path": m[1]})),
    (r"(?:search for|look for|find me|where is|where's)\s+" + D + r"(.+)", lambda m: Intent("find", {"query": m[1]})),
    (r"(?:delete|remove|throw away|get rid of|erase)\s+" + D + r"(.+)", lambda m: Intent("trash", {"paths": _names(m[1])})),
    (r"(?:rename)\s+(.+?)\s+to\s+(.+)", lambda m: Intent("rename", {"src": m[1], "dst": m[2]})),
    (r"(?:move)\s+(.+?)\s+(?:to|into)\s+" + D + r"(.+?)(?: folder)?", lambda m: Intent("move", {"src": m[1], "dst": m[2]})),
    (r"(?:copy)\s+(.+?)\s+(?:to|into)\s+" + D + r"(.+?)(?: folder)?", lambda m: Intent("copy", {"src": m[1], "dst": m[2]})),
    (r"(?:play|show me|view|watch|listen to|read|open)\s+" + D + r"(.+)", lambda m: Intent("open", {"path": m[1]})),
]
ENGLISH_RX = [(re.compile(rx + r"$", re.I), fn) for rx, fn in ENGLISH]


# Command names that are also everyday English. "which folder is biggest" is a question, "which python3" a command.
ENGLISHY = {"which", "who", "what", "make", "find", "sort", "test", "time", "watch", "look", "tell", "show", "say",
            "read", "wait", "sleep", "more", "less", "last", "head", "tail", "cut", "join", "split", "paste", "file",
            "type", "link", "touch", "top", "free", "install", "info", "date", "w", "id", "at", "nice", "tree", "can",
            "help", "man", "script", "units", "write", "mail", "open", "start", "stop", "see", "history", "kill", "clear"}
SENTENCE_WORD = re.compile(r"^[\w']+[?!.,]?$")


def _sentence(tokens: list[str]) -> bool:
    return len(tokens) >= 4 and tokens[0].lower() in ENGLISHY and all(SENTENCE_WORD.match(t) for t in tokens)


def _uq(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def _unquote(intent: Intent) -> Intent:
    for k in ("path", "query", "src", "dst"):
        if isinstance(intent.args.get(k), str):
            intent.args[k] = _uq(intent.args[k])
    if isinstance(intent.args.get("paths"), list):
        intent.args["paths"] = [_uq(p) for p in intent.args["paths"]]
    return intent


def _names(text: str) -> list[str]:
    words = text.split()
    return words if len(words) > 1 and all("." in w for w in words) else [text.strip()]


def _note(word: str, dialect: str | None, action: str) -> str | None:
    if not dialect:
        return None
    return f"{word} is the {dialect} way. {SUFFIX.get(action, 'same thing here:')}"


def _plain(args: list[str]) -> list[str]:
    """Arguments without flags (-x, --x, /x)."""
    return [a for a in args if not (a.startswith("-") or (a.startswith("/") and len(a) <= 3))]


def route(text: str, on_path: Callable[[str], object] = shutil.which) -> Intent:
    text = text.strip()
    if not text:
        return Intent("noop")
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()
    first = tokens[0] if tokens else text
    fl = first.lower()
    if fl in WIPERS or fl.startswith("mkfs"):
        return Intent("refuse", {"text": REFUSE})
    # a quoted name like "Tom & Jerry.mp4" (what a click sends) is a name, not shell syntax
    if not SHELL_META.search(re.sub(r'"[^"]*"|\'[^\']*\'', "", text)):
        bare = text.rstrip("?!. ") or text
        for rx, fn in ENGLISH_RX:
            m = rx.match(bare)
            if m:
                return _unquote(fn(m))
        if _sentence(tokens):
            return Intent("brain", {"text": text})
        hit = _command(first, fl, tokens[1:], text)
        if hit:
            return hit
    if on_path(first):
        return Intent("shell", {"cmd": text})
    return Intent("brain", {"text": text})


def _command(first: str, fl: str, rest: list[str], text: str) -> Intent | None:
    if fl not in WORDS:
        return None
    action, dialect = WORDS[fl]
    plain = _plain(rest)
    flags = [a for a in rest if a not in plain]
    note = _note(first, dialect, action)

    def it(a, args=None):
        return Intent(a, args or {}, _note(first, dialect, a))

    if action == "list":
        if fl == "ls" and flags:
            return Intent("shell", {"cmd": text})
        if any(f.lower() in ("/s", "-recurse", "-r") for f in flags) and plain:
            return it("find", {"query": plain[-1]})
        return it("list", {"path": plain[0] if plain and plain[0] != "." else None})
    if action == "cd":
        return it("cd", {"path": plain[0] if plain else "~"})
    if action == "open":
        if not plain:
            return None
        if fl == "cat" and (flags or len(plain) > 1):
            return Intent("shell", {"cmd": text})
        return it("open", {"path": " ".join(plain)})
    if action == "edit":
        if not plain:
            return None
        editor = "vim" if fl in ("vim", "vi", "nvim") else "nano"
        return it("edit", {"path": " ".join(plain), "editor": editor})
    if action in ("copy", "move", "rename"):
        if len(plain) < 2:
            return None
        return it(action, {"src": plain[0], "dst": plain[-1]})
    if action == "trash":
        return it("trash", {"paths": plain}) if plain else None
    if action == "mkdir":
        return it("mkdir", {"path": " ".join(plain)}) if plain else None
    if action == "touch":
        if fl in ("new-item", "ni") and any(a.lower() == "directory" for a in rest):
            names = [a for a in plain if a.lower() != "directory"]
            return it("mkdir", {"path": names[0]}) if names else None
        return it("touch", {"path": " ".join(plain)}) if plain else None
    if action == "find":
        if fl == "find" and (flags or (plain and plain[0] in (".", "/", "~"))):
            return Intent("shell", {"cmd": text})
        return it("find", {"query": " ".join(plain)}) if plain else None
    if action == "network" and fl == "ip" and plain and plain[0] not in ("a", "addr", "address"):
        return Intent("shell", {"cmd": text})
    if action == "processes" and fl == "ps" and rest:
        return Intent("shell", {"cmd": text})
    if action == "kill":
        lower = [a.lower() for a in rest]
        for key in ("/im", "/pid", "-name", "-id"):
            if key in lower and lower.index(key) + 1 < len(rest):
                return it("kill", {"target": rest[lower.index(key) + 1]})
        return it("kill", {"target": plain[-1]}) if plain else None
    if action == "shutdown" and fl == "shutdown" and any(a.lower() in ("/r", "-r") for a in rest):
        return Intent("reboot")
    if action in ("clear", "shutdown", "reboot", "help", "settings", "about"):
        return Intent(action)
    if action == "history" and fl == "doskey" and "/history" not in [a.lower() for a in rest]:
        return None
    return Intent(action, {}, note)
