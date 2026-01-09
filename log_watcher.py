"""
Log file watcher for SecretCourse Discord Bot
Monitors TaystJK server log for SCLOG events
"""
import asyncio
import aiofiles
import json
import re
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

from config import config
from db_manager import db_manager

import discord

logger = logging.getLogger(__name__)

class LogWatcher:
    """Watches the TaystJK server log file for SCLOG events"""
    
    def __init__(self, bot_instance=None):
        self.log_file_path = config.get("log_file_path")
        self.position_file = "log_position.txt"
        self.last_position = 0
        self.bot = bot_instance
        self.running = False
        
        # Regex patterns for parsing
        self.sclog_pattern = re.compile(r'--SCLOG-START--(.+?)--SCLOG-END--')
        self.ansi_pattern = re.compile(r'\x1b\[[0-9;]*[mK]')
    
    async def start_monitoring(self):
        """Start monitoring the log file"""
        if self.running:
            logger.warning("Log monitoring is already running")
            return
        
        self.running = True
        logger.info(f"Starting log file monitoring: {self.log_file_path}")
        
        # Load last position
        await self.load_position()
        
        # Start monitoring loop
        while self.running:
            try:
                await self.check_log_file()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in log monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def stop_monitoring(self):
        """Stop monitoring the log file"""
        self.running = False
        logger.info("Log monitoring stopped")
    
    async def load_position(self):
        """Load the last read position from file"""
        try:
            if Path(self.position_file).exists():
                async with aiofiles.open(self.position_file, 'r') as f:
                    content = await f.read()
                    self.last_position = int(content.strip())
                    logger.debug(f"Loaded last position: {self.last_position}")
            else:
                # Start from end of file on first run
                if Path(self.log_file_path).exists():
                    self.last_position = Path(self.log_file_path).stat().st_size
                    logger.info(f"Starting from end of log file: {self.last_position}")
        except Exception as e:
            logger.error(f"Error loading position: {e}")
            self.last_position = 0
    
    async def save_position(self):
        """Save the current read position to file"""
        try:
            async with aiofiles.open(self.position_file, 'w') as f:
                await f.write(str(self.last_position))
            logger.debug(f"Saved position: {self.last_position}")
        except Exception as e:
            logger.error(f"Error saving position: {e}")
    
    async def check_log_file(self):
        """Check log file for new content since last position"""
        try:
            if not Path(self.log_file_path).exists():
                logger.warning(f"Log file not found: {self.log_file_path}")
                return
            
            # Get current file size
            current_size = Path(self.log_file_path).stat().st_size
            
            # Check if file was rotated (size decreased)
            if current_size < self.last_position:
                logger.info("Log file rotated, starting from beginning")
                self.last_position = 0
            
            # No new content
            if current_size == self.last_position:
                return
            
            # Read new content
            async with aiofiles.open(self.log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                await f.seek(self.last_position)
                new_content = await f.read()
                self.last_position = current_size
            
            if new_content:
                await self.process_new_content(new_content)
                await self.save_position()
                
        except Exception as e:
            logger.error(f"Error checking log file: {e}")
    
    async def process_new_content(self, content: str):
        """Process new log content for SCLOG events"""
        try:
            # Split into lines for processing
            lines = content.split('\n')
            
            for line in lines:
                if '--SCLOG-START--' in line and '--SCLOG-END--' in line:
                    await self.process_sclog_event(line)
                    
        except Exception as e:
            logger.error(f"Error processing new content: {e}")
    
    async def process_sclog_event(self, line: str):
        """Process a single SCLOG event from a log line"""
        try:
            # Strip ANSI color codes
            clean_line = self.ansi_pattern.sub('', line)
            
            # Extract SCLOG content
            match = self.sclog_pattern.search(clean_line)
            if not match:
                logger.warning(f"Failed to extract SCLOG content from: {line[:100]}...")
                return
            
            sclog_content = match.group(1).strip()
            logger.debug(f"Processing SCLOG event: {sclog_content}")
            
            # Determine event type and process
            if sclog_content.startswith('COURSE_ADDED:'):
                await self.handle_course_added(sclog_content)
            elif sclog_content.startswith('COURSE_REMOVED:'):
                await self.handle_course_removed(sclog_content)
            elif sclog_content.startswith('{'):
                # JSON event (course expiry)
                await self.handle_course_expired(sclog_content)
            else:
                logger.warning(f"Unknown SCLOG event type: {sclog_content[:50]}...")
                
        except Exception as e:
            logger.error(f"Error processing SCLOG event: {e}")
    
    async def handle_course_added(self, content: str):
        """Handle COURSE_ADDED event"""
        try:
            # Parse: "COURSE_ADDED: racearena_pro (dash1) | 1758066824"
            parts = content.split('COURSE_ADDED:', 1)[1].strip().split('|')
            if len(parts) != 2:
                logger.error(f"Invalid COURSE_ADDED format: {content}")
                return
            
            full_course_name = parts[0].strip()
            secret_until = int(parts[1].strip())
            
            # Get active season
            season = await db_manager.get_active_season()
            if not season:
                logger.warning(f"No active season when adding course: {full_course_name}")
                return
            
            # Add course to database
            await db_manager.add_season_course(season['id'], full_course_name, secret_until)
            
            logger.info(f"Course added: {full_course_name}, expires at {datetime.fromtimestamp(secret_until)}")
            
            # Notify bot if available
            if self.bot:
                await self.notify_course_added(full_course_name, secret_until)
                
        except Exception as e:
            logger.error(f"Error handling COURSE_ADDED: {e}")
    
    async def handle_course_removed(self, content: str):
        """Handle COURSE_REMOVED event"""
        try:
            # Parse: "COURSE_REMOVED: racearena_pro (dash1)"
            full_course_name = content.split('COURSE_REMOVED:', 1)[1].strip()

            season = await db_manager.get_active_season()
            if not season:
                logger.warning(f"No active season when adding course: {full_course_name}")
                return
            
            await db_manager.remove_season_course(season['id'], full_course_name)
            
            logger.info(f"Course removed: {full_course_name}")

            if self.bot:
                await self.notify_course_removed(full_course_name)
            
            # Note: This was a manual admin removal so we remove from database
            
            
        except Exception as e:
            logger.error(f"Error handling COURSE_REMOVED: {e}")
    
    async def handle_course_expired(self, content: str):
        """Handle course expiry JSON event"""
        try:
            # Parse JSON content
            event_data = json.loads(content)
            
            if event_data.get('event') != 'secret_course_expired':
                logger.warning(f"Unknown JSON event type: {event_data.get('event')}")
                return
            
            full_course_name = event_data.get('coursename')
            standings = event_data.get('standings', [])
            
            if not full_course_name:
                logger.error(f"Missing coursename in expiry event: {content}")
                return
            
            # Mark course as expired and store standings
            await db_manager.expire_course(full_course_name, event_data)
            
            logger.info(f"Course expired: {full_course_name} with {len(standings)} results")
            
            # Notify bot if available
            if self.bot:
                await self.notify_course_expired(full_course_name, event_data)
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SCLOG event: {e}")
        except Exception as e:
            logger.error(f"Error handling course expiry: {e}")
    
    async def notify_course_added(self, full_course_name: str, secret_until: int):
        """Notify bot about course addition (for future live updates)"""
        try:
            # Extract course name for display
            course_name = full_course_name.split('(')[1].split(')')[0] if '(' in full_course_name else full_course_name
            expiry_date = datetime.fromtimestamp(secret_until).strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info(f"Course '{course_name}' added, expires: {expiry_date}")
            # TODO: Update live messages when implemented in Phase 4
            
        except Exception as e:
            logger.error(f"Error notifying course addition: {e}")

    async def notify_course_removed(self, full_course_name: str):
        try:
            logger.info(f"Course '{full_course_name}' has been removed.")
            # TODO: Update live messages when implemented in Phase 4
        except Exception as e:
            logger.error(f"Error notifying course removal: {e}")
    
    async def notify_course_expired(self, full_course_name: str, event_data: Dict):
        """Notify bot about course expiry (for immediate announcements)"""
        try:
            course_name = full_course_name.split('(')[1].split(')')[0] if '(' in full_course_name else full_course_name
            standings = event_data.get('standings', [])
            
            logger.info(f"Course '{course_name}' expired with {len(standings)} participants")
            
            # Send announcement if bot and channel are available
            if self.bot and config.get("announcement_channel_id"):
                channel = self.bot.get_channel(config.get("announcement_channel_id"))
                
                if channel and standings:
                    embed = discord.Embed(
                        title=f"🏁 {course_name.title()} - Final Results",
                        color=discord.Color.red()
                    )
                    
                    # Top 10 results
                    top_10 = standings[:10]
                    results_text = []
                    
                    for result in top_10:
                        points = db_manager.calculate_points(result['rank'])
                        medal = "🥇" if result['rank'] == 1 else "🥈" if result['rank'] == 2 else "🥉" if result['rank'] == 3 else f"{result['rank']}."
                        results_text.append(f"{medal} {result['username']} - {result['time_str']}s ({points} pts)")
                    
                    embed.add_field(
                        name=f"Final Standings ({len(standings)} participants)",
                        value="\n".join(results_text),
                        inline=False
                    )
                    
                    embed.set_footer(text=f"Course expired at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    try:
                        # Send message with @everyone ping
                        await channel.send("@everyone", embed=embed)
                        logger.info(f"Posted expiry announcement for {course_name} with @everyone ping")
                    except Exception as e:
                        logger.error(f"Error posting expiry announcement: {e}")
            
        except Exception as e:
            logger.error(f"Error notifying course expiry: {e}")

    async def notify_course_expired(self, full_course_name: str, event_data: Dict):
        """Notify bot about course expiry (for immediate announcements)"""
        try:
            course_name = full_course_name.split('(')[1].split(')')[0] if '(' in full_course_name else full_course_name
            standings = event_data.get('standings', [])
            
            logger.info(f"Course '{course_name}' expired with {len(standings)} participants")
            
            # Send announcement if bot and channel are available
            if self.bot and config.get("announcement_channel_id"):
                channel = self.bot.get_channel(config.get("announcement_channel_id"))
                
                if channel and standings:
                    embed = discord.Embed(
                        title=f"🏁 {course_name.title()} - Final Results",
                        color=discord.Color.red()
                    )
                    
                    # Top 10 results
                    top_10 = standings[:10]
                    results_text = []
                    
                    for result in top_10:
                        points = db_manager.calculate_points(result['rank'])
                        medal = "🥇" if result['rank'] == 1 else "🥈" if result['rank'] == 2 else "🥉" if result['rank'] == 3 else f"{result['rank']}."
                        results_text.append(f"{medal} {result['username']} - {result['time_str']}s ({points} pts)")
                    
                    embed.add_field(
                        name=f"Final Standings ({len(standings)} participants)",
                        value="\n".join(results_text),
                        inline=False
                    )
                    
                    embed.set_footer(text=f"Course expired at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    try:
                        await channel.send(embed=embed)
                        logger.info(f"Posted expiry announcement for {course_name}")
                    except Exception as e:
                        logger.error(f"Error posting expiry announcement: {e}")
            
        except Exception as e:
            logger.error(f"Error notifying course expiry: {e}")

# Global log watcher instance
log_watcher = LogWatcher()