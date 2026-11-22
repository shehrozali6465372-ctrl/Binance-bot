"""Fail-closed tests for the JSONL publication-history integrity gate."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class PersistenceIntegrityTests(unittest.TestCase):
    def _git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
        )

    def _repo(self, root, history=None):
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", "test@example.invalid")
        self._git(root, "config", "user.name", "Test")
        if history is not None:
            (root / "published_posts.jsonl").write_text(history, encoding="utf-8")
            self._git(root, "add", "published_posts.jsonl")
            self._git(root, "commit", "-qm", "seed history")

    def _record(self, symbol):
        return json.dumps({
            "symbol": symbol,
            "timestamp": "2026-11-22T10:00:00+00:00",
            "catalyst": "test", "link": "", "image_url": "",
            "media_id": "", "remote_post_id": "",
        }) + "\n"

    def _in_repo(self, root, path, callback):
        old_cwd = os.getcwd()
        old_path = main._POST_HISTORY_FILE
        try:
            os.chdir(root)
            main._POST_HISTORY_FILE = str(path)
            return callback()
        finally:
            main._POST_HISTORY_FILE = old_path
            os.chdir(old_cwd)

    def test_git_log_nonzero_exit_fails_closed_without_creating_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root, self._record("BTC"))
            target = root / "published_posts.jsonl"
            target.unlink()
            failed = subprocess.CompletedProcess(
                ["git", "log"], 128, stdout=b"", stderr=b"fatal: synthetic git failure",
            )
            real_run = subprocess.run
            def fail_git_log(args, **kwargs):
                if len(args) > 1 and args[1] == "log":
                    return failed
                return real_run(args, **kwargs)
            with patch("subprocess.run", side_effect=fail_git_log):
                result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_git_show_nonzero_exit_fails_closed_without_restoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self._record("BTC")
            self._repo(root, baseline)
            target = root / "published_posts.jsonl"
            target.unlink()
            failed = subprocess.CompletedProcess(
                ["git", "show"], 128, stdout=b"partial", stderr=b"fatal: synthetic show failure",
            )
            real_run = subprocess.run
            def fail_git_show(args, **kwargs):
                if len(args) > 1 and args[1] == "show":
                    return failed
                return real_run(args, **kwargs)
            with patch("subprocess.run", side_effect=fail_git_show):
                result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_git_log_timeout_fails_closed_without_creating_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root, self._record("BTC"))
            target = root / "published_posts.jsonl"
            target.unlink()
            real_run = subprocess.run
            def timeout_git_log(args, **kwargs):
                if len(args) > 1 and args[1] == "log":
                    raise subprocess.TimeoutExpired("git log", 10)
                return real_run(args, **kwargs)
            with patch("subprocess.run", side_effect=timeout_git_log):
                result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_corrupt_nonempty_jsonl_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            target = root / "published_posts.jsonl"
            target.write_text('{"symbol":"BTC"}\nnot-json\n', encoding="utf-8")
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)

    def test_nonempty_history_missing_committed_records_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self._record("BTC") + self._record("ETH")
            self._repo(root, baseline)
            target = root / "published_posts.jsonl"
            target.write_text(self._record("BTC"), encoding="utf-8")
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)

    def test_empty_history_restores_valid_committed_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self._record("BTC") + self._record("ETH")
            self._repo(root, baseline)
            target = root / "published_posts.jsonl"
            target.write_text("", encoding="utf-8")
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertTrue(result)
            self.assertEqual(target.read_text(encoding="utf-8"), baseline)

    def test_workflow_does_not_restore_or_save_publication_history_cache(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "run_bot.yml").read_text(encoding="utf-8")
        self.assertNotIn("actions/cache/restore", workflow)
        self.assertNotIn("actions/cache/save", workflow)
        self.assertNotIn("post-history-", workflow)

    def test_broken_branch_ref_is_not_mistaken_for_a_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            symbolic = self._git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()
            (root / ".git" / "refs" / "heads" / symbolic).write_text("1" * 40 + "\n", encoding="ascii")
            target = root / "published_posts.jsonl"
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertFalse(result)
            self.assertFalse(target.exists())

    def test_valid_local_history_may_extend_committed_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self._record("BTC")
            self._repo(root, baseline)
            target = root / "published_posts.jsonl"
            target.write_text(baseline + self._record("ETH"), encoding="utf-8")
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertTrue(result)

    def test_missing_history_restores_valid_committed_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self._record("BTC")
            self._repo(root, baseline)
            target = root / "published_posts.jsonl"
            target.unlink()
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertTrue(result)
            self.assertEqual(target.read_text(encoding="utf-8"), baseline)

    def test_first_run_in_valid_git_repo_creates_empty_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repo(root)
            target = root / "published_posts.jsonl"
            result = self._in_repo(root, target, main._verify_persistence_integrity)
            self.assertTrue(result)
            self.assertEqual(target.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
