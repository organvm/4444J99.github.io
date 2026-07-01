#!/usr/bin/env python3
"""Tests for scripts/sync-site.py.

Run:  python3 scripts/test_sync_site.py
"""

import importlib.util
import json
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("sync_site", _HERE / "sync-site.py")
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


class RenderOrgansTests(unittest.TestCase):
    def test_active_and_inactive_classes(self):
        out = ss.render_organs([
            {"label": "A", "url": "https://a/"},
            {"label": "B", "url": "https://b/", "active": True},
        ], "")
        self.assertIn('<li><a href="https://a/" class="">A</a></li>', out)
        self.assertIn('<li><a href="https://b/" class="active">B</a></li>', out)

    def test_escapes_special_chars(self):
        out = ss.render_organs([{"label": "X & <Y>", "url": "https://x/?a=1&b=2"}], "")
        self.assertIn("X &amp; &lt;Y&gt;", out)
        self.assertIn("a=1&amp;b=2", out)

    def test_indent_applied(self):
        out = ss.render_organs([{"label": "A", "url": "https://a/"}], "    ")
        self.assertTrue(out.startswith('    <li>'))


class RenderTests(unittest.TestCase):
    def test_value_marker_replaced(self):
        text = "d: <!-- v:synced -->old<!-- /v -->"
        out, warns = ss.render(text, {"values": {"synced": "2026-05-24"}})
        self.assertEqual(out, "d: <!-- v:synced -->2026-05-24<!-- /v -->")
        self.assertEqual(warns, [])

    def test_value_marker_escapes_html_and_coerces_none(self):
        text = ("name: <!-- v:name -->old<!-- /v --> "
                "empty: <!-- v:empty -->old<!-- /v -->")
        out, warns = ss.render(text, {"values": {"name": 'A&B <"Q">', "empty": None}})
        self.assertIn("<!-- v:name -->A&amp;B &lt;&quot;Q&quot;&gt;<!-- /v -->", out)
        self.assertIn("<!-- v:empty --><!-- /v -->", out)
        self.assertEqual(warns, [])

    def test_organs_block_regenerated(self):
        text = "<!-- organs:start -->stale<!-- organs:end -->"
        out, _ = ss.render(text, {"organs": [{"label": "A", "url": "https://a/"}]})
        self.assertIn("<!-- organs:start -->", out)
        self.assertIn('<li><a href="https://a/" class="">A</a></li>', out)
        self.assertIn("<!-- organs:end -->", out)
        self.assertNotIn("stale", out)

    def test_organs_indent_derived_from_marker(self):
        text = "        <!-- organs:start -->old<!-- organs:end -->"
        out, _ = ss.render(text, {"organs": [{"label": "A", "url": "https://a/"}]})
        self.assertTrue(out.startswith("        <!-- organs:start -->"))
        self.assertIn('\n        <li><a href="https://a/" class="">A</a></li>\n', out)
        self.assertIn("\n        <!-- organs:end -->", out)

    def test_orphan_value_and_marker_warn(self):
        _, warns = ss.render("<!-- v:foo -->x<!-- /v -->", {"values": {"bar": "1"}})
        self.assertTrue(any("foo" in w for w in warns))
        self.assertTrue(any("bar" in w for w in warns))

    def test_idempotent(self):
        data = {"values": {"synced": "2026-05-24"},
                "organs": [{"label": "A", "url": "https://a/", "active": True}]}
        seed = ("x <!-- v:synced -->0<!-- /v --> "
                "<!-- organs:start -->z<!-- organs:end -->")
        once, _ = ss.render(seed, data)
        twice, _ = ss.render(once, data)
        self.assertEqual(once, twice)

    def test_check_fails_when_marker_missing(self):
        # A value with no marker in the HTML must fail --check, not pass silently.
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text("<html>no markers here</html>", encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py", "--check"]
                self.assertEqual(ss.main(), 1)
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]

    def test_check_fails_on_text_drift_without_rewriting(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            stale = "<!-- v:synced -->old<!-- /v -->"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text(stale, encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py", "--check"]
                self.assertEqual(ss.main(), 1)
                self.assertEqual(hp.read_text(encoding="utf-8"), stale)
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]

    def test_missing_organs_block_warns(self):
        text = "<html>no block here</html>"
        _, warns = ss.render(text, {"organs": [{"label": "A", "url": "https://a/"}]})
        self.assertTrue(any("no <!-- organs:start/end --> block" in w for w in warns))

    def test_real_index_in_sync(self):
        data = json.loads((ss.REPO_ROOT / "data/site.json").read_text(encoding="utf-8"))
        original = (ss.REPO_ROOT / "index.html").read_text(encoding="utf-8")
        out, _ = ss.render(original, data)
        self.assertEqual(out, original, "index.html is out of sync with data/site.json")

    def test_main_updates_file(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text("<!-- v:synced -->old<!-- /v -->", encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py"]
                self.assertEqual(ss.main(), 0)
                self.assertEqual(hp.read_text(encoding="utf-8"), "<!-- v:synced -->2026-05-24<!-- /v -->")
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]

    def test_main_already_in_sync(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text("<!-- v:synced -->2026-05-24<!-- /v -->", encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py"]
                self.assertEqual(ss.main(), 0)
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]

    def test_main_check_in_sync(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text("<!-- v:synced -->2026-05-24<!-- /v -->", encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py", "--check"]
                self.assertEqual(ss.main(), 0)
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]

    def test_script_entrypoint_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d) / "site.json"
            hp = Path(d) / "index.html"
            dp.write_text(json.dumps({"values": {"synced": "2026-05-24"}}), encoding="utf-8")
            hp.write_text("<!-- v:synced -->2026-05-24<!-- /v -->", encoding="utf-8")
            os.environ["SITE_DATA"] = str(dp)
            os.environ["SITE_HTML"] = str(hp)
            old_argv = sys.argv
            try:
                sys.argv = ["sync-site.py", "--check"]
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(_HERE / "sync-site.py"), run_name="__main__")
                self.assertEqual(ctx.exception.code, 0)
            finally:
                sys.argv = old_argv
                del os.environ["SITE_DATA"]
                del os.environ["SITE_HTML"]


if __name__ == "__main__":
    unittest.main()
