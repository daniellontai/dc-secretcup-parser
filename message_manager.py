"""
Message manager for live Discord updates
Handles the 3-message system and periodic updates
"""
import discord
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from config import config
from db_manager import db_manager
from formatters import MessageFormatter

logger = logging.getLogger(__name__)

class MessageManager:
    """Manages live Discord message updates"""
    
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.running = False
        self.update_task = None
        
    def set_bot(self, bot_instance):
        """Set bot instance"""
        self.bot = bot_instance
    
    async def start_live_updates(self):
        """Start the live update loop"""
        if self.running:
            logger.warning("Live updates already running")
            return
        
        if not config.get("live_messages_enabled", False):
            logger.info("Live messages disabled in config")
            return
        
        if not config.get("announcement_channel_id"):
            logger.warning("No announcement channel configured")
            return
        
        self.running = True
        logger.info("Starting live message updates")
        
        # Start update task
        self.update_task = asyncio.create_task(self._update_loop())
    
    async def stop_live_updates(self):
        """Stop the live update loop"""
        if not self.running:
            return
        
        self.running = False
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Live message updates stopped")
    
    async def _update_loop(self):
        """Main update loop"""
        while self.running:
            try:
                await self.update_all_messages()
                
                interval = config.get("message_update_interval", 300)
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in update loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def update_all_messages(self):
        """Update all live messages"""
        try:
            season = await db_manager.get_active_season()
            if not season:
                logger.debug("No active season for live updates")
                return
            
            channel_id = config.get("announcement_channel_id")
            if not channel_id:
                return
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"Announcement channel {channel_id} not found")
                return
            
            # Get current data
            leaderboard = await db_manager.get_season_leaderboard_with_projections(season['id'])
            courses = await db_manager.get_active_courses(season['id'])
            current_standings = await self._get_current_standings(courses)
            
            # Get stored message IDs
            stored_messages = await db_manager.get_message_ids(season['id'])
            
            # Update each message type if enabled
            toggles = config.get("message_toggles", {})
            
            if toggles.get("season_summary", True):
                await self._update_message(
                    channel, "season_summary", season, stored_messages,
                    MessageFormatter.create_season_summary(season, leaderboard)
                )
            
            if toggles.get("season_standings", True):
                await self._update_message(
                    channel, "season_standings", season, stored_messages,
                    MessageFormatter.create_season_standings(season, leaderboard)
                )
            
            if toggles.get("course_grid", True):
                await self._update_message(
                    channel, "course_grid", season, stored_messages,
                    MessageFormatter.create_course_grid(season, courses, current_standings)
                )
            
            logger.debug("Live messages updated successfully")
            
        except Exception as e:
            logger.error(f"Error updating live messages: {e}")
    
    async def _update_message(self, channel: discord.TextChannel, message_type: str, 
                             season: Dict, stored_messages: Dict, embed: discord.Embed):
        """Update or create a single message"""
        try:
            message_info = stored_messages.get(message_type)
            message = None
            
            # Try to get existing message
            if message_info:
                try:
                    message = await channel.fetch_message(message_info['message_id'])
                except discord.NotFound:
                    logger.info(f"Stored {message_type} message not found, will create new one")
                    await db_manager.delete_message_id(message_type, season['id'])
                except Exception as e:
                    logger.warning(f"Error fetching {message_type} message: {e}")
            
            # Update existing message or create new one
            if message:
                await message.edit(embed=embed)
                logger.debug(f"Updated existing {message_type} message")
            else:
                message = await channel.send(embed=embed)
                await db_manager.store_message_id(message_type, channel.id, message.id, season['id'])
                logger.info(f"Created new {message_type} message: {message.id}")
            
        except Exception as e:
            logger.error(f"Error updating {message_type} message: {e}")
    
    async def _get_current_standings(self, courses: List[Dict]) -> Dict[str, List[Dict]]:
        """Get current standings for all active courses"""
        standings = {}
        
        for course in courses:
            if course['expired']:
                # Use final standings for expired courses
                if course.get('final_standings') and course['final_standings'].get('standings'):
                    standings[course['course_name']] = course['final_standings']['standings']
            else:
                # Get live standings for active courses
                live_standings = await db_manager.get_current_standings(course['full_course_name'])
                standings[course['course_name']] = live_standings
        
        return standings
    
    async def force_update(self):
        """Force an immediate update of all messages"""
        if not self.bot:
            logger.error("No bot instance available for force update")
            return False
        
        try:
            await self.update_all_messages()
            logger.info("Forced message update completed")
            return True
        except Exception as e:
            logger.error(f"Error in force update: {e}")
            return False

# Global message manager instance
message_manager = MessageManager()