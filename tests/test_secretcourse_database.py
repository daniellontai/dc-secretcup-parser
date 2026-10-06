import tempfile
import unittest
from pathlib import Path

from db_manager import DatabaseManager
from secretcourse_types import ExportCourse, ExportSeason, LeaderboardEntry, StatusExport


def cup(course_id, name="hothchallenges (sumotower)", lifecycle="active", finalized_at=None):
    return ExportCourse(course_id, name, "cup", "cc-s3", 10, 20, lifecycle, 11, finalized_at, "private", f"/secretcourses/cup/cc-s3/{course_id}/leaderboard.json")


def entry(username, duration=35000):
    return LeaderboardEntry(username, 1, "35.000", duration, 2000, 600, 100)


class SecretCourseDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = DatabaseManager(str(Path(self.directory.name) / "bot.db"))
        await self.database.init_bot_database()
        self.status = StatusExport("rev-1", (ExportSeason("cc-s3", "Climb Cup Season 3", 1, 100),), (cup("sumot"), cup("sumot-rerun")))

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_upserts_courses_by_jka_id_even_when_names_match(self):
        await self.database.apply_status(self.status, seen_at=50)

        courses = await self.database.get_season_courses("cc-s3")

        self.assertEqual([course["id"] for course in courses], ["sumot", "sumot-rerun"])

    async def test_finalization_is_idempotent_and_survives_reopening_database(self):
        await self.database.apply_status(self.status, seen_at=50)

        self.assertTrue(await self.database.finalize_course("sumot", 60, [entry("thndr"), entry("shakur", 36000)]))
        reopened = DatabaseManager(self.database.bot_db_path)
        self.assertFalse(await reopened.finalize_course("sumot", 60, [entry("thndr")]))

        leaderboard = await reopened.get_season_leaderboard("cc-s3", include_projections=False)
        self.assertEqual([(row["username"], row["total_points"]) for row in leaderboard], [("thndr", 30), ("shakur", 25)])

    async def test_missing_active_course_is_cancelled_without_points_but_finalized_course_is_retained(self):
        await self.database.apply_status(self.status, seen_at=50)
        await self.database.finalize_course("sumot", 60, [entry("thndr")])
        await self.database.mark_missing_courses(set(), seen_at=70)

        courses = {course["id"]: course for course in await self.database.get_season_courses("cc-s3")}
        leaderboard = await self.database.get_season_leaderboard("cc-s3", include_projections=False)

        self.assertEqual(courses["sumot-rerun"]["lifecycle"], "cancelled")
        self.assertEqual(courses["sumot"]["lifecycle"], "expired")
        self.assertEqual([(row["username"], row["total_points"]) for row in leaderboard], [("thndr", 30)])


if __name__ == "__main__":
    unittest.main()
