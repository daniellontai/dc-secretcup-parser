import json
import tempfile
import unittest
from pathlib import Path

from config import Config
from secretcourse_types import ExportCourse


class SecretCourseTypesTests(unittest.TestCase):
    def test_export_course_preserves_cup_and_permanent_schedule_fields(self):
        cup = ExportCourse(
            id="sumot",
            course_name="hothchallenges (sumotower)",
            type="cup",
            season_id="cc-s3",
            starts_at=1791198000,
            expires_at=1791486000,
            lifecycle="active",
            activated_at=1791200009,
            finalized_at=None,
            demos_visibility="private",
            leaderboard_path="/secretcourses/cup/cc-s3/sumot/leaderboard.json",
        )
        permanent = ExportCourse(
            id="acro-downmaze",
            course_name="expedition (downmaze)",
            type="permanent",
            season_id=None,
            starts_at=1788220800,
            expires_at=None,
            lifecycle="active",
            activated_at=1790812800,
            finalized_at=None,
            demos_visibility="private",
            leaderboard_path="/secretcourses/permanent/acro-downmaze/leaderboard.json",
        )

        self.assertEqual(cup.season_id, "cc-s3")
        self.assertEqual(cup.expires_at, 1791486000)
        self.assertIsNone(permanent.season_id)
        self.assertIsNone(permanent.expires_at)

    def test_nested_config_update_preserves_sibling_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(
                json.dumps({"scoring": {"min_courses_required": 1, "best_courses_count": 3}}),
                encoding="utf-8",
            )
            config = Config(str(config_path))

            config.set_path("scoring.min_courses_required", 2)

            self.assertEqual(config.get_path("scoring.min_courses_required"), 2)
            self.assertEqual(config.get_path("scoring.best_courses_count"), 3)


if __name__ == "__main__":
    unittest.main()
