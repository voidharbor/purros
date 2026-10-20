import unittest
from unittest import mock

from helpers import make_home
from purrd import actions, brain, pictures
from purrd.actions import Ctx
from purrd.router import Intent, route


class Rec:
    """A Ctx with recording callbacks."""

    def __init__(self, home, answer=True):
        self.msgs, self.asked, self.terms = [], [], []

        async def emit(m):
            self.msgs.append(m)

        async def confirm(q, cmd):
            self.asked.append((q, cmd))
            return answer

        async def open_term(argv, title):
            self.terms.append((argv, title))
        self.ctx = Ctx(home=home, emit=emit, confirm=confirm, open_term=open_term, settings_path=home / ".config/purros/settings.json")

    def of(self, t):
        return [m for m in self.msgs if m["t"] == t]

    def lines(self):
        return [m["text"] for m in self.of("line")]

    def moods(self):
        return [m["mood"] for m in self.of("mood")]


class ActionsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.td, self.home = make_home()
        self.rec = Rec(self.home)

    def tearDown(self):
        self.td.cleanup()

    async def do(self, text, rec=None):
        rec = rec or self.rec
        await actions.do(route(text), rec.ctx)
        return rec

    async def test_list_home(self):
        r = await self.do("show all files")
        self.assertEqual(r.msgs[0], {"t": "mood", "mood": "searching", "word": "looking"})
        self.assertIn({"t": "line", "text": "ran: ls ~", "cls": "ran"}, r.msgs)
        lst = r.of("list")[0]
        self.assertEqual([i["name"] for i in lst["items"]][:2], ["Documents", "Downloads"])
        self.assertEqual(lst["summary"], "8 things in your home folder. click one to open it.")
        self.assertEqual(r.moods()[-1], "idle")

    async def test_list_folder_counts(self):
        r = await self.do("ls Pictures")
        self.assertEqual(r.of("list")[0]["summary"], "1 thing in Pictures.")
        r2 = await self.do("ls Downloads", Rec(self.home))
        self.assertEqual(r2.of("list")[0]["summary"], "Downloads is empty.")

    async def test_dir_note_before_list(self):
        r = await self.do("dir")
        i_note = r.msgs.index({"t": "line", "text": "dir is the windows way. same list:", "cls": "ran"})
        i_list = next(i for i, m in enumerate(r.msgs) if m["t"] == "list")
        self.assertLess(i_note, i_list)

    async def test_open_missing_suggests(self):
        r = await self.do("open taxes-2026.pdf")
        self.assertIn("oops", r.moods())
        self.assertIn("I can't find taxes-2026.pdf. There's a taxes-2025.pdf in Documents. Want that one?", r.lines())
        self.assertEqual(r.ctx.pending, "open " + str(self.home / "Documents" / "taxes-2025.pdf"))

    async def test_open_missing_no_suggestion(self):
        r = await self.do("open zzqqxx")
        self.assertIn("I can't find zzqqxx.", r.lines())

    async def test_open_image(self):
        r = await self.do("open cabin")
        m = r.of("media")[0]
        p = str(self.home / "Pictures" / "cabin-in-snow.png")
        self.assertEqual((m["kind"], m["name"], m["path"]), ("image", "cabin-in-snow.png", p))
        self.assertTrue(m["url"].startswith("/file?path=") and "cabin-in-snow.png" in m["url"])

    async def test_open_video_sets_playing(self):
        r = await self.do("play beach-sunset.mp4")
        self.assertEqual(r.of("media")[0]["kind"], "video")
        self.assertEqual(r.moods()[-1], "playing")

    async def test_open_folder_is_cd_and_list(self):
        r = await self.do("open Documents")
        self.assertEqual(r.ctx.cwd, self.home / "Documents")
        self.assertEqual(r.of("cwd")[0]["cwd"], "~/Documents")
        self.assertEqual(len(r.of("list")), 1)

    async def test_open_text(self):
        r = await self.do("cat notes.txt")
        t = r.of("text")[0]
        self.assertEqual(t["name"], "notes.txt")
        self.assertEqual(t["lines"], ["call mom sunday", "fix the porch light", "try the new ramen place"])

    async def test_trash(self):
        r = await self.do("del grocery-list.txt")
        self.assertFalse((self.home / "grocery-list.txt").exists())
        self.assertTrue((self.home / ".local/share/Trash/files/grocery-list.txt").exists())
        self.assertIn("moved grocery-list.txt to the trash. 'empty trash' deletes it for good.", r.lines())
        self.assertEqual(r.asked, [])

    async def test_trash_home_refused(self):
        r = await self.do("rm -rf ~")
        self.assertTrue(self.home.exists() and (self.home / "notes.txt").exists())
        self.assertIn("that's your whole home folder. I won't trash that.", r.lines())

    async def test_trash_outside_home_refused(self):
        r = await self.do("rm /etc/hosts")
        self.assertIn("that's outside your home folder. I only trash your own stuff.", r.lines())

    async def test_trash_glob(self):
        r = await self.do("del *.txt")
        self.assertFalse((self.home / "notes.txt").exists())
        self.assertFalse((self.home / "grocery-list.txt").exists())
        self.assertIn("moved 2 things to the trash. 'empty trash' deletes them for good.", r.lines())

    async def test_empty_trash_asks(self):
        await self.do("del notes.txt")
        no = Rec(self.home, answer=False)
        await self.do("empty trash", no)
        self.assertTrue((self.home / ".local/share/Trash/files/notes.txt").exists())
        self.assertEqual(len(no.asked), 1)
        yes = Rec(self.home, answer=True)
        await self.do("empty trash", yes)
        self.assertFalse((self.home / ".local/share/Trash/files/notes.txt").exists())
        self.assertIn("trash emptied.", yes.lines())

    async def test_danger_shell_asks_and_respects_no(self):
        no = Rec(self.home, answer=False)
        with mock.patch("purrd.actions.shell.run") as run:
            await actions.do(Intent("shell", {"cmd": "dd if=/dev/zero of=x bs=1 count=1"}), no.ctx)
        run.assert_not_called()
        self.assertEqual(no.asked[0][1], "dd if=/dev/zero of=x bs=1 count=1")

    async def test_shell_streams_output(self):
        r = await self.do("echo meow")
        self.assertEqual("".join(m["text"] for m in r.of("out")), "meow\n")

    async def test_interactive_shell_opens_term(self):
        await actions.do(Intent("shell", {"cmd": "python3"}), self.rec.ctx)
        self.assertEqual(self.rec.terms[0][0], ["bash", "-lc", "python3"])

    async def test_edit_opens_nano(self):
        await self.do("notepad notes.txt")
        self.assertEqual(self.rec.terms[0][0], ["nano", str(self.home / "notes.txt")])
        self.assertIn("notepad is the windows way. opening it in nano:", self.rec.lines())

    async def test_brain_down(self):
        with mock.patch("purrd.actions.brain.ask", side_effect=brain.BrainDown("refused")):
            r = await self.do("tell me a joke")
        self.assertIn("oops", r.moods())
        self.assertIn("my brain is napping right now (a game may be running). plain commands still work.", r.lines())

    async def test_brain_read_command_runs(self):
        with mock.patch("purrd.actions.brain.ask", return_value={"say": "here's the date.", "run": "echo 2026", "draw": None}):
            r = await self.do("what year is it in a weird way")
        self.assertEqual(r.asked, [])
        self.assertIn("here's the date.", r.lines())
        self.assertIn("ran: echo 2026", r.lines())
        self.assertEqual("".join(m["text"] for m in r.of("out")), "2026\n")

    async def test_brain_change_command_asks(self):
        no = Rec(self.home, answer=False)
        with mock.patch("purrd.actions.brain.ask", return_value={"say": "zipping it.", "run": "tar czf d.tgz Documents", "draw": None}):
            await self.do("compress documents", no)
        self.assertEqual(no.asked[0][1], "tar czf d.tgz Documents")
        self.assertFalse((self.home / "d.tgz").exists())
        self.assertIn("ok, left it alone.", no.lines())

    async def test_brain_trash_goes_through_phrasebook(self):
        with mock.patch("purrd.actions.brain.ask", return_value={"say": "tossing it.", "run": "trash grocery-list.txt", "draw": None}):
            await self.do("get that shopping thing out of here")
        self.assertTrue((self.home / ".local/share/Trash/files/grocery-list.txt").exists())

    async def test_cd_and_pwd(self):
        r = await self.do("cd Documents")
        self.assertEqual(r.ctx.cwd, self.home / "Documents")
        await self.do("cd ..")
        self.assertEqual(r.ctx.cwd, self.home)
        await self.do("cd nowhere-real")
        self.assertEqual(r.ctx.cwd, self.home)

    async def test_mkdir_and_touch(self):
        await self.do("make a folder called recipes")
        self.assertTrue((self.home / "recipes").is_dir())
        await self.do("touch todo.txt")
        self.assertTrue((self.home / "todo.txt").is_file())

    async def test_copy_move_rename(self):
        await self.do("copy notes.txt Documents")
        self.assertTrue((self.home / "Documents/notes.txt").exists())
        await self.do("rename grocery-list.txt to shopping.txt")
        self.assertTrue((self.home / "shopping.txt").exists())
        await self.do("move shopping.txt to Documents")
        self.assertTrue((self.home / "Documents/shopping.txt").exists())

    async def test_find(self):
        r = await self.do("find cabin")
        self.assertEqual([i["name"] for i in r.of("list")[0]["items"]], ["Pictures/cabin-in-snow.png"])

    async def test_draw(self):
        with mock.patch("purrd.actions.pictures.draw", return_value=b"\x89PNG"):
            r = await self.do("draw a cozy cabin in the snow at night")
        self.assertEqual(r.moods()[0], "drawing")
        self.assertEqual(r.of("media")[0]["kind"], "image")
        self.assertEqual(r.moods()[-1], "done")
        self.assertIn("saved to Pictures/a-cozy-cabin-in-the.png", r.lines())
        self.assertTrue((self.home / "Pictures/a-cozy-cabin-in-the.png").exists())

    async def test_draw_down(self):
        with mock.patch("purrd.actions.pictures.draw", side_effect=pictures.PicturesDown("a game is running")):
            r = await self.do("draw a fox")
        self.assertEqual(r.moods()[-1], "oops")
        self.assertIn("I couldn't draw that right now: a game is running", r.lines())

    async def test_theme_saves(self):
        r = await self.do("theme amber")
        self.assertEqual(r.ctx.settings["theme"], "amber")
        self.assertEqual(r.of("settings")[0]["settings"]["theme"], "amber")
        self.assertIn('"amber"', (self.home / ".config/purros/settings.json").read_text())
        r2 = await self.do("theme pink", Rec(self.home))
        self.assertIn("oops", r2.moods())

    async def test_kill_protects_purros(self):
        r = await self.do("killall chromium")
        self.assertIn("that would close PurrOS itself. I'll leave it running.", r.lines())
        self.assertEqual(r.asked, [])

    async def test_refuse(self):
        r = await self.do("format c:")
        self.assertIn("format wipes a whole disk. I won't do that from here.", r.lines())


class WordingTest(unittest.TestCase):
    def test_no_touch_words_on_a_computer(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        for f in list((root / "purrd").glob("*.py")) + [root / "static/purr.js", root / "static/index.html"]:
            self.assertIsNone(re.search(r"\btap", f.read_text(), re.I), f"{f.name} says tap; PurrOS is a computer, say click")
