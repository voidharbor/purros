"""PurrOS settings: one small JSON file, checked on every change."""
import copy
import json
from pathlib import Path

DEFAULTS = {
    "name": "",
    "theme": "phosphor",
    "glow": "light",
    "font": "pixel",
    "nap_seconds": 45,
    "brain": {"kind": "ollama", "url": "http://10.0.2.2:11434", "model": "jarvis-ornith-ctx131072", "key": ""},
    "pictures": {"kind": "purr-host", "url": "http://10.0.2.2:7790", "quality": "careful", "model": "", "key": ""},
}
CHOICES = {
    "theme": {"phosphor", "amber", "ice", "paper"},
    "glow": {"off", "light", "more"},
    "font": {"pixel", "clean"},
    ("brain", "kind"): {"ollama", "openai"},
    ("pictures", "kind"): {"purr-host", "openai"},
    ("pictures", "quality"): {"careful", "quick"},
}


def _check(key, value):
    allowed = CHOICES.get(key)
    if allowed is not None and value not in allowed:
        name = key if isinstance(key, str) else ".".join(key)
        raise ValueError(f"{name} can be {', '.join(sorted(allowed))}")


def patch(d: dict, changes: dict) -> dict:
    out = copy.deepcopy(d)
    for k, v in changes.items():
        if k not in DEFAULTS:
            raise ValueError(f"no setting called {k}")
        if isinstance(DEFAULTS[k], dict):
            if not isinstance(v, dict):
                raise ValueError(f"{k} needs fields")
            for sk, sv in v.items():
                if sk not in DEFAULTS[k]:
                    raise ValueError(f"no setting called {k}.{sk}")
                _check((k, sk), sv)
                out[k][sk] = str(sv)
        elif k == "nap_seconds":
            n = int(v)
            if not 10 <= n <= 3600:
                raise ValueError("nap_seconds is 10 to 3600")
            out[k] = n
        else:
            _check(k, v)
            out[k] = str(v)
    return out


def load(path: Path) -> dict:
    try:
        return patch(DEFAULTS, json.loads(Path(path).read_text()))
    except (OSError, ValueError, TypeError):
        return copy.deepcopy(DEFAULTS)


def save(path: Path, d: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2) + "\n")
    tmp.replace(path)
