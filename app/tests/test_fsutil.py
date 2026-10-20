import unittest

from helpers import make_home
from purrd import fsutil


class FsutilTest(unittest.TestCase):
    def setUp(self):
        self.td, self.home = make_home()

    def tearDown(self):
        self.td.cleanup()

    def test_find_by_stem_prefix_any_case(self):
        self.assertEqual(fsutil.find("CABIN", self.home, self.home), self.home / "Pictures" / "cabin-in-snow.png")

    def test_find_folder(self):
        self.assertEqual(fsutil.find("documents", self.home, self.home), self.home / "Documents")

    def test_find_tilde_and_absolute(self):
        self.assertEqual(fsutil.find("~/notes.txt", self.home / "Music", self.home), self.home / "notes.txt")
        p = self.home / "Documents" / "resume.docx"
        self.assertEqual(fsutil.find(str(p), self.home, self.home), p)

    def test_find_prefers_cwd(self):
        self.assertEqual(fsutil.find("beach-sunset.mp4", self.home / "Videos", self.home), self.home / "Videos" / "beach-sunset.mp4")

    def test_find_with_spaces(self):
        (self.home / "Documents" / "My Notes.txt").write_text("x")
        self.assertEqual(fsutil.find("my notes", self.home, self.home), self.home / "Documents" / "My Notes.txt")

    def test_find_missing(self):
        self.assertIsNone(fsutil.find("nothing", self.home, self.home))

    def test_suggest_close_name(self):
        self.assertEqual(fsutil.suggest("taxes-2026.pdf", self.home), self.home / "Documents" / "taxes-2025.pdf")

    def test_suggest_nothing_close(self):
        self.assertIsNone(fsutil.suggest("zzzzqqq", self.home))

    def test_kind(self):
        k = fsutil.kind
        self.assertEqual(k(self.home / "Pictures"), "dir")
        for n, want in [("a.PNG", "image"), ("a.jpg", "image"), ("a.webp", "image"), ("a.gif", "image"),
                        ("a.mp4", "video"), ("a.webm", "video"), ("a.mkv", "video"), ("a.mov", "video"),
                        ("a.mp3", "audio"), ("a.ogg", "audio"), ("a.wav", "audio"), ("a.flac", "audio"), ("a.m4a", "audio"),
                        ("a.pdf", "pdf"), ("a.txt", "text"), ("a.md", "text"), ("a.py", "text"), ("a.json", "text"),
                        ("a.csv", "text"), ("a.log", "text"), ("a.sh", "text"), ("a.docx", "other")]:
            self.assertEqual(k(self.home / n), want, n)

    def test_kind_text_without_extension(self):
        p = self.home / "README"
        p.write_text("hello\n")
        self.assertEqual(fsutil.kind(p), "text")
        b = self.home / "blob"
        b.write_bytes(b"\x00\x01\x02\xff")
        self.assertEqual(fsutil.kind(b), "other")

    def test_listdir_folders_first_hidden_skipped(self):
        names = [i["name"] for i in fsutil.listdir(self.home)]
        self.assertEqual(names, ["Documents", "Downloads", "Music", "Pictures", "Videos", "beach-sunset.mp4", "grocery-list.txt", "notes.txt"])
        item = fsutil.listdir(self.home)[0]
        self.assertEqual(item, {"name": "Documents", "dir": True, "kind": "dir", "path": str(self.home / "Documents")})

    def test_listdir_show_all(self):
        self.assertIn(".hidden", [i["name"] for i in fsutil.listdir(self.home, show_all=True)])

    def test_pretty(self):
        self.assertEqual(fsutil.pretty(self.home / "Documents" / "x", self.home), "~/Documents/x")
        self.assertEqual(fsutil.pretty(self.home, self.home), "~")
        self.assertEqual(fsutil.pretty(fsutil.Path("/etc/hosts"), self.home), "/etc/hosts")


if __name__ == "__main__":
    unittest.main()
