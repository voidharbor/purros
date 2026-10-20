import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

FAKE_OK = """import sys, pathlib, os
name = sys.argv[2]
assert sys.argv[1] == 'base' and sys.argv[3:5] == ['1344', '896'], sys.argv
pathlib.Path(os.environ['PURR_MOCKUP_DIR'], name + '.png').write_bytes(b'\\x89PNG' + ' '.join(sys.argv[6:]).encode())
"""
FAKE_FAIL = """import sys
print('Image generation stopped: A game or hold has priority. Image generation stopped.', file=sys.stderr)
sys.exit(1)
"""


def load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("purr_host", Path(__file__).parent / "purr-host.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PurrHostTest(unittest.TestCase):
    def serve(self, fake):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        script = Path(td.name) / "fake.py"
        script.write_text(fake)
        os.environ["PURR_MOCKUP_CMD"] = f"{sys.executable} {script}"
        os.environ["PURR_MOCKUP_DIR"] = td.name
        mod = load()
        srv = mod.make_server(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def post(self, url, body):
        req = urllib.request.Request(url + "/draw", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=10)

    def test_health_and_bind(self):
        url = self.serve(FAKE_OK)
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        self.assertEqual(json.load(urllib.request.urlopen(url + "/health")), {"ok": True})

    def test_draw_returns_png(self):
        url = self.serve(FAKE_OK)
        r = self.post(url, {"prompt": "a fox", "quality": "careful"})
        self.assertEqual(r.headers["Content-Type"], "image/png")
        self.assertEqual(r.read(), b"\x89PNGa fox --managed")

    def test_quick_uses_fast(self):
        url = self.serve(FAKE_OK)
        r = self.post(url, {"prompt": "a fox", "quality": "quick"})
        self.assertEqual(r.read(), b"\x89PNGa fox --managed --quality fast")

    def test_failure_is_503_with_reason(self):
        url = self.serve(FAKE_FAIL)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(url, {"prompt": "a fox", "quality": "careful"})
        self.assertEqual(cm.exception.code, 503)
        self.assertEqual(cm.exception.read().decode(), "a game is running, so the GPU is busy. try again after.")

    def test_empty_prompt_is_400(self):
        url = self.serve(FAKE_OK)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(url, {"prompt": "  "})
        self.assertEqual(cm.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
