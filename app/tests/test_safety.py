import unittest

from purrd.safety import classify


class SafetyTest(unittest.TestCase):
    def test_read_only(self):
        for c in ["ls -la", "cat x", "grep -r a .", "df -h", "ps aux", "find . -name x", "du -sh *", "head -n 3 notes.txt", "ls | wc -l"]:
            self.assertEqual(classify(c), "read", c)

    def test_change(self):
        for c in ["find . -delete", "mv a b", "echo hi > f", "apk add htop", "touch x", "cp a b", "find . -exec rm {} ;"]:
            self.assertEqual(classify(c), "change", c)

    def test_danger(self):
        for c in ["rm -rf ~", "rm x", "dd if=x of=/dev/vda", "mkfs.ext4 /dev/vda1", "shutdown now", "doas rm x",
                  "sudo apk add x", "chmod -R 777 /", ":(){ :|:& };:", "ls && rm -rf /", "reboot", "poweroff", "kill -9 1"]:
            self.assertEqual(classify(c), "danger", c)


if __name__ == "__main__":
    unittest.main()
