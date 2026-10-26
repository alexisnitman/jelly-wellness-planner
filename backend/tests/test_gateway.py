"""Gateway rules from CLAUDE.md: model allowlist, kill switch, spend cap, input limit, privacy of usage records.

Run from backend/:   ../.venv/bin/python -m unittest discover -s tests -v
No network and no model calls.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402

_TMP = tempfile.TemporaryDirectory()
store.DATA_DIR = Path(_TMP.name)  # never touch the real usage database in tests
store.DB_PATH = Path(_TMP.name) / "test.db"
store.init()

from lib import llm  # noqa: E402


def call(prompt="hi"):
    return asyncio.run(llm.run_agent(None, prompt, feature="test"))  # type: ignore[arg-type]


class GatewayRules(unittest.TestCase):
    def test_only_gpt_6_luna_is_allowed(self):
        llm.assert_model("gpt-6-luna")
        for other in ("gpt-5", "gpt-6-astra", "claude-sonnet-5-5", ""):
            with self.assertRaises(ValueError):
                llm.assert_model(other)
        self.assertEqual(llm.ALLOWED_MODELS, frozenset({"gpt-6-luna"}))

    def test_kill_switch_blocks_calls(self):
        os.environ["AI_ENABLED"] = "false"
        try:
            with self.assertRaises(llm.AIUnavailable):
                call()
        finally:
            os.environ.pop("AI_ENABLED", None)

    def test_daily_cap_blocks_calls(self):
        store.record_usage("test", 1, 1, 0, llm.LIMITS.daily_cap_usd + 0.01)
        try:
            with self.assertRaises(llm.AIUnavailable):
                call()
        finally:
            with store.connect() as conn:
                conn.execute("DELETE FROM ai_usage")

    def test_oversize_input_is_refused(self):
        with self.assertRaises(llm.AIUnavailable):
            call("x" * (llm.LIMITS.max_input_chars + 1))

    def test_usage_records_hold_no_user_content(self):
        with store.connect() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(ai_usage)")]
        self.assertEqual(set(cols), {"id", "day", "feature", "tokens_in", "tokens_out", "web_searches", "estimated_cost"})

    def test_cost_estimate_is_sane(self):
        usage = type("U", (), {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "web_searches": 2})()
        self.assertAlmostEqual(llm.estimate_cost(usage), 0.10 + 0.50 + 0.02, places=6)


if __name__ == "__main__":
    unittest.main()


class EnvFiles(unittest.TestCase):
    """The key is found in the repo's folder first, then in the folder above it; blanks never hide a real key."""

    def run_loader(self, repo_env, parent_env, start=None):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock

        from lib import llm

        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            repo.mkdir()
            if repo_env is not None:
                (repo / ".env").write_text(repo_env)
            if parent_env is not None:
                (Path(d) / ".env").write_text(parent_env)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PORTKEY_API_KEY", None)
                if start:
                    os.environ["PORTKEY_API_KEY"] = start
                llm.load_env_files([repo, Path(d)])
                return os.environ.get("PORTKEY_API_KEY")

    def test_a_shared_env_one_level_above_the_repo_is_found(self):
        self.assertEqual(self.run_loader(None, "PORTKEY_API_KEY=parent-key\nOPENAI_API_KEY=x\n"), "parent-key")

    def test_the_repos_own_env_wins_when_both_have_a_key(self):
        self.assertEqual(self.run_loader("PORTKEY_API_KEY=repo-key\n", "PORTKEY_API_KEY=parent-key\n"), "repo-key")

    def test_a_blank_key_copied_from_the_example_does_not_hide_the_real_one(self):
        self.assertEqual(self.run_loader("PORTKEY_API_KEY=\nAI_ENABLED=true\n", "PORTKEY_API_KEY=parent-key\n"), "parent-key")

    def test_an_already_set_variable_is_not_replaced(self):
        self.assertEqual(self.run_loader("PORTKEY_API_KEY=repo-key\n", None, start="from-the-shell"), "from-the-shell")
