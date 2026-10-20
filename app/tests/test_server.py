import asyncio
import json
import unittest

from aiohttp.test_utils import TestClient, TestServer

from helpers import make_home
from purrd.server import make_app


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.td, self.home = make_home()
        self.client = TestClient(TestServer(make_app(self.home)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.td.cleanup()

    async def ws(self):
        ws = await self.client.ws_connect("/ws")
        hello = await ws.receive_json(timeout=5)
        return ws, hello

    async def until(self, ws, pred, timeout=10):
        got = []
        while True:
            m = await ws.receive_json(timeout=timeout)
            got.append(m)
            if pred(m):
                return got

    async def run_text(self, ws, text, rid):
        await ws.send_json({"t": "run", "id": rid, "text": text})
        return await self.until(ws, lambda m: m["t"] == "end" and m["id"] == rid)

    async def test_health(self):
        r = await self.client.get("/health")
        self.assertEqual(await r.json(), {"ok": True})

    async def test_index(self):
        r = await self.client.get("/")
        self.assertEqual(r.status, 200)

    async def test_hello(self):
        ws, hello = await self.ws()
        self.assertEqual(hello["t"], "hello")
        self.assertEqual(hello["cwd"], "~")
        self.assertEqual(hello["settings"]["theme"], "phosphor")
        await ws.close()

    async def test_show_all_files(self):
        ws, _ = await self.ws()
        got = await self.run_text(ws, "show all files", "r1")
        kinds = [m["t"] for m in got]
        self.assertEqual(kinds[0], "mood")
        self.assertIn("list", kinds)
        self.assertIn({"t": "line", "text": "ran: ls ~", "cls": "ran"}, got)
        await ws.close()

    async def test_settings_persist(self):
        ws, _ = await self.ws()
        await ws.send_json({"t": "settings", "patch": {"theme": "ice"}})
        got = await self.until(ws, lambda m: m["t"] == "settings")
        self.assertEqual(got[-1]["settings"]["theme"], "ice")
        saved = json.loads((self.home / ".config/purros/settings.json").read_text())
        self.assertEqual(saved["theme"], "ice")
        await ws.close()

    async def test_file(self):
        r = await self.client.get("/file", params={"path": str(self.home / "Pictures/cabin-in-snow.png")})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["Content-Type"], "image/png")
        r2 = await self.client.get("/file", params={"path": str(self.home / "nope.png")})
        self.assertEqual(r2.status, 404)

    async def test_complete(self):
        ws, _ = await self.ws()
        await ws.send_json({"t": "complete", "id": "c1", "text": "open no"})
        got = await self.until(ws, lambda m: m["t"] == "completions")
        self.assertEqual(got[-1], {"t": "completions", "id": "c1", "items": ["notes.txt"]})
        await ws.send_json({"t": "complete", "id": "c2", "text": "cd Doc"})
        got = await self.until(ws, lambda m: m["t"] == "completions")
        self.assertEqual(got[-1]["items"], ["Documents/"])
        await ws.close()

    async def test_confirm_flow(self):
        ws, _ = await self.ws()
        await self.run_text(ws, "del notes.txt", "r1")
        await ws.send_json({"t": "run", "id": "r2", "text": "empty trash"})
        got = await self.until(ws, lambda m: m["t"] == "ask")
        await ws.send_json({"t": "confirm", "id": got[-1]["id"], "yes": True})
        got = await self.until(ws, lambda m: m["t"] == "end" and m["id"] == "r2")
        self.assertIn("trash emptied.", [m.get("text") for m in got])
        await ws.close()

    async def test_yes_opens_suggestion(self):
        ws, _ = await self.ws()
        await self.run_text(ws, "open taxes-2026.pdf", "r1")
        got = await self.run_text(ws, "yes", "r2")
        self.assertEqual([m for m in got if m["t"] == "media"][0]["name"], "taxes-2025.pdf")
        await ws.close()

    async def test_stop(self):
        ws, _ = await self.ws()
        await ws.send_json({"t": "run", "id": "r1", "text": "sleep 20"})
        await self.until(ws, lambda m: m["t"] == "mood" and m["mood"] == "working")
        await ws.send_json({"t": "stop"})
        got = await self.until(ws, lambda m: m["t"] == "end", timeout=3)
        self.assertIn("(stopped)", [m.get("text") for m in got])
        await ws.close()

    async def test_terminal_pane(self):
        ws, _ = await self.ws()
        await ws.send_json({"t": "run", "id": "r1", "text": "python3"})
        got = await self.until(ws, lambda m: m["t"] == "term_open")
        sid = got[-1]["sid"]
        await ws.send_json({"t": "term_in", "sid": sid, "data": "print(6*7)\r"})
        buf = ""
        while "42" not in buf:
            m = await ws.receive_json(timeout=5)
            if m["t"] == "term_out":
                buf += m["data"]
        await ws.send_json({"t": "term_in", "sid": sid, "data": "exit()\r"})
        await self.until(ws, lambda m: m["t"] == "term_exit" and m["sid"] == sid)
        await ws.close()

    async def test_crash_in_action_is_reported(self):
        ws, _ = await self.ws()
        from unittest import mock
        with mock.patch("purrd.actions.a_whoami", side_effect=RuntimeError("boom")), \
                mock.patch.dict("purrd.actions.HANDLERS", {"whoami": mock.AsyncMock(side_effect=RuntimeError("boom"))}):
            got = await self.run_text(ws, "whoami", "r1")
        self.assertIn("something went wrong: boom", [m.get("text") for m in got])
        await ws.close()
