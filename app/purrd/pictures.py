"""Pictures: Jarvis's klein through purr-host at home, or any OpenAI-compatible images endpoint."""
import base64
import re
from pathlib import Path

import aiohttp


class PicturesDown(Exception):
    pass


async def draw(prompt: str, cfg: dict) -> bytes:
    url = cfg["url"].rstrip("/")
    timeout = aiohttp.ClientTimeout(total=1800, sock_connect=2)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as s:
            if cfg.get("kind") == "openai":
                headers = {"Authorization": "Bearer " + cfg["key"]} if cfg.get("key") else {}
                body = {"model": cfg.get("model") or "gpt-image-1", "prompt": prompt, "size": "1536x1024", "n": 1}
                async with s.post(url + "/images/generations", json=body, headers=headers) as r:
                    if r.status != 200:
                        raise PicturesDown((await r.text())[:300])
                    item = (await r.json())["data"][0]
                if item.get("b64_json"):
                    return base64.b64decode(item["b64_json"])
                async with s.get(item["url"]) as r:
                    return await r.read()
            async with s.post(url + "/draw", json={"prompt": prompt, "quality": cfg.get("quality", "careful")}) as r:
                if r.status != 200:
                    raise PicturesDown((await r.text())[:300])
                return await r.read()
    except (aiohttp.ClientError, TimeoutError, KeyError, IndexError) as e:
        raise PicturesDown(str(e) or type(e).__name__) from e


def save_picture(png: bytes, prompt: str, home: Path) -> Path:
    words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in prompt.split()]
    slug = "-".join(w for w in words if w)
    slug = "-".join(slug.split("-")[:5]) or "picture"
    folder = Path(home) / "Pictures"
    folder.mkdir(parents=True, exist_ok=True)
    path, n = folder / f"{slug}.png", 2
    while path.exists():
        path, n = folder / f"{slug}-{n}.png", n + 1
    path.write_bytes(png)
    return path
