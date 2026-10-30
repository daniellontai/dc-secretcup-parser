import tempfile
import unittest
from pathlib import Path

from db_manager import DatabaseManager
from formatters import MessageFormatter
from message_manager import MessageManager
from config import config
from secretcourse_types import ExportCourse, ExportSeason, LeaderboardEntry, StatusExport, SyncReport


def course(course_id, season_id, lifecycle, finalized_at=None):
    return ExportCourse(course_id, course_id.title(), "cup", season_id, 10, 20, lifecycle, 11, finalized_at, "private", f"/{course_id}.json")


class SecretCourseMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = DatabaseManager(str(Path(self.directory.name) / "bot.db"))
        await self.database.init_bot_database()
        self.status = StatusExport(
            "rev-1",
            (ExportSeason("cc-s3", "Climb Cup Season 3", 1, 100),),
            (course("scheduled", "cc-s3", "scheduled"), course("active", "cc-s3", "active"), course("final", "cc-s3", "expired", 30)),
        )
        await self.database.apply_status(self.status, 50)
        await self.database.replace_live_results("active", [LeaderboardEntry("thndr", 1, "35.000", 35000, 1, 1, 1)])
        await self.database.finalize_course("final", 30, [LeaderboardEntry("shakur", 1, "36.000", 36000, 1, 1, 1)])

    async def asyncTearDown(self):
        self.directory.cleanup()

    async def test_final_announcement_claim_is_released_on_failure_and_persists_after_delivery(self):
        self.assertTrue(await self.database.claim_final_announcement("final"))
        self.assertFalse(await self.database.claim_final_announcement("final"))
        await self.database.release_final_announcement("final")
        self.assertTrue(await self.database.claim_final_announcement("final"))
        await self.database.mark_final_announced("final")

        reopened = DatabaseManager(self.database.bot_db_path)
        self.assertFalse(await reopened.claim_final_announcement("final"))

    async def test_final_announcement_pages_are_durable_across_retries(self):
        await self.database.store_final_announcement_page("final", 0, 9, 99)

        pages = await self.database.get_final_announcement_pages("final")

        self.assertEqual(pages, {0})

    async def test_final_announcement_payloads_freeze_page_boundaries_before_delivery(self):
        payloads = ['{"title":"page one"}', '{"title":"page two"}']
        await self.database.store_final_announcement_page_payloads("final", payloads)

        self.assertEqual(await self.database.get_final_announcement_page_payloads("final"), payloads)

    def test_final_season_embed_has_jka_name_dates_champion_and_first_five(self):
        leaderboard = [
            {"position": 1, "username": "thndr", "total_points": 30},
            {"position": 2, "username": "zielu", "total_points": 25},
            {"position": 3, "username": "shakur", "total_points": 21},
            {"position": 4, "username": "fourth", "total_points": 18},
            {"position": 5, "username": "fifth", "total_points": 16},
            {"position": 6, "username": "sixth", "total_points": 14},
        ]

        embed = MessageFormatter.create_final_season_result_embed(
            {"name": "Climb Cup Season 3", "starts_at": 1, "expires_at": 100},
            leaderboard,
        )

        self.assertEqual(embed.title, "🏁 Climb Cup Season 3 - Season Complete")
        self.assertIn("<t:1:F>", embed.fields[0].value)
        self.assertIn("<t:100:F>", embed.fields[0].value)
        self.assertIn("thndr — 30 pts", embed.fields[1].value)
        body = "\n".join(field.value for field in embed.fields)
        self.assertIn("fifth — 16 pts", body)
        self.assertNotIn("sixth", body)

    def test_final_season_embed_without_players_omits_champion_and_standings(self):
        embed = MessageFormatter.create_final_season_result_embed(
            {"name": "Climb Cup Season 3", "starts_at": 1, "expires_at": 100},
            [],
        )

        self.assertEqual([field.name for field in embed.fields], ["Season dates"])

    async def test_final_results_embed_lists_all_players_or_configured_limit(self):
        results = [
            {"rank": 1, "username": "thndr", "time": "35.407"},
            {"rank": 2, "username": "zielu", "time": "36.245"},
            {"rank": 3, "username": "shakur", "time": "37.012"},
        ]
        course = {"course_name": "Capella-Mountain", "finalized_at": 30}

        all_results = MessageFormatter.create_final_course_result_embeds(course, results, True, 0)
        limited = MessageFormatter.create_final_course_result_embeds(course, results, True, 2)

        self.assertEqual(all_results[0].title, "🏁 Capella-Mountain - Final Results")
        self.assertIn("🥇 thndr — 35.407s (30 pts)", all_results[0].fields[0].value)
        self.assertIn("🥉 shakur — 37.012s (21 pts)", all_results[0].fields[0].value)
        self.assertNotIn("shakur", limited[0].fields[0].value)

    async def test_final_results_embeds_bound_untrusted_display_text(self):
        course = {"course_name": "course-" + "x" * 400, "finalized_at": 30}
        results = [{"rank": 1, "username": "player-" + "y" * 1100, "time": "36.000"}]

        embed = MessageFormatter.create_final_course_result_embeds(course, results, True, 0)[0]

        self.assertLessEqual(len(embed.title), 256)
        self.assertLessEqual(len(embed.fields[0].value), 1024)

    async def test_dashboard_uses_jka_names_and_lifecycle_specific_result_details(self):
        courses = await self.database.get_season_courses("cc-s3")
        results = {item["id"]: await self.database.get_course_results(item["id"]) for item in courses}

        embed = MessageFormatter.create_season_dashboard(
            {"id": "cc-s3", "name": "Climb Cup Season 3"}, courses, results, show_final_times=True
        )
        body = "\n".join(field.value for field in embed.fields)

        self.assertEqual(embed.title, "🏆 Climb Cup Season 3")
        self.assertIn("Scheduled:", body)
        self.assertIn("1. thndr", body)
        self.assertNotIn("35.000", body)
        self.assertIn("1. shakur — 36.000", body)

    async def test_dashboard_standings_show_projected_points_for_active_courses(self):
        courses = await self.database.get_season_courses("cc-s3")
        results = {item["id"]: await self.database.get_course_results(item["id"]) for item in courses}
        standings = await self.database.get_season_leaderboard("cc-s3")

        embed = MessageFormatter.create_season_dashboard(
            {"id": "cc-s3", "name": "Climb Cup Season 3"}, courses, results, True, standings
        )

        self.assertIn("0 pts (30 projected)", embed.fields[0].value)

    async def test_dashboard_prioritizes_active_courses_and_discloses_overflow(self):
        courses = [
            {"id": f"final-{index}", "course_name": f"Final {index}", "starts_at": 1, "expires_at": 2, "lifecycle": "expired"}
            for index in range(25)
        ] + [{"id": "active-now", "course_name": "Active now", "starts_at": 1, "expires_at": 2, "lifecycle": "active"}]

        embed = MessageFormatter.create_season_dashboard({"id": "cc-s3", "name": "Cup"}, courses, {}, True)

        self.assertEqual(embed.fields[0].name, "Active now")
        self.assertEqual(embed.fields[-1].name, "More courses")

    async def test_jka_course_grid_stays_within_discord_embed_limit(self):
        courses = [
            {"id": f"course-{index}", "course_name": f"Course {index}", "starts_at": 1, "expires_at": index + 10, "lifecycle": "expired"}
            for index in range(25)
        ]
        results = {
            course["id"]: [{"rank": rank, "username": f"playername{rank:03d}", "time": "36.000"} for rank in range(1, 11)]
            for course in courses
        }

        embed = MessageFormatter.create_jka_course_grid({"id": "cc-s3", "name": "Cup"}, courses, results, True, True, 10, 2)

        self.assertLessEqual(len(embed), 6000)
        self.assertEqual(embed.fields[-1].name, "More courses")

    async def test_final_announcement_is_sent_once_across_repeated_reports(self):
        class Message:
            def __init__(self, message_id): self.id = message_id
            async def edit(self, **kwargs): pass

        class Channel:
            def __init__(self, channel_id): self.id, self.sent, self.messages = channel_id, [], {}
            async def send(self, **kwargs):
                self.sent.append(kwargs)
                message = Message(len(self.sent))
                self.messages[message.id] = message
                return message
            async def fetch_message(self, message_id): return self.messages[message_id]

        class Bot:
            def __init__(self, channel): self.channel = channel
            def get_channel(self, channel_id): return self.channel if channel_id == self.channel.id else None

        class Synchronizer:
            def __init__(self, database):
                self.database = database
                self.report = SyncReport("rev-1", 50, finalized_course_ids=("final",))
            async def sync_once(self): return self.report

        previous_channel = config.get_path("discord.default_channel_id")
        config.set_path("discord.default_channel_id", 9)
        try:
            channel = Channel(9)
            manager = MessageManager()
            manager.set_bot(Bot(channel))
            manager.set_synchronizer(Synchronizer(self.database))

            await manager.update_all_messages()
            await manager.update_all_messages()

            self.assertEqual(len(channel.sent), 4)
            self.assertEqual(
                [item["embed"].title for item in channel.sent],
                [
                    "🏆 Climb Cup Season 3",
                    "📊 Climb Cup Season 3 Standings",
                    "🗺️ Climb Cup Season 3 - Course Progress",
                    "🏁 Final - Final Results",
                ],
            )
            self.assertIsNotNone(await self.database.get_message("cc-s3", "summary"))
            self.assertIsNotNone(await self.database.get_message("cc-s3", "standings"))
            self.assertIsNotNone(await self.database.get_message("cc-s3", "course_grid"))
        finally:
            config.set_path("discord.default_channel_id", previous_channel)

    async def test_message_toggles_select_individual_jka_dashboard_messages(self):
        class Message:
            def __init__(self, message_id): self.id = message_id
            async def edit(self, **kwargs): pass
        class Channel:
            def __init__(self): self.id, self.sent = 9, []
            async def send(self, **kwargs): self.sent.append(kwargs); return Message(len(self.sent))
            async def fetch_message(self, message_id): raise KeyError(message_id)
        class Bot:
            def __init__(self, channel): self.channel = channel
            def get_channel(self, channel_id): return self.channel
        class Synchronizer:
            def __init__(self, database): self.database = database
            async def sync_once(self): return SyncReport("rev-1", 50)

        previous_channel = config.get_path("discord.default_channel_id")
        previous_toggles = dict(config.get_path("discord.message_toggles"))
        config.set_path("discord.default_channel_id", 9)
        config.set_path("discord.message_toggles", {"season_summary": False, "season_standings": True, "course_grid": False})
        try:
            channel, manager = Channel(), MessageManager()
            manager.set_bot(Bot(channel)); manager.set_synchronizer(Synchronizer(self.database))
            await manager.update_all_messages()
            dashboard_titles = [item["embed"].title for item in channel.sent if not item["embed"].title.startswith("🏁")]
            self.assertEqual(dashboard_titles, ["📊 Climb Cup Season 3 Standings"])
            self.assertIsNone(await self.database.get_message("cc-s3", "summary"))
            self.assertIsNone(await self.database.get_message("cc-s3", "course_grid"))
        finally:
            config.set_path("discord.default_channel_id", previous_channel)
            config.set_path("discord.message_toggles", previous_toggles)

    async def test_turning_a_published_message_toggle_off_removes_its_stale_message(self):
        class Message:
            def __init__(self, message_id): self.id, self.deleted = message_id, False
            async def edit(self, **kwargs): pass
            async def delete(self): self.deleted = True
        class Channel:
            def __init__(self): self.id, self.sent, self.messages = 9, [], {}
            async def send(self, **kwargs):
                message = Message(len(self.messages) + 1); self.messages[message.id] = message; self.sent.append(kwargs); return message
            async def fetch_message(self, message_id): return self.messages[message_id]
        class Bot:
            def __init__(self, channel): self.channel = channel
            def get_channel(self, channel_id): return self.channel
        class Synchronizer:
            def __init__(self, database): self.database = database
            async def sync_once(self): return SyncReport("rev-1", 50)

        previous_channel = config.get_path("discord.default_channel_id")
        previous_toggles = dict(config.get_path("discord.message_toggles"))
        config.set_path("discord.default_channel_id", 9)
        config.set_path("discord.message_toggles", {"season_summary": True, "season_standings": True, "course_grid": False})
        try:
            channel, manager = Channel(), MessageManager()
            manager.set_bot(Bot(channel)); manager.set_synchronizer(Synchronizer(self.database))
            await manager.update_all_messages()
            standings = await self.database.get_message("cc-s3", "standings")
            config.set_path("discord.message_toggles", {"season_summary": True, "season_standings": False, "course_grid": False})

            await manager.update_all_messages()

            self.assertTrue(channel.messages[standings[1]].deleted)
            self.assertIsNone(await self.database.get_message("cc-s3", "standings"))
        finally:
            config.set_path("discord.default_channel_id", previous_channel)
            config.set_path("discord.message_toggles", previous_toggles)

    async def test_failed_announcement_is_retried_after_the_finalization_report_is_gone(self):
        class Message:
            def __init__(self, message_id): self.id = message_id
            async def edit(self, **kwargs): pass
        class Channel:
            def __init__(self): self.id, self.sent, self.fail_final = 9, [], True
            async def send(self, **kwargs):
                if kwargs['embed'].title.startswith('🏁') and self.fail_final:
                    self.fail_final = False
                    raise RuntimeError('temporary Discord failure')
                self.sent.append(kwargs)
                return Message(len(self.sent))
            async def fetch_message(self, message_id): return Message(message_id)
        class Bot:
            def __init__(self, channel): self.channel = channel
            def get_channel(self, channel_id): return self.channel
        class Synchronizer:
            def __init__(self, database): self.database, self.calls = database, 0
            async def sync_once(self):
                self.calls += 1
                return SyncReport('rev-1', 50, finalized_course_ids=('final',) if self.calls == 1 else ())

        previous_channel = config.get_path('discord.default_channel_id')
        config.set_path('discord.default_channel_id', 9)
        try:
            channel, manager = Channel(), MessageManager()
            manager.set_bot(Bot(channel)); manager.set_synchronizer(Synchronizer(self.database))
            await manager.update_all_messages()
            await manager.update_all_messages()
            self.assertEqual([item['embed'].title for item in channel.sent].count('🏁 Final - Final Results'), 1)
        finally:
            config.set_path('discord.default_channel_id', previous_channel)
