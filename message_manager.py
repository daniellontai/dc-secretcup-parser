"""Discord dashboard rendering and idempotent final-course delivery."""

import asyncio

import discord

from config import config
from formatters import MessageFormatter


class MessageManager:
    def __init__(self):
        self.bot = None
        self.synchronizer = None
        self.running = False

    def set_bot(self, bot) -> None:
        self.bot = bot

    def set_synchronizer(self, synchronizer) -> None:
        self.synchronizer = synchronizer

    async def start_live_updates(self) -> None:
        if self.running:
            return
        self.running = True
        while self.running:
            await self.update_all_messages()
            await asyncio.sleep(config.get_path("secretcourses.poll_interval_seconds", 30))

    def _channel_for(self, season_id: str):
        if self.bot is None:
            return None
        channel_id = config.get_path(
            f"discord.season_channel_ids.{season_id}",
            config.get_path("discord.default_channel_id"),
        )
        return self.bot.get_channel(channel_id) if channel_id else None

    async def update_all_messages(self):
        if self.synchronizer is None:
            return None
        report = await self.synchronizer.sync_once()
        if self.bot is None:
            return report
        database = self.synchronizer.database
        for season in await database.get_imported_seasons():
            channel = self._channel_for(season["id"])
            if channel is None:
                continue
            courses = await database.get_season_courses(season["id"])
            results = {course["id"]: await database.get_course_results(course["id"]) for course in courses}
            embed = MessageFormatter.create_season_dashboard(
                season, courses, results, config.get_path("discord.show_final_times", True)
            )
            saved = await database.get_message(season["id"])
            message = None
            if saved and saved[0] == channel.id:
                try:
                    message = await channel.fetch_message(saved[1])
                except (discord.NotFound, KeyError):
                    message = None
            if message is None:
                message = await channel.send(embed=embed)
                await database.store_message(season["id"], channel.id, message.id)
            else:
                await message.edit(embed=embed)
        await self._announce_final_courses(report)
        return report

    async def _announce_final_courses(self, report) -> None:
        database = self.synchronizer.database
        for course_id in report.finalized_course_ids:
            course = await database.get_course(course_id)
            if course is None or not await database.claim_final_announcement(course_id):
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
