import asyncio
import time
import unittest
from pathlib import Path

from purrd.shell import Pty, is_interactive, run


class RunTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, cmd, **kw):
        out = []

        async def on_out(t):
            out.append(t)
        code = await run(cmd, Path("/tmp"), on_out, **kw)
        return code, "".join(out)

    async def test_merges_stdout_and_stderr(self):
        code, out = await self.collect("echo hi; echo err >&2")
        self.assertEqual(code, 0)
        self.assertEqual(out, "hi\nerr\n")

    async def test_timeout_stops(self):
        t0 = time.monotonic()
        code, out = await self.collect("sleep 5", timeout=0.5)
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertNotEqual(code, 0)
        self.assertTrue(out.rstrip().endswith("(stopped after 0.5 s)"), out)

    async def test_flood_is_cut(self):
        code, out = await self.collect("yes", max_bytes=1000)
        self.assertTrue(out.rstrip().endswith("(output cut)"), out[-60:])
        self.assertLess(len(out), 1200)

    async def test_cancel_kills_process_group(self):
        task = asyncio.create_task(self.collect("sleep 30 & sleep 30; wait"))
        await asyncio.sleep(0.3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task


class InteractiveTest(unittest.TestCase):
    def test_interactive(self):
        for c in ["nano x", "vim", "htop", "top", "less f", "python3", "man ls", "bash", "ssh host"]:
            self.assertTrue(is_interactive(c), c)
        for c in ["python3 script.py", "ls", "echo hi", "bash -c 'echo'"]:
            self.assertFalse(is_interactive(c), c)


class PtyTest(unittest.IsolatedAsyncioTestCase):
    async def test_echo_and_exit(self):
        got, done = [], asyncio.Event()
        p = Pty(["cat"], Path("/tmp"), 80, 24, on_data=got.append, on_exit=lambda code: done.set())
        p.start()
        p.write("meow\n")
        for _ in range(50):
            if "meow" in "".join(got):
                break
            await asyncio.sleep(0.05)
        self.assertIn("meow", "".join(got))
        p.resize(100, 30)
        p.close()
        await asyncio.wait_for(done.wait(), 3)
