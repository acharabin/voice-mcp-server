"""Offline checks for portfolio extraction; run from any working directory."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import sync_portfolio


HTML = """
<html><body>
<section id="about"><div class="content"><span class="tag">Data &amp; AI</span>
<p>Business and engineering.</p><!-- <p>Obsolete biography</p> -->
<div class="box"><p>age: 31</p><p>phone: 555</p></div></div></section>
<section id="myinterests"><div class="content"><h3>Anywhere</h3>
<span class="tag">Cover</span><p>I recorded the instruments.</p><audio>Browser fallback</audio></div></section>
<section id="education"><div class="box"><div class="content"><h3>Degree</h3><p>School</p><h4>2018</h4></div></div></section>
<section id="experience"><div class="container"><h2>Manager</h2><h3>Company</h3><p>2025 - Oct 2026</p></div></section>
<script>do_not_include()</script></body></html>
"""


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.files = {
            "index.html": HTML,
            "projects.json": json.dumps([{"name": "Project", "desc": "Built an assistant.",
                "category": "AI", "links": {"view": "https://example.com/project", "code": "https://example.com/project"}}]),
            "skills.json": json.dumps([{"name": "Python"}, {"name": ""}, {"name": "Python"}]),
        }

    def render(self):
        # Autospec preserves the path argument so each fixture is read separately.
        with patch.object(Path, "read_text", autospec=True,
                          side_effect=lambda path, **kw: self.files[path.name]), \
                patch.object(sync_portfolio, "git", return_value=None):
            return sync_portfolio.export_portfolio(Path("fixture"))

    def test_factual_sections_and_links_are_preserved_without_page_chrome(self):
        result = self.render()
        for fact in ("Data & AI", "Business and engineering.", "Degree | School | 2018",
                     "Manager | Company | 2025 - Oct 2026", "Built an assistant."):
            self.assertIn(fact, result)
        for noise in ("Obsolete biography", "age: 31", "phone: 555", "do_not_include", "Browser fallback"):
            self.assertNotIn(noise, result)
        self.assertEqual(result.count("https://example.com/project"), 1)
        self.assertEqual(result.count("Python"), 1)

    def test_empty_projects_fail_instead_of_writing_an_incomplete_profile(self):
        self.files["projects.json"] = "[]"
        with self.assertRaisesRegex(ValueError, "incomplete snapshot"):
            self.render()

    def test_invalid_project_schema_is_reported(self):
        self.files["projects.json"] = "{}"
        with self.assertRaisesRegex(ValueError, "array of objects"):
            self.render()


if __name__ == "__main__":
    unittest.main()
