import unittest

from purrd.safety import classify


class SafetyTest(unittest.TestCase):
    def test_read_only(self):
        for c in ["ls -la", "cat x", "grep -r a .", "df -h", "ps aux", "find . -name x", "du -sh *", "head -n 3 notes.txt", "ls | wc -l"]:
            self.assertEqual(classify(c), "read", c)

    def test_change(self):
        for c in ["mv a b", "echo hi > f", "apk add htop", "touch x", "cp a b", "python3 -c 'import os'", "find . -exec touch {} ;"]:
            self.assertEqual(classify(c), "change", c)

    def test_danger(self):
        for c in ["rm -rf ~", "rm x", "dd if=x of=/dev/vda", "mkfs.ext4 /dev/vda1", "shutdown now", "doas rm x",
                  "sudo apk add x", "chmod -R 777 /", ":(){ :|:& };:", "ls && rm -rf /", "reboot", "poweroff", "kill -9 1"]:
            self.assertEqual(classify(c), "danger", c)


    def test_bypass_shapes_are_danger(self):
        for c in ["echo $(rm Documents/victim.txt)", "ls `rm -rf ~`", "env rm -rf ~", "env X=1 rm -rf ~",
                  "find Documents -name v2.txt -delete", "find . -delete", "find . -exec rm -rf {} \\;", "find . -execdir rm {} +",
                  "ls | xargs rm -rf", "xargs -0 rm < list", "bash -c 'rm -rf ~'", "sh -c \"rm x\"", "nice rm -rf ~",
                  "nice -n 5 rm x", "timeout 5 rm -rf ~", "eval rm -rf ~", "command rm x", "nohup rm x", "time rm x",
                  "echo $(echo $(rm x))", "cat <(rm x)"]:
            self.assertEqual(classify(c), "danger", c)

    def test_substitution_is_never_read(self):
        self.assertEqual(classify("echo $(date)"), "change")
        self.assertEqual(classify("echo `date`"), "change")


if __name__ == "__main__":
    unittest.main()
