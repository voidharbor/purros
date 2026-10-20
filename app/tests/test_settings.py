import tempfile
import unittest
from pathlib import Path

from purrd import settings


class SettingsTest(unittest.TestCase):
    def test_defaults(self):
        d = settings.DEFAULTS
        self.assertEqual((d["theme"], d["glow"], d["font"], d["nap_seconds"]), ("phosphor", "light", "pixel", 45))
        self.assertEqual(d["brain"], {"kind": "ollama", "url": "http://10.0.2.2:11434", "model": "jarvis-ornith-ctx131072", "key": ""})
        self.assertEqual(d["pictures"], {"kind": "purr-host", "url": "http://10.0.2.2:7790", "quality": "careful", "model": "", "key": ""})

    def test_patch(self):
        got = settings.patch(settings.DEFAULTS, {"theme": "amber", "brain": {"model": "x"}})
        self.assertEqual(got["theme"], "amber")
        self.assertEqual(got["brain"]["model"], "x")
        self.assertEqual(got["brain"]["kind"], "ollama")
        self.assertEqual(settings.DEFAULTS["theme"], "phosphor")

    def test_patch_rejects(self):
        for bad in [{"theme": "pink"}, {"glow": "max"}, {"font": "comic"}, {"brain": {"kind": "magic"}}, {"pictures": {"quality": "ultra"}}]:
            with self.assertRaises(ValueError, msg=bad):
                settings.patch(settings.DEFAULTS, bad)

    def test_load_save_roundtrip_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c" / "settings.json"
            self.assertEqual(settings.load(p), settings.DEFAULTS)
            settings.save(p, settings.patch(settings.DEFAULTS, {"name": "josh", "glow": "more"}))
            got = settings.load(p)
            self.assertEqual((got["name"], got["glow"], got["theme"]), ("josh", "more", "phosphor"))

    def test_load_corrupt_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            p.write_text("{nope")
            self.assertEqual(settings.load(p), settings.DEFAULTS)
