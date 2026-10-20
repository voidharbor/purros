#!/usr/bin/env python3
"""Draws the PurrOS cat (idle, eyes open) from app/static/cat.js into purros.ico and purros-256.png.
Node renders the sprite so the icon is the exact cat on screen; Pillow scales it up pixel-sharp."""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
CAT_JS = HERE.parent / "app/static/cat.js"
BG, FG, HI, DIM = (6, 17, 10, 255), "#8ef0a6", "#d4ffdf", "#55a06a"
NODE = r"""
const fs = require('fs'), vm = require('vm');
const window = {};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), { window, Math });
const px = {};
const ctx = { globalAlpha: 1, fillStyle: '',
  clearRect(x, y, w, h) { for (let i = x; i < x + w; i++) for (let j = y; j < y + h; j++) delete px[i + ',' + j]; },
  fillRect(x, y) { px[x + ',' + y] = [this.fillStyle, this.globalAlpha]; } };
window.PurrCat.draw(ctx, 'idle', 0.5, JSON.parse(process.argv[2]));
console.log(JSON.stringify(px));
"""


def sprite() -> dict:
    colors = json.dumps({"fg": FG, "hi": HI, "dim": DIM})
    out = subprocess.run(["node", "-e", NODE, str(CAT_JS), colors], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def sprite_image(px: dict) -> Image.Image:
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for key, (color, alpha) in px.items():
        x, y = map(int, key.split(","))
        im.putpixel((x, y), tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (round(255 * alpha),))
    return im.crop(im.getbbox())


def render(size: int, cat: Image.Image) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, size - 1, size - 1], radius=max(2, size // 6), fill=BG)
    k = max(1, int(size * 0.78 // max(cat.size)))
    big = cat.resize((cat.width * k, cat.height * k), Image.NEAREST)
    im.alpha_composite(big, ((size - big.width) // 2, (size - big.height) // 2))
    return im


if __name__ == "__main__":
    cat = sprite_image(sprite())
    big = render(256, cat)
    big.save(HERE / "purros-256.png")
    big.save(HERE / "purros.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
             append_images=[render(s, cat) for s in (16, 24, 32, 48, 64, 128)])
    print("wrote purros.ico and purros-256.png")
