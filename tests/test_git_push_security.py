"""Security regressions for authenticated Git history pushes."""
import base64
import os
import subprocess
import unittest
from unittest.mock import patch

import main


class GitPushSecurityTests(unittest.TestCase):
    def test_push_uses_ephemeral_git_auth_without_mutating_remote_url(self):
        token = "test-secret-token-value"
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/test-branch\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "commit"] or command[:4] == ["git", "-c", "user.name=bot", "-c"]:
                return subprocess.CompletedProcess(command, 0, stdout=b"[feature/test-branch] saved\n", stderr=b"")
            if command[:2] == ["git", "push"]:
                return subprocess.CompletedProcess(command, 0, stdout=b"pushed\n", stderr=b"")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        with patch.dict(os.environ, {
            "GH_TOKEN": token,
            "GITHUB_REPOSITORY": "owner/repository",
            "GIT_CONFIG_COUNT": "0",
        }, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertTrue(main._try_git_push(max_retries=1))

        commands = [call[0] for call in calls]
        self.assertFalse(any(command[:3] == ["git", "remote", "set-url"] for command in commands))
        push_call = next(kwargs for command, kwargs in calls if command[:2] == ["git", "push"])
        git_env = push_call["env"]
        expected_header = "AUTHORIZATION: basic " + base64.b64encode(
            f"x-access-token:{token}".encode("utf-8")
        ).decode("ascii")
        self.assertEqual(git_env["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(git_env["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
        self.assertEqual(git_env["GIT_CONFIG_VALUE_0"], expected_header)
        self.assertNotIn(token, repr(commands))

    def test_missing_token_skips_git_without_running_subprocess(self):
        with patch.dict(os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": "", "GITHUB_REPOSITORY": "owner/repository"}, clear=False), patch("subprocess.run") as run:
            self.assertFalse(main._try_git_push(max_retries=1))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
