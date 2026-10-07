import json
import shutil
import tempfile
import unittest
from pathlib import Path

from secretcourse_source import SecretCourseSource, SecretCourseSourceError


class SecretCourseSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.status_path = self.root / "secretcourses" / "secretcourses-status.json"
        self.status_path.parent.mkdir(parents=True)
        self.source = SecretCourseSource(self.root, jka_style=1)

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    def write_status(self, courses, schema_version=2):
        self.status_path.write_text(
            json.dumps(
                {
                    "schema_version": schema_version,
                    "revision": "dc29a923",
                    "seasons": [
                        {
                            "id": "cc-s3",
                            "name": "Climb Cup Season 3",
                            "starts_at": 1791158400,
                            "expires_at": 1793401199,
                        }
                    ],
                    "courses": courses,
                }
            ),
            encoding="utf-8",
        )

    def cup_course(self, leaderboard_path="/secretcourses/cup/cc-s3/sumot/leaderboard.json"):
        return {
            "id": "sumot",
            "course_name": "hothchallenges (sumotower)",
            "type": "cup",
            "season_id": "cc-s3",
            "starts_at": 1791198000,
            "expires_at": 1791486000,
            "lifecycle": "active",
            "activated_at": 1791200009,
            "finalized_at": None,
            "demos_visibility": "private",
            "leaderboard_path": leaderboard_path,
        }

    async def test_loads_status_and_filtered_leaderboard_in_export_order(self):
        cup = self.cup_course()
        permanent = {
            **cup,
            "id": "acro-downmaze",
            "type": "permanent",
            "season_id": None,
            "expires_at": None,
            "leaderboard_path": "/secretcourses/permanent/acro-downmaze/leaderboard.json",
        }
        self.write_status([cup, permanent])
        leaderboard_path = self.root / cup["leaderboard_path"].lstrip("/")
        leaderboard_path.parent.mkdir(parents=True)
        leaderboard_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": "dc29a923",
                    "course_id": "sumot",
                    "course_name": cup["course_name"],
                    "demos_visibility": "private",
                    "entries": [
                        {"username": "thndr", "style": 1, "time": "35.407", "duration_ms": 35407, "topspeed": 2088, "average": 600, "end_time": 1791239631},
                        {"username": "shakur", "style": 1, "time": "36.245", "duration_ms": 36245, "topspeed": 2092, "average": 611, "end_time": 1791232291},
                        {"username": "thndr", "style": 4, "time": "4.274", "duration_ms": 4274, "topspeed": 487, "average": 133, "end_time": 1791232294},
                    ],
                }
            ),
            encoding="utf-8",
        )

        status = await self.source.load_status()
        entries = await self.source.load_leaderboard(status.courses[0], status.revision)

        self.assertEqual(status.seasons[0].name, "Climb Cup Season 3")
        self.assertEqual([course.id for course in status.courses], ["sumot", "acro-downmaze"])
        self.assertEqual([entry.username for entry in entries], ["thndr", "shakur"])

    async def test_rejects_unsupported_status_schema_and_malformed_json(self):
        self.write_status([], schema_version=1)
        with self.assertRaises(SecretCourseSourceError):
            await self.source.load_status()

        self.status_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SecretCourseSourceError):
            await self.source.load_status()

    async def test_rejects_leaderboard_path_outside_export_root(self):
        self.write_status([self.cup_course("/../outside/leaderboard.json")])
        status = await self.source.load_status()

        with self.assertRaises(SecretCourseSourceError):
            await self.source.load_leaderboard(status.courses[0], status.revision)

    async def test_rejects_status_export_reached_through_an_escaping_symlink(self):
        outside = Path(self.temporary_directory.name).with_name(Path(self.temporary_directory.name).name + "-outside")
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "secretcourses-status.json").write_text(
            json.dumps({"schema_version": 2, "revision": "outside", "seasons": [], "courses": []}),
            encoding="utf-8",
        )
        self.status_path.parent.rmdir()
        self.status_path.parent.symlink_to(outside, target_is_directory=True)

        with self.assertRaises(SecretCourseSourceError):
            await self.source.load_status()

    async def test_rejects_leaderboard_with_mismatched_identity_or_revision(self):
        cup = self.cup_course()
        self.write_status([cup])
        leaderboard_path = self.root / cup["leaderboard_path"].lstrip("/")
        leaderboard_path.parent.mkdir(parents=True)
        leaderboard_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "revision": "other-revision",
                    "course_id": "other-course",
                    "course_name": cup["course_name"],
                    "demos_visibility": "private",
                    "entries": [],
                }
            ),
            encoding="utf-8",
        )
        status = await self.source.load_status()

        with self.assertRaises(SecretCourseSourceError):
            await self.source.load_leaderboard(status.courses[0], status.revision)


if __name__ == "__main__":
    unittest.main()
