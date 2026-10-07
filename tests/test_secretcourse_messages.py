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

            self.assertEqual(len(channel.sent), 2)
            self.assertEqual(channel.sent[1]["embed"].title, "🏁 Final finalized")
        finally:
            config.set_path("discord.default_channel_id", previous_channel)

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
            self.assertEqual([item['embed'].title for item in channel.sent].count('🏁 Final finalized'), 1)
        finally:
            config.set_path('discord.default_channel_id', previous_channel)
