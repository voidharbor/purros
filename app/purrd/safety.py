"""How risky a shell command is: read (look only), change (modifies something), danger (always ask)."""
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
    "kill", "killall", "pkill", "fdisk", "sfdisk", "parted", "wipefs", "format", "diskpart", "mkswap",
}
FIND_CHANGERS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"}
SED_CHANGERS = re.compile(r"(^|\s)-i")


def _parts(cmd: str) -> list[str]:
    return [p.strip() for p in re.split(r"\|\||&&|;|\||&", cmd) if p.strip()]


def classify(cmd: str) -> str:
    if re.search(r":\(\)\s*\{", cmd):
        return "danger"
    worst = "read"
    if re.search(r"(?<![<>&0-9])>(?!&)|>>", cmd.replace("2>&1", "").replace("&>/dev/null", "").replace(">/dev/null", "")):
        worst = "change"
    for part in _parts(cmd):
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        if not words:
            continue
        prog = words[0].rsplit("/", 1)[-1]
        if prog in DANGER_CMDS or prog.startswith("mkfs"):
            return "danger"
        if prog == "chmod" or prog == "chown":
            if any(w.startswith("-") and "R" in w for w in words[1:]) and any(w in ("/", "~") or w.startswith("/") for w in words[1:]):
                return "danger"
            worst = "change"
            continue
        if prog == "find" and any(w in FIND_CHANGERS for w in words):
            worst = "change"
            continue
        if prog in ("sed", "awk") and (SED_CHANGERS.search(part) or "system(" in part):
            worst = "change"
            continue
        if prog not in READ_ONLY:
            worst = "change"
    return worst
