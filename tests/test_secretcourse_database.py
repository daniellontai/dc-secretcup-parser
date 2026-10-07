import tempfile
import unittest
from pathlib import Path

from db_manager import DatabaseManager
from config import config
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

    async def test_season_courses_are_ordered_by_nearest_expiry(self):
        later = cup("later")
        sooner = ExportCourse("sooner", "Sooner", "cup", "cc-s3", 99, 15, "active", 10, None, "private", "/soon.json")
        await self.database.apply_status(
            StatusExport("rev-1", (ExportSeason("cc-s3", "Climb Cup Season 3", 1, 100),), (later, sooner)),
            seen_at=50,
        )

        courses = await self.database.get_season_courses("cc-s3")

        self.assertEqual([course["id"] for course in courses], ["sooner", "later"])

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

    async def test_leaderboard_keeps_final_points_separate_from_active_projections(self):
        await self.database.apply_status(self.status, seen_at=50)
        await self.database.finalize_course("sumot", 60, [entry("thndr")])
        await self.database.replace_live_results("sumot-rerun", [entry("shakur"), entry("thndr", 36000)])

        leaderboard = await self.database.get_season_leaderboard("cc-s3", include_projections=True)

        self.assertEqual(
            [(row["username"], row["total_points"], row["projected_points"], row["courses_completed"], row["courses_run"]) for row in leaderboard],
            [("thndr", 30, 55, 1, 2), ("shakur", 0, 30, 0, 1)],
        )

    async def test_scoring_honors_best_course_count_and_minimum_participation(self):
        previous_best = config.get_path("scoring.best_courses_count")
        previous_minimum = config.get_path("scoring.min_courses_required")
        config.set_path("scoring.best_courses_count", 1)
        config.set_path("scoring.min_courses_required", 2)
        try:
            await self.database.apply_status(self.status, seen_at=50)
            await self.database.finalize_course("sumot", 60, [entry("thndr")])
            await self.database.finalize_course("sumot-rerun", 61, [entry("shakur"), entry("thndr", 36000)])

            leaderboard = await self.database.get_season_leaderboard("cc-s3", include_projections=False)

            self.assertEqual(
                [(row["username"], row["total_points"], row["courses_completed"], row["qualified"]) for row in leaderboard],
                [("thndr", 30, 2, True), ("shakur", 30, 1, False)],
            )
        finally:
            config.set_path("scoring.best_courses_count", previous_best)
            config.set_path("scoring.min_courses_required", previous_minimum)


if __name__ == "__main__":
    unittest.main()
