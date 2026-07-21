import unittest
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_analytics import compute_streaks, replace_analytics_block, select_repositories


class AnalyticsGeneratorTests(unittest.TestCase):
    def test_compute_streaks_with_gap_today(self):
        day_counts = {
            "2026-07-17": 1,
            "2026-07-18": 2,
            "2026-07-19": 0,
            "2026-07-20": 5,
            "2026-07-21": 0,
        }
        current, longest, active = compute_streaks(day_counts, date(2026, 7, 21))
        self.assertEqual((current, longest, active), (1, 2, 3))

    def test_select_repositories_keeps_profile_repo(self):
        repos = [
            {"name": "other", "pushed_at": "2024-01-01T00:00:00Z"},
            {"name": "RaktheshTG", "pushed_at": "2020-01-01T00:00:00Z"},
        ]
        selected = select_repositories(repos, "RaktheshTG", max_repos=5, active_days=7)
        self.assertTrue(any(repo["name"] == "RaktheshTG" for repo in selected))

    def test_replace_analytics_block(self):
        text = "before\n<!-- ANALYTICS:START -->\nold\n<!-- ANALYTICS:END -->\nafter\n"
        updated = replace_analytics_block(text, "new\n")
        self.assertIn("new", updated)
        self.assertNotIn("old", updated)


if __name__ == "__main__":
    unittest.main()
