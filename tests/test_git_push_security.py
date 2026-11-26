"""Security regressions for authenticated Git history pushes."""
import base64
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
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
            "GITHUB_ACTIONS": "false",
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
        commit_command = next(command for command in commands if "commit" in command)
        self.assertIn("--", commit_command)
        self.assertIn(main._POST_HISTORY_FILE, commit_command)
        self.assertIn("posts/", commit_command)

    def test_main_branch_is_never_committed_or_pushed(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="main", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="abc1234", stderr="")

        with patch.dict(os.environ, {
            "GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository",
        }, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any(command[:2] in (["git", "add"], ["git", "push"]) for command in calls))
        self.assertFalse(any("commit" in command for command in calls))

    def test_detached_head_is_never_committed_or_pushed(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="HEAD", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="abc1234", stderr="")

        with patch.dict(os.environ, {
            "GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository",
        }, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any(command[:2] in (["git", "add"], ["git", "push"]) for command in calls))
        self.assertFalse(any("commit" in command for command in calls))

    def test_missing_token_skips_git_without_running_subprocess(self):
        with patch.dict(os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": "", "GITHUB_REPOSITORY": "owner/repository"}, clear=False), patch("subprocess.run") as run:
            self.assertFalse(main._try_git_push(max_retries=1))
            run.assert_not_called()


    def test_short_sha_failure_aborts_before_staging(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/test\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="bad revision")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        with patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository"}), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any(command[:2] == ["git", "add"] for command in calls))
        self.assertFalse(any("commit" in command for command in calls))

    def test_first_git_add_failure_aborts_without_commit_or_push(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/test\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "add"]:
                return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"index locked")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        with patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository"}), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any("commit" in command for command in calls))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in calls))

    def test_second_git_add_failure_aborts_without_commit_or_push(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/test\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "add"] and command[-1] == "posts/":
                return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"pathspec error")
            if command[:2] == ["git", "add"]:
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        with patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository"}), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any("commit" in command for command in calls))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in calls))

    def test_pending_push_status_failure_is_not_treated_as_clean(self):
        with patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repository"}), patch.object(main.Path, "exists", return_value=True), patch("subprocess.run", return_value=subprocess.CompletedProcess(["git", "status"], 128, stdout=b"", stderr=b"fatal")):
            self.assertFalse(main._retry_pending_push())


    def test_github_actions_push_requires_explicit_exact_ref_allowlist(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/approved\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "commit"] or "commit" in command:
                return subprocess.CompletedProcess(command, 0, stdout=b"saved\n", stderr=b"")
            if command[:2] == ["git", "push"]:
                return subprocess.CompletedProcess(command, 0, stdout=b"pushed\n", stderr=b"")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        env = {
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/feature/approved",
            "GIT_HISTORY_ALLOWED_REFS": "refs/heads/feature/approved",
        }
        with patch.dict(os.environ, env, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertTrue(main._try_git_push(max_retries=1))

        push_command = next(command for command in calls if command[:2] == ["git", "push"])
        self.assertEqual(push_command[-1], "HEAD:feature/approved")

    def test_github_actions_push_fails_closed_without_allowlisted_ref(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/approved\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        env = {
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/feature/approved",
            "GIT_HISTORY_ALLOWED_REFS": "",
        }
        with patch.dict(os.environ, env, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any(command[:2] in (["git", "add"], ["git", "push"]) for command in calls))
        self.assertFalse(any("commit" in command for command in calls))

    def test_github_actions_push_rejects_checkout_ref_mismatch(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/other\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        env = {
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repository",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/feature/approved",
            "GIT_HISTORY_ALLOWED_REFS": "refs/heads/feature/approved",
        }
        with patch.dict(os.environ, env, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))

        self.assertFalse(any(command[:2] in (["git", "add"], ["git", "push"]) for command in calls))
        self.assertFalse(any("commit" in command for command in calls))


    def _make_temporary_git_remote(self, *, upstream=True):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        remote = root / "origin.git"
        work = root / "work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "feature/history", str(work)], check=True, capture_output=True)
        def git(*args, cwd=work):
            return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.invalid")
        (work / main._POST_HISTORY_FILE).write_text('{"symbol":"BTC","timestamp":"2026-11-24T00:00:00Z"}\n')
        (work / "posts").mkdir()
        (work / "posts" / ".gitkeep").write_text("")
        git("add", main._POST_HISTORY_FILE, "posts/.gitkeep")
        git("commit", "-m", "initial history")
        git("--git-dir", str(remote), "fetch", str(work), "HEAD:refs/heads/feature/history", cwd=root)
        git("remote", "add", "origin", str(remote))
        git("fetch", "origin")
        git("branch", "--set-upstream-to", "origin/feature/history")
        if not upstream:
            git("branch", "--unset-upstream")
        return temp, work, remote, git

    def test_retry_pushes_clean_worktree_when_history_commit_is_ahead_of_origin(self):
        temp, work, remote, git = self._make_temporary_git_remote()
        previous = os.getcwd()
        try:
            (work / main._POST_HISTORY_FILE).write_text(
                (work / main._POST_HISTORY_FILE).read_text() + '{"symbol":"ETH","timestamp":"2026-11-24T00:01:00Z"}\n'
            )
            git("add", main._POST_HISTORY_FILE)
            git("commit", "-m", "history commit whose push failed")
            local_head = git("rev-parse", "HEAD").stdout.strip()
            os.chdir(work)
            real_run = subprocess.run
            def fake_run(command, **kwargs):
                if command[:2] == ["git", "push"]:
                    real_run(["git", "--git-dir", str(remote), "fetch", str(work), "HEAD:refs/heads/feature/history"], check=True, capture_output=True, text=True)
                    return subprocess.CompletedProcess(command, 0, stdout=b"simulated local bare remote update", stderr=b"")
                return real_run(command, **kwargs)
            with patch.dict(os.environ, {"GH_TOKEN":"test-token", "GITHUB_TOKEN":"", "GITHUB_REPOSITORY":"owner/repository", "GITHUB_ACTIONS":"false"}, clear=False), patch.object(main, "_POST_HISTORY_FILE", "published_posts.jsonl"), patch("subprocess.run", side_effect=fake_run):
                self.assertTrue(main._retry_pending_push())
            remote_head = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/feature/history"], check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(remote_head, local_head)
        finally:
            os.chdir(previous)
            temp.cleanup()

    def test_retry_refuses_clean_ahead_commit_that_changes_unrelated_file(self):
        temp, work, remote, git = self._make_temporary_git_remote()
        previous = os.getcwd()
        try:
            (work / "application.py").write_text("unrelated change\n")
            git("add", "application.py")
            git("commit", "-m", "unrelated code change")
            local_head = git("rev-parse", "HEAD").stdout.strip()
            os.chdir(work)
            with patch.dict(os.environ, {"GH_TOKEN":"test-token", "GITHUB_TOKEN":"", "GITHUB_REPOSITORY":"owner/repository"}, clear=False):
                self.assertFalse(main._retry_pending_push())
            remote_head = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "refs/heads/feature/history"], check=True, capture_output=True, text=True).stdout.strip()
            self.assertNotEqual(remote_head, local_head)
        finally:
            os.chdir(previous)
            temp.cleanup()

    def test_retry_refuses_when_exact_upstream_is_missing(self):
        temp, work, remote, git = self._make_temporary_git_remote(upstream=False)
        previous = os.getcwd()
        try:
            (work / main._POST_HISTORY_FILE).write_text(
                (work / main._POST_HISTORY_FILE).read_text() + '{"symbol":"ETH","timestamp":"2026-11-24T00:01:00Z"}\n'
            )
            git("add", main._POST_HISTORY_FILE)
            git("commit", "-m", "history commit")
            os.chdir(work)
            with patch.dict(os.environ, {"GH_TOKEN":"test-token", "GITHUB_TOKEN":"", "GITHUB_REPOSITORY":"owner/repository"}, clear=False):
                self.assertFalse(main._retry_pending_push())
        finally:
            os.chdir(previous)
            temp.cleanup()

    def test_retry_refuses_upstream_branch_mismatch(self):
        temp, work, remote, git = self._make_temporary_git_remote()
        previous = os.getcwd()
        try:
            local_head = git("rev-parse", "HEAD").stdout.strip()
            subprocess.run(["git", "--git-dir", str(remote), "update-ref", "refs/heads/other", local_head], check=True, capture_output=True, text=True)
            git("fetch", "origin")
            git("branch", "--set-upstream-to", "origin/other")
            with (work / main._POST_HISTORY_FILE).open("a") as handle:
                handle.write('{"symbol":"ETH","timestamp":"2026-11-24T00:01:00Z"}\n')
            os.chdir(work)
            with patch.dict(os.environ, {"GH_TOKEN":"test-token", "GITHUB_TOKEN":"", "GITHUB_REPOSITORY":"owner/repository"}, clear=False):
                self.assertFalse(main._retry_pending_push())
        finally:
            os.chdir(previous)
            temp.cleanup()


    def test_no_commit_is_not_reported_as_success_outside_verified_recovery(self):
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return subprocess.CompletedProcess(command, 0, stdout="feature/test\n", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(command, 0, stdout="abc1234\n", stderr="")
            if "commit" in command:
                return subprocess.CompletedProcess(command, 1, stdout=b"nothing to commit, working tree clean", stderr=b"")
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
        with patch.dict(os.environ, {"GH_TOKEN":"test-token", "GITHUB_REPOSITORY":"owner/repository"}, clear=False), patch("subprocess.run", side_effect=fake_run):
            self.assertFalse(main._try_git_push(max_retries=1))
        self.assertFalse(any(command[:2] == ["git", "push"] for command in calls))



if __name__ == "__main__":
    unittest.main()
