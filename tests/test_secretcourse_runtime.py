import unittest

import bot as runtime
from config import config
from secretcourse_types import SyncReport


class SecretCourseRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_jka_season_commands_and_channel_configuration_replace_legacy_commands(self):
        class Response:
            def __init__(self): self.messages = []
            async def send_message(self, message, **kwargs): self.messages.append(message)

        class Interaction:
            def __init__(self, administrator=True):
                self.response = Response()
                self.user = type("User", (), {"guild_permissions": type("Permissions", (), {"administrator": administrator})(), "roles": []})()

        class Database:
            async def get_season_leaderboard(self, season_id):
                return [{"position": 1, "username": "thndr", "total_points": 30}] if season_id == "cc-s3" else []
            async def get_season_courses(self, season_id):
                return [{"course_name": "sumot", "lifecycle": "active"}] if season_id == "cc-s3" else []

        old_database, old_synchronizer = runtime.db_manager, runtime.bot.synchronizer
        default_channel = config.get_path("discord.default_channel_id")
        season_channels = dict(config.get_path("discord.season_channel_ids", {}))
        runtime.db_manager = Database()
        runtime.bot.synchronizer = type("Synchronizer", (), {"last_report": SyncReport("rev-1", 10, warnings=("partial export",))})()
        try:
            leaderboard = Interaction()
            await runtime.secretcourse.callback(leaderboard, "leaderboard", "cc-s3")
            courses = Interaction()
            await runtime.secretcourse.callback(courses, "courses", "cc-s3")
            debug = Interaction()
            await runtime.secretcourse.callback(debug, "debug", "sync")
            default = Interaction()
            await runtime.secretcourse.callback(default, "config", "default-channel", "123")
            override = Interaction()
            await runtime.secretcourse.callback(override, "config", "season-channel", "cc-s3 456")
            scoring = Interaction()
            await runtime.secretcourse.callback(scoring, "config", "scoring min", "2")
            toggle = Interaction()
            await runtime.secretcourse.callback(toggle, "toggle", "standings", "off")
            legacy = Interaction()
            await runtime.secretcourse.callback(legacy, "season", "start", "1")
            unauthorized = Interaction(administrator=False)
            await runtime.secretcourse.callback(unauthorized, "config", "default-channel", "999")

            self.assertIn("thndr", leaderboard.response.messages[0])
            self.assertIn("sumot", courses.response.messages[0])
            self.assertIn("Revision: rev-1", debug.response.messages[0])
            self.assertEqual(config.get_path("discord.default_channel_id"), 123)
            self.assertEqual(config.get_path("discord.season_channel_ids.cc-s3"), 456)
            self.assertEqual(config.get_path("scoring.min_courses_required"), 2)
            self.assertFalse(config.get_path("discord.message_toggles.season_standings"))
            self.assertNotIn("season start", legacy.response.messages[0])
            self.assertNotIn("logstatus", legacy.response.messages[0])
            self.assertEqual(config.get_path("discord.default_channel_id"), 123)
            self.assertIn("not authorized", unauthorized.response.messages[0])
        finally:
            runtime.db_manager, runtime.bot.synchronizer = old_database, old_synchronizer
            config.set_path("discord.default_channel_id", default_channel)
            config.set_path("discord.season_channel_ids", season_channels)
            config.set_path("scoring.min_courses_required", 0)
            config.set_path("discord.message_toggles.season_standings", True)
