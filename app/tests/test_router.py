import unittest

from purrd.router import Intent, route


def r(text):
    return route(text, on_path=lambda w: w in {"echo", "ls", "cat", "uname", "python3", "git", "nano", "vim", "htop", "which", "who", "time", "top", "find", "free"})


class RouterTest(unittest.TestCase):
    def check(self, text, action, args=None, note=...):
        got = r(text)
        self.assertEqual(got.action, action, f"{text!r} -> {got}")
        if args is not None:
            for k, v in args.items():
                self.assertEqual(got.args.get(k), v, f"{text!r} arg {k} -> {got}")
        if note is not ...:
            self.assertEqual(got.note, note, f"{text!r} note -> {got}")
        return got

    def test_list_plain_words(self):
        for t in ["show all files", "show me my files", "what's in here", "list files", "show files", "ls"]:
            self.check(t, "list", {"path": None}, None)

    def test_list_windows_and_powershell(self):
        self.check("dir", "list", {"path": None}, "dir is the windows way. same list:")
        self.check("gci", "list", {"path": None}, "gci is the powershell way. same list:")
        self.check("Get-ChildItem", "list", {"path": None}, "Get-ChildItem is the powershell way. same list:")

    def test_list_folder(self):
        self.check("ls Documents", "list", {"path": "Documents"}, None)
        self.check("dir Pictures", "list", {"path": "Pictures"})
        self.check("what's in Documents", "list", {"path": "Documents"})

    def test_ls_with_flags_is_real_shell(self):
        self.check("ls -la", "shell", {"cmd": "ls -la"})

    def test_cd(self):
        self.check("cd Documents", "cd", {"path": "Documents"})
        self.check("go to documents", "cd", {"path": "documents"})
        self.check("open folder Music", "cd", {"path": "Music"})
        self.check("cd", "cd", {"path": "~"})
        self.check("cd ..", "cd", {"path": ".."})

    def test_open(self):
        self.check("open cabin", "open", {"path": "cabin"}, None)
        self.check("start notes.txt", "open", {"path": "notes.txt"}, "start is the windows way. same thing here:")
        self.check("play beach-sunset.mp4", "open", {"path": "beach-sunset.mp4"})
        self.check("show me cabin-in-snow.png", "open", {"path": "cabin-in-snow.png"})
        self.check("open My Notes.txt", "open", {"path": "My Notes.txt"})
        self.check("cat notes.txt", "open", {"path": "notes.txt"}, None)
        self.check("type notes.txt", "open", {"path": "notes.txt"}, "type is the windows way. same thing here:")
        self.check("xdg-open cabin", "open", {"path": "cabin"})

    def test_edit(self):
        self.check("edit notes.txt", "edit", {"path": "notes.txt", "editor": "nano"})
        self.check("vim notes.txt", "edit", {"path": "notes.txt", "editor": "vim"})
        self.check("notepad notes.txt", "edit", {"path": "notes.txt", "editor": "nano"}, "notepad is the windows way. opening it in nano:")

    def test_trash(self):
        self.check("del grocery-list.txt", "trash", {"paths": ["grocery-list.txt"]})
        self.check("rm -rf old", "trash", {"paths": ["old"]})
        self.check("Remove-Item x", "trash", {"paths": ["x"]})
        self.check("delete the grocery list", "trash", {"paths": ["grocery list"]})
        self.check("trash x y", "trash", {"paths": ["x", "y"]})
        self.check("empty trash", "empty_trash")
        self.check("empty the trash", "empty_trash")

    def test_copy_move_rename(self):
        self.check("copy a b", "copy", {"src": "a", "dst": "b"})
        self.check("cp a b", "copy", {"src": "a", "dst": "b"})
        self.check("mv a b", "move", {"src": "a", "dst": "b"})
        self.check("move a to b", "move", {"src": "a", "dst": "b"})
        self.check("ren a b", "rename", {"src": "a", "dst": "b"})
        self.check("rename a to b", "rename", {"src": "a", "dst": "b"})

    def test_mkdir_touch(self):
        for t in ["mkdir recipes", "md recipes", "make a folder called recipes", "new folder recipes"]:
            self.check(t, "mkdir", {"path": "recipes"})
        self.check("touch todo.txt", "touch", {"path": "todo.txt"})
        self.check("new file todo.txt", "touch", {"path": "todo.txt"})

    def test_find(self):
        self.check("find cabin", "find", {"query": "cabin"})
        self.check("search for taxes", "find", {"query": "taxes"})
        self.check("where is my resume", "find", {"query": "resume"})

    def test_system_info(self):
        self.check("ipconfig", "network", note="ipconfig is the windows way. here's the network:")
        self.check("ifconfig", "network", note="ifconfig is the mac way. here's the network:")
        self.check("ip a", "network", note=None)
        self.check("what's my ip", "network")
        for t in ["tasklist", "ps", "what's running", "Get-Process"]:
            self.check(t, "processes")
        for t in ["htop", "top", "task manager", "activity monitor"]:
            self.check(t, "top")
        for t in ["systeminfo", "sw_vers", "uname -a", "about this computer"]:
            self.check(t, "sysinfo")
        for t in ["df", "how much space do i have", "disk space"]:
            self.check(t, "disk")
        for t in ["free", "how much memory", "how much ram"]:
            self.check(t, "memory")
        self.check("whoami", "whoami")
        self.check("what time is it", "date")
        self.check("date", "date")
        self.check("pwd", "pwd")
        self.check("where am i", "pwd")

    def test_kill(self):
        self.check("taskkill /IM chrome.exe", "kill", {"target": "chrome.exe"})
        self.check("killall chrome", "kill", {"target": "chrome"})
        self.check("kill 1234", "kill", {"target": "1234"})

    def test_clear_power(self):
        for t in ["cls", "clear", "Clear-Host"]:
            self.check(t, "clear")
        for t in ["shutdown", "turn off", "shutdown /s", "shut down"]:
            self.check(t, "shutdown")
        for t in ["restart", "reboot", "shutdown /r"]:
            self.check(t, "reboot")

    def test_draw(self):
        self.check("draw a cozy cabin in the snow at night", "draw", {"prompt": "a cozy cabin in the snow at night"})
        self.check("make a picture of a fox", "draw", {"prompt": "a fox"})
        self.check("paint a lighthouse", "draw", {"prompt": "a lighthouse"})
        self.check("generate an image of a red barn", "draw", {"prompt": "a red barn"})

    def test_purros_words(self):
        self.check("theme amber", "theme", {"value": "amber"})
        self.check("glow more", "glow", {"value": "more"})
        self.check("font clean", "font", {"value": "clean"})
        self.check("settings", "settings")
        for t in ["help", "?", "what can you do"]:
            self.check(t, "help")
        self.check("history", "history")

    def test_shell_and_brain(self):
        self.check("echo hi", "shell", {"cmd": "echo hi"})
        self.check("git status", "shell", {"cmd": "git status"})
        self.check("how do I compress a folder", "brain", {"text": "how do I compress a folder"})
        self.check("tell me a joke", "brain")

    def test_sentences_starting_with_command_names_go_to_brain(self):
        for t in ["which folder is taking up the most space", "who made this computer", "time to clean up my files",
                  "top 10 biggest files please", "find out why my computer is slow today", "free up some space for me"]:
            self.check(t, "brain", {"text": t})

    def test_short_commands_with_english_names_stay_commands(self):
        self.check("which python3", "shell", {"cmd": "which python3"})
        self.check("top", "top")
        self.check("time", "date")
        self.check("find cabin", "find", {"query": "cabin"})

    def test_refuse_disk_wipers(self):
        for t in ["format c:", "diskpart", "fdisk /dev/vda"]:
            got = self.check(t, "refuse")
            self.assertEqual(got.args["text"], "format wipes a whole disk. I won't do that from here.")

    def test_name(self):
        self.check("call me sam", "name", {"value": "sam"})
        self.check("my name is Josh", "name", {"value": "Josh"})

    def test_pipes_go_to_shell(self):
        self.check("ls | wc -l", "shell", {"cmd": "ls | wc -l"})
        self.check("cat notes.txt | grep mom", "shell")

    def test_empty(self):
        self.check("   ", "noop")


if __name__ == "__main__":
    unittest.main()
