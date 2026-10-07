"""Discord dashboard rendering and idempotent final-course delivery."""

import asyncio
import logging

import discord

from config import config
from formatters import MessageFormatter

logger = logging.getLogger(__name__)


class MessageManager:
    def __init__(self):
        self.bot = None
        self.synchronizer = None
        self.running = False
        self._update_lock = asyncio.Lock()

    def set_bot(self, bot) -> None:
        self.bot = bot

    def set_synchronizer(self, synchronizer) -> None:
        self.synchronizer = synchronizer

    async def start_live_updates(self) -> None:
        if self.running:
            return
        self.running = True
        try:
            while self.running:
                try:
                    await self.update_all_messages()
                except Exception:
                    logger.exception("Secret Course message update failed")
                await asyncio.sleep(config.get_path("secretcourses.poll_interval_seconds", 30))
        finally:
            self.running = False

    def _channel_for(self, season_id: str):
        if self.bot is None:
            return None
        channel_id = config.get_path(
            f"discord.season_channel_ids.{season_id}",
            config.get_path("discord.default_channel_id"),
        )
        return self.bot.get_channel(channel_id) if channel_id else None

    async def update_all_messages(self):
        async with self._update_lock:
            return await self._update_all_messages()

    async def _update_all_messages(self):
        if self.synchronizer is None:
            return None
        report = await self.synchronizer.sync_once()
        if self.bot is None:
            return report
        database = self.synchronizer.database
        for season in await database.get_imported_seasons():
            try:
                channel = self._channel_for(season["id"])
                if channel is None:
                    continue
                courses = await database.get_season_courses(season["id"])
                results = {course["id"]: await database.get_course_results(course["id"]) for course in courses}
                toggles = config.get_path("discord.message_toggles", {})
                top_players = config.get_path("discord.top_players_count", 10)
                leaderboard = await database.get_season_leaderboard(season["id"])
                messages = []
                if toggles.get("season_summary", True):
                    messages.append(("summary", MessageFormatter.create_jka_season_summary(season, leaderboard, top_players)))
                if toggles.get("season_standings", True):
                    messages.append(("standings", MessageFormatter.create_jka_season_standings(season, leaderboard, top_players)))
                if toggles.get("course_grid", True):
                    messages.append(("course_grid", MessageFormatter.create_jka_course_grid(season, courses, results, config.get_path("discord.show_final_times", True), config.get_path("discord.show_scheduled_courses", True), top_players, config.get_path("discord.courses_per_row", 2))))
                for message_type, embed in messages:
                    await self._upsert_message(database, season["id"], message_type, channel, embed)
            except Exception:
                logger.exception("Secret Course dashboard delivery failed for %s", season["id"])
        await self._announce_final_courses(report)
        return report

    async def _upsert_message(self, database, season_id: str, message_type: str, channel, embed) -> None:
        saved = await database.get_message(season_id, message_type)
        message = None
        if saved and saved[0] == channel.id:
            try:
                message = await channel.fetch_message(saved[1])
            except (discord.NotFound, KeyError):
                pass
        if message is None:
            message = await channel.send(embed=embed)
            await database.store_message(season_id, message_type, channel.id, message.id)
        else:
            await message.edit(embed=embed)

    async def _announce_final_courses(self, report) -> None:
        database = self.synchronizer.database
        await database.release_pending_final_announcement_claims()
        for course in await database.get_unannounced_final_courses():
            course_id = course["id"]
            if not await database.claim_final_announcement(course_id):
                continue
            channel = self._channel_for(course["season_id"])
            try:
                if channel is None:
                    raise RuntimeError("no Discord channel configured for final announcement")
                await channel.send(embed=discord.Embed(
                    title=f"🏁 {course['course_name']} finalized",
                    description=f"{course['course_name']} has been finalized by JKA.",
                    color=discord.Color.gold(),
                ))
            except Exception:
                await database.release_final_announcement(course_id)
            else:
                await database.mark_final_announced(course_id)

    async def force_update(self):
        await self.update_all_messages()
        return True


message_manager = MessageManager()
