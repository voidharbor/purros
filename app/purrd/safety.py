"""How risky a shell command is: read (look only), change (modifies something), danger (always ask).

Every command position counts, not just the first word: inside $( ), backticks, <( ), behind wrappers like
env, nice, timeout and xargs, inside sh -c '...' and eval, and after find -exec. When unsure, it says change."""
import re
import shlex

READ_ONLY = {
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "find", "du", "df", "free", "ps", "pwd", "whoami",
    "date", "cal", "uname", "uptime", "echo", "printf", "wc", "sort", "uniq", "cut", "tr", "file", "stat",
    "which", "type", "id", "hostname", "ip", "ping", "env", "printenv", "tree", "less", "more", "diff",
    "md5sum", "sha256sum", "basename", "dirname", "realpath", "readlink", "lsblk", "lscpu", "history",
    "true", "false", "seq", "column", "nl", "jq", "awk", "sed", "top", "htop", "man", "dmesg", "w", "who",
}
DANGER_CMDS = {
    "rm", "rmdir", "dd", "shred", "shutdown", "reboot", "poweroff", "halt", "init", "sudo", "doas", "su",
    "kill", "killall", "pkill", "fdisk", "sfdisk", "parted", "wipefs", "format", "diskpart", "mkswap", "unlink",
    "truncate",
}
# programs that run another command: (options that take a value, how many plain words come before the command)
WRAPPERS = {
    "env": ({"-u", "-C", "-S"}, 0), "nice": ({"-n"}, 0), "ionice": ({"-c", "-n", "-p"}, 0),
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1), "nohup": (set(), 0), "time": ({"-f", "-o"}, 0),
    "command": (set(), 0), "exec": ({"-a"}, 0), "builtin": (set(), 0), "stdbuf": ({"-i", "-o", "-e"}, 0),
    "setsid": (set(), 0), "flock": ({"-w", "-E"}, 1), "watch": ({"-n", "-d"}, 0), "strace": ({"-o", "-e", "-p"}, 0),
    "chroot": (set(), 1), "unbuffer": (set(), 0), "busybox": (set(), 0), "taskset": (set(), 1),
    "xargs": ({"-I", "-n", "-d", "-L", "-P", "-s", "-a", "-E", "-i"}, 0),
}
SHELLS = {"sh", "bash", "zsh", "dash", "ash", "ksh", "fish"}
SCRIPTERS = {"python", "python3", "perl", "ruby", "node", "lua", "php"}
FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}
ORDER = {"read": 0, "change": 1, "danger": 2}


def _worse(a: str, b: str) -> str:
    return a if ORDER[a] >= ORDER[b] else b


def _substitutions(cmd: str) -> tuple[str, list[str]]:
    """Pulls out $( ), <( ), >( ) and backtick bodies; returns the command with each one replaced by a word."""
    out, subs, i = [], [], 0
    while i < len(cmd):
        if cmd.startswith(("$(", "<(", ">("), i):
            depth, j = 1, i + 2
            while j < len(cmd) and depth:
                depth += {"(": 1, ")": -1}.get(cmd[j], 0)
                j += 1
            subs.append(cmd[i + 2:j - 1] if depth == 0 else cmd[i + 2:])
            out.append(" SUBST ")
            i = j
        elif cmd[i] == "`":
            j = cmd.find("`", i + 1)
            j = len(cmd) if j < 0 else j
            subs.append(cmd[i + 1:j])
            out.append(" SUBST ")
            i = j + 1
        else:
            out.append(cmd[i])
            i += 1
    return "".join(out), subs


def _parts(cmd: str) -> list[str]:
    """Splits on unquoted ; | & (and && ||)."""
    parts, cur, quote, i = [], [], None, 0
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and quote != "'" and i + 1 < len(cmd):
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c in ";|&\n":
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _words(part: str) -> list[str]:
    try:
        return shlex.split(part)
    except ValueError:
        return part.split()


def _segment(words: list[str]) -> str:
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words = words[1:]
    if not words:
        return "read"
    prog = words[0].rsplit("/", 1)[-1]
    if prog in DANGER_CMDS or prog.startswith("mkfs"):
        return "danger"
    if prog in WRAPPERS:
        takes, positional = WRAPPERS[prog]
        rest, i = words[1:], 0
        while i < len(rest) and (rest[i].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[i])):
            i += 2 if rest[i] in takes else 1
        rest = rest[i + positional:]
        return _worse("read" if prog in ("env", "time", "watch", "xargs") else "change", _segment(rest)) if rest else "read"
    if prog == "eval":
        return _worse("change", classify(" ".join(words[1:])))
    if prog in SHELLS:
        if "-c" in words[1:-1]:
            return _worse("change", classify(words[words.index("-c") + 1]))
        return "change"
    if prog in SCRIPTERS:
        return "change"
    if prog == "find":
        level = "read"
        for i, w in enumerate(words):
            if w == "-delete":
                return "danger"
            if w in FIND_EXEC:
                sub = []
                for x in words[i + 1:]:
                    if x in (";", "\;", "+"):
                        break
                    sub.append(x)
                level = _worse(level, _worse("change", _segment(sub)))
            elif w in ("-fprint", "-fprintf", "-fls"):
                level = _worse(level, "change")
        return level
    if prog in ("chmod", "chown"):
        if any(w.startswith("-") and "R" in w for w in words[1:]) and any(w in ("/", "~") or w.startswith("/") for w in words[1:]):
            return "danger"
        return "change"
    if prog in ("sed", "awk") and any(re.match(r"^-i", w) or "system(" in w for w in words[1:]):
        return "change"
    return "read" if prog in READ_ONLY else "change"


def classify(cmd: str) -> str:
    if re.search(r":\(\)\s*\{", cmd):
        return "danger"
    flat, subs = _substitutions(cmd)
    worst = "change" if subs else "read"
    for sub in subs:
        worst = _worse(worst, classify(sub))
    plain = flat.replace("2>&1", "").replace("&>/dev/null", "").replace(">/dev/null", "")
    if re.search(r"(?<![<>&0-9])>(?!&)|>>", plain):
        worst = _worse(worst, "change")
    for part in _parts(flat):
        worst = _worse(worst, _segment(_words(part)))
        if worst == "danger":
            return worst
    return worst
