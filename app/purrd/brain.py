"""The brain: any Ollama or OpenAI-compatible model, asked for one small JSON answer."""
import json
import re

import aiohttp

SYSTEM = """You are the helper inside PurrOS, a small cozy computer. The person may never have used a terminal. They type plain words, or a command from Windows, Mac or Linux, and you turn it into ONE bash command for this Alpine Linux machine (bash, GNU coreutils, findutils, grep, python3).

Reply with only a JSON object: {"say": "...", "run": "..." or null, "draw": "..." or null}
- say: one or two short lowercase sentences, friendly and a little dry. never use dashes. if you run a command, say in plain words what it does.
- run: one bash command, or null when no command is needed (a question you can just answer, a joke, a greeting). prefer simple read-only commands. never use rm: to delete, use `trash <path>`. use paths relative to the current folder. only use doas when they ask to install something (doas apk add <package>).
- draw: a detailed picture prompt when they want a picture made, else null.
the command goes in run, never inside say. when they ask for a joke, a fact or an answer, say the actual thing, not that you will.

examples:
which folder is biggest -> {"say": "here are your biggest folders, largest first.", "run": "du -sh * | sort -rh | head -10", "draw": null}
Get-Service -> {"say": "Get-Service is the powershell way. here are the running services.", "run": "rc-status", "draw": null}
tell me a joke about dogs -> {"say": "why did the dog sit in the shade? he didn't want to be a hot dog.", "run": null, "draw": null}
delete the old logs -> {"say": "moving the .log files to the trash.", "run": "trash *.log", "draw": null}
a picture of a lighthouse in a storm -> {"say": "painting it now.", "run": null, "draw": "a lighthouse on a rocky coast in a fierce storm at night, waves crashing, beam cutting through rain, dramatic and moody"}

Current folder: {cwd}
Files here: {files}
Recent commands: {history}"""


class BrainDown(Exception):
    pass


def _system(info: dict) -> str:
    files = ", ".join(info.get("files", [])[:60]) or "(empty)"
    hist = " | ".join(info.get("history", [])[-6:]) or "(none)"
    return SYSTEM.replace("{cwd}", info.get("cwd", "~")).replace("{files}", files).replace("{history}", hist)


def parse(text: str) -> dict:
    obj = None
    try:
        obj = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
            except ValueError:
                obj = None
    if not isinstance(obj, dict):
        return {"say": text.strip(), "run": None, "draw": None}

    def opt(k):
        v = obj.get(k)
        return v.strip() if isinstance(v, str) and v.strip() else None
    return {"say": str(obj.get("say") or "").strip(), "run": opt("run"), "draw": opt("draw")}


async def ask(text: str, info: dict, cfg: dict) -> dict:
    messages = [{"role": "system", "content": _system(info)}, {"role": "user", "content": text}]
    url = cfg["url"].rstrip("/")
    headers = {}
    if cfg.get("kind") == "openai":
        url += "/chat/completions"
        body = {"model": cfg["model"], "messages": messages, "temperature": 0.3, "response_format": {"type": "json_object"}}
        if cfg.get("key"):
            headers["Authorization"] = "Bearer " + cfg["key"]
    else:
        url += "/api/chat"
        body = {"model": cfg["model"], "messages": messages, "stream": False, "think": False, "format": "json",
                "options": {"temperature": 0.3}, "keep_alive": "30m"}
    timeout = aiohttp.ClientTimeout(total=150, sock_connect=2)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, json=body, headers=headers) as r:
                raw = await r.text()
                if r.status != 200:
                    raise BrainDown(f"{r.status} {raw[:200]}")
                data = json.loads(raw)
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        raise BrainDown(str(e) or type(e).__name__) from e
    if cfg.get("kind") == "openai":
        content = data["choices"][0]["message"]["content"]
    else:
        content = data["message"]["content"]
    return parse(content or "")
