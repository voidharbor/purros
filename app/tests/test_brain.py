import json
import unittest
from pathlib import Path
import tempfile

from aiohttp import web
from aiohttp.test_utils import TestServer

from purrd import brain, pictures

INFO = {"cwd": "~", "files": ["notes.txt", "Pictures"], "history": ["show all files"]}


class FakeServer:
    def __init__(self, handler):
        self.app = web.Application()
        self.app.router.add_route("POST", "/{tail:.*}", self._wrap(handler))
        self.seen = []

    def _wrap(self, handler):
        async def h(req):
            body = await req.read()
            self.seen.append((req.path, dict(req.headers), json.loads(body) if body else None))
            return await handler(req)
        return h

    async def __aenter__(self):
        self.server = TestServer(self.app, host="127.0.0.1")
        await self.server.start_server()
        self.url = f"http://127.0.0.1:{self.server.port}"
        return self

    async def __aexit__(self, *a):
        await self.server.close()


def reply_json(obj):
    async def h(_req):
        return web.json_response(obj)
    return h


class BrainTest(unittest.IsolatedAsyncioTestCase):
    async def test_ollama(self):
        async with FakeServer(reply_json({"message": {"content": '{"say":"hi","run":"ls"}'}})) as s:
            got = await brain.ask("list stuff", INFO, {"kind": "ollama", "url": s.url, "model": "m1"})
        self.assertEqual(got, {"say": "hi", "run": "ls", "draw": None})
        path, _h, body = s.seen[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual((body["think"], body["format"], body["stream"], body["model"]), (False, "json", False, "m1"))
        self.assertIn("notes.txt", body["messages"][0]["content"])
        self.assertEqual(body["messages"][-1], {"role": "user", "content": "list stuff"})

    async def test_openai(self):
        async with FakeServer(reply_json({"choices": [{"message": {"content": '{"say":"ok","draw":"a fox"}'}}]})) as s:
            got = await brain.ask("fox pic", INFO, {"kind": "openai", "url": s.url + "/v1", "model": "gpt", "key": "sk-1"})
        self.assertEqual(got, {"say": "ok", "run": None, "draw": "a fox"})
        path, headers, body = s.seen[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer sk-1")
        self.assertEqual(body["response_format"], {"type": "json_object"})

    async def test_json_inside_prose_or_fences(self):
        text = 'Sure!\n```json\n{"say": "here", "run": "df -h"}\n```'
        async with FakeServer(reply_json({"message": {"content": text}})) as s:
            got = await brain.ask("x", INFO, {"kind": "ollama", "url": s.url, "model": "m"})
        self.assertEqual(got, {"say": "here", "run": "df -h", "draw": None})

    async def test_plain_text_reply(self):
        async with FakeServer(reply_json({"message": {"content": "just words"}})) as s:
            got = await brain.ask("x", INFO, {"kind": "ollama", "url": s.url, "model": "m"})
        self.assertEqual(got, {"say": "just words", "run": None, "draw": None})

    async def test_down(self):
        with self.assertRaises(brain.BrainDown):
            await brain.ask("x", INFO, {"kind": "ollama", "url": "http://127.0.0.1:9", "model": "m"})

    async def test_server_error_is_down(self):
        async def boom(_req):
            return web.Response(status=500, text="model not loaded")
        async with FakeServer(boom) as s:
            with self.assertRaises(brain.BrainDown):
                await brain.ask("x", INFO, {"kind": "ollama", "url": s.url, "model": "m"})


class PicturesTest(unittest.IsolatedAsyncioTestCase):
    async def test_purr_host(self):
        async def png(_req):
            return web.Response(body=b"\x89PNGdata", content_type="image/png")
        async with FakeServer(png) as s:
            got = await pictures.draw("a fox", {"kind": "purr-host", "url": s.url, "quality": "quick"})
        self.assertEqual(got, b"\x89PNGdata")
        self.assertEqual(s.seen[0][0], "/draw")
        self.assertEqual(s.seen[0][2], {"prompt": "a fox", "quality": "quick"})

    async def test_openai_images(self):
        import base64
        async with FakeServer(reply_json({"data": [{"b64_json": base64.b64encode(b"img").decode()}]})) as s:
            got = await pictures.draw("a fox", {"kind": "openai", "url": s.url + "/v1", "model": "gpt-image-1", "key": "k"})
        self.assertEqual(got, b"img")
        self.assertEqual(s.seen[0][0], "/v1/images/generations")

    async def test_down(self):
        with self.assertRaisesRegex(pictures.PicturesDown, "the picture maker isn't answering"):
            await pictures.draw("x", {"kind": "purr-host", "url": "http://127.0.0.1:9", "quality": "careful"})

    async def test_host_error_text(self):
        async def busy(_req):
            return web.Response(status=503, text="a game is running")
        async with FakeServer(busy) as s:
            with self.assertRaisesRegex(pictures.PicturesDown, "a game is running"):
                await pictures.draw("x", {"kind": "purr-host", "url": s.url, "quality": "careful"})

    def test_save_picture_names(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            a = pictures.save_picture(b"1", "a cozy cabin in the snow at night", home)
            b = pictures.save_picture(b"2", "a cozy cabin in the snow at night", home)
            self.assertEqual(a, home / "Pictures" / "a-cozy-cabin-in-the.png")
            self.assertEqual(b, home / "Pictures" / "a-cozy-cabin-in-the-2.png")
            self.assertEqual(a.read_bytes(), b"1")
            self.assertEqual(pictures.save_picture(b"3", "Fox!!", home).name, "fox.png")
