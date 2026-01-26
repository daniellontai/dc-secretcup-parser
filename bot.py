"""
SecretCourse Discord Bot - Main Bot File
Phase 1: Basic bot setup with command framework and database initialization
"""
import discord
from discord.ext import commands
import logging
import asyncio
from datetime import datetime

from config import config
from db_manager import db_manager
from log_watcher import log_watcher
from message_manager import message_manager

from typing import Dict, List

# Setup logging
config.setup_logging()
logger = logging.getLogger(__name__)

class SecretCourseBot(commands.Bot):
    """Main bot class"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',  # We'll use slash commands, but prefix needed
            intents=intents,
            help_command=None
        )
    
    async def setup_hook(self):
        """Called when bot is starting up"""
        logger.info("Bot setup starting...")
        
        # Initialize bot database
        await db_manager.init_bot_database()
        
        # Setup log watcher with bot reference
        log_watcher.bot = self

        # Setup message manager
        message_manager.set_bot(self)
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_ready(self):
        """Called when bot has connected to Discord"""
        logger.info(f"Bot logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="secret courses expire"
            )
        )
        
        # Start log monitoring
        asyncio.create_task(log_watcher.start_monitoring())

        # Start live message updates
        if config.get("live_messages_enabled", False):
            asyncio.create_task(message_manager.start_live_updates())

bot = SecretCourseBot()

def has_admin_role():
    """Check if user has admin role"""
    async def predicate(interaction: discord.Interaction) -> bool:
        admin_role = config.get("admin_role", "Admin")
        if any(role.name == admin_role for role in interaction.user.roles):
            return True
        
        await interaction.response.send_message(
            f"❌ You need the '{admin_role}' role to use this command.", 
            ephemeral=True
        )
        return False
    
    return discord.app_commands.check(predicate)

@bot.tree.command(name="secretcourse", description="SecretCourse bot management commands")
@discord.app_commands.describe(
    action="Action to perform",
    subaction="Sub-action (for season commands)",
    value="Value for the action"
)
async def secretcourse(
    interaction: discord.Interaction,
    action: str,
    subaction: str = None,
    value: str = None
):
    """Main command dispatcher for all bot functions"""
    
    # For now, just handle basic commands
    if action == "season":
        if subaction == "info":
            await handle_season_info(interaction)
        elif subaction == "start":
            await handle_season_start(interaction, value)
        elif subaction == "end":
            await handle_season_end(interaction)
        else:
            await interaction.response.send_message(
                "❌ Available season commands: `info`, `start <season_number> [title]`, `end`",
                ephemeral=True
            )
    
    elif action == "config":
        if subaction == "channel":
            await handle_config_channel(interaction, value)
        elif subaction == "loglevel":
            await handle_config_loglevel(interaction, value)
        elif subaction == "messages":
            await handle_config_messages(interaction, value)
        elif subaction == "scoring":
            await handle_config_scoring(interaction, value)
        else:
            await interaction.response.send_message(
                "❌ Available config commands: `channel <channel_id>`, `loglevel <off|minimal|debug>`, `messages <on|off>`, `scoring [min|best <number>]`",
                ephemeral=True
            )
    elif action == "leaderboard":
        await handle_leaderboard(interaction, subaction)
    elif action == "courses":
        await handle_courses_list(interaction, subaction)
    
    elif action == "test":
        await handle_test(interaction)
    
    elif action == "debug":
        if subaction == "logstatus":
            await handle_debug_logstatus(interaction)
        elif subaction == "courses":
            await handle_debug_courses(interaction)
        else:
            await interaction.response.send_message(
                "❌ Available debug commands: `logstatus`, `courses`",
                ephemeral=True
            )
    elif action == "update":
        await handle_update_messages(interaction)

    elif action == "toggle":
        if subaction in ["summary", "standings", "grid"]:
            await handle_toggle_message(interaction, subaction, value)
        else:
            await interaction.response.send_message(
                "❌ Available toggles: `summary <on|off>`, `standings <on|off>`, `grid <on|off>`",
                ephemeral=True
            )
    
    else:
        await interaction.response.send_message(
            "❌ Available actions: `season`, `config`, `test`, `debug`, `leaderboard`, `courses`, `update`, `toggle`\n"
            "Use `/secretcourse season info` to see current season status.",
            ephemeral=True
        )

async def handle_season_info(interaction: discord.Interaction):
    """Handle season info command"""
    try:
        season = await db_manager.get_active_season()
        
        if not season:
            await interaction.response.send_message("❌ No active season found.", ephemeral=True)
            return
        
        start_date = datetime.fromtimestamp(season['start_date']).strftime("%Y-%m-%d %H:%M:%S")
        end_date = "Not set" if not season['end_date'] else datetime.fromtimestamp(season['end_date']).strftime("%Y-%m-%d %H:%M:%S")
        
        embed = discord.Embed(
            title=f"🏆 Season {season['season_number']} Info",
            color=discord.Color.blue()
        )
        
        if season['title']:
            embed.add_field(name="Title", value=season['title'], inline=False)
        
        embed.add_field(name="Started", value=start_date, inline=True)
        embed.add_field(name="Status", value="🟢 Active", inline=True)
        embed.add_field(name="End Date", value=end_date, inline=True)
        
        # Get course count
        courses = await db_manager.get_active_courses(season['id'])
        active_courses = [c for c in courses if not c['expired']]
        expired_courses = [c for c in courses if c['expired']]
        
        embed.add_field(name="Courses", value=f"{len(active_courses)} active, {len(expired_courses)} expired", inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in season info: {e}")
        await interaction.response.send_message("❌ An error occurred while getting season info.", ephemeral=True)

@has_admin_role()
async def handle_season_start(interaction: discord.Interaction, value: str):
    """Handle season start command"""
    if not value:
        await interaction.response.send_message("❌ Please provide a season number.", ephemeral=True)
        return
    
    try:
        # Parse season number and optional title
        parts = value.split(" ", 1)
        season_number = int(parts[0])
        title = parts[1] if len(parts) > 1 else None
        
        # Check if season already exists
        existing_season = await db_manager.get_active_season()
        if existing_season and existing_season['season_number'] == season_number:
            await interaction.response.send_message(f"❌ Season {season_number} is already active.", ephemeral=True)
            return
        
        # Create new season
        season_id = await db_manager.create_season(season_number, title)
        
        embed = discord.Embed(
            title=f"✅ Season {season_number} Started",
            color=discord.Color.green()
        )
        
        if title:
            embed.add_field(name="Title", value=title, inline=False)
        
        embed.add_field(name="Season ID", value=str(season_id), inline=True)
        embed.add_field(name="Started", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"Season {season_number} started by {interaction.user}")
        
    except ValueError:
        await interaction.response.send_message("❌ Invalid season number. Please provide a valid integer.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error starting season: {e}")
        await interaction.response.send_message("❌ An error occurred while starting the season.", ephemeral=True)

@has_admin_role()
async def handle_season_end(interaction: discord.Interaction):
    """Handle season end command"""
    try:
        season = await db_manager.get_active_season()
        if not season:
            await interaction.response.send_message("❌ No active season to end.", ephemeral=True)
            return
        
        # Check if there are any active courses
        courses = await db_manager.get_active_courses(season['id'])
        active_courses = [c for c in courses if not c['expired']]
        
        # Create confirmation view
        view = SeasonEndConfirmView(season, active_courses)
        
        if active_courses:
            course_list = ", ".join([c['course_name'] for c in active_courses[:5]])
            if len(active_courses) > 5:
                course_list += f" (and {len(active_courses) - 5} more)"
            
            embed = discord.Embed(
                title="⚠️ Confirm Season End",
                description=f"Season {season['season_number']} still has {len(active_courses)} active courses:\n{course_list}\n\nAre you sure you want to end this season?",
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(
                title="🏁 End Season",
                description=f"End Season {season['season_number']}?",
                color=discord.Color.red()
            )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in season end: {e}")
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

@has_admin_role()
async def handle_config_channel(interaction: discord.Interaction, value: str):
    """Handle config channel command"""
    if not value:
        await interaction.response.send_message("❌ Please provide a channel ID.", ephemeral=True)
        return
    
    try:
        channel_id = int(value)
        channel = bot.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        
        config.set("announcement_channel_id", channel_id)
        
        embed = discord.Embed(
            title="✅ Channel Configuration Updated",
            description=f"Announcement channel set to {channel.mention}",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"Announcement channel set to {channel.name} ({channel_id}) by {interaction.user}")
        
    except ValueError:
        await interaction.response.send_message("❌ Invalid channel ID. Please provide a valid integer.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error setting channel: {e}")
        await interaction.response.send_message("❌ An error occurred while setting the channel.", ephemeral=True)

@has_admin_role()
async def handle_config_loglevel(interaction: discord.Interaction, value: str):
    """Handle config loglevel command"""
    valid_levels = ["off", "minimal", "debug"]
    
    if not value or value.lower() not in valid_levels:
        await interaction.response.send_message(
            f"❌ Invalid log level. Valid options: {', '.join(valid_levels)}", 
            ephemeral=True
        )
        return
    
    try:
        config.set("log_level", value.lower())
        
        embed = discord.Embed(
            title="✅ Log Level Updated",
            description=f"Log level set to: `{value.lower()}`",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"Log level set to {value} by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error setting log level: {e}")
        await interaction.response.send_message("❌ An error occurred while setting the log level.", ephemeral=True)

@has_admin_role()
async def handle_config_scoring(interaction: discord.Interaction, value: str):
    """Handle config scoring command - set min_courses_required or best_courses_count"""
    if not value:
        # Show current settings
        min_req = config.get("min_courses_required", 0)
        best_count = config.get("best_courses_count", 0)

        embed = discord.Embed(
            title="📊 Scoring Configuration",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="min_courses_required",
            value=f"`{min_req}` (0 = disabled)",
            inline=False
        )
        embed.add_field(
            name="best_courses_count",
            value=f"`{best_count}` (0 = all courses count)",
            inline=False
        )
        embed.add_field(
            name="Usage",
            value="`/secretcourse config scoring min <number>`\n`/secretcourse config scoring best <number>`",
            inline=False
        )

        await interaction.response.send_message(embed=embed)
        return

    try:
        parts = value.split()
        if len(parts) != 2:
            await interaction.response.send_message(
                "❌ Usage: `scoring min <number>` or `scoring best <number>`",
                ephemeral=True
            )
            return

        setting_type, number = parts[0].lower(), int(parts[1])

        if number < 0:
            await interaction.response.send_message("❌ Value must be 0 or positive.", ephemeral=True)
            return

        if setting_type == "min":
            config.set("min_courses_required", number)
            desc = f"Minimum courses required set to `{number}`"
            if number == 0:
                desc += " (disabled)"
        elif setting_type == "best":
            config.set("best_courses_count", number)
            desc = f"Best courses count set to `{number}`"
            if number == 0:
                desc += " (all courses count)"
        else:
            await interaction.response.send_message(
                "❌ Unknown setting. Use `min` or `best`.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✅ Scoring Configuration Updated",
            description=desc,
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed)
        logger.info(f"Scoring config {setting_type} set to {number} by {interaction.user}")

    except ValueError:
        await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
    except Exception as e:
        logger.error(f"Error setting scoring config: {e}")
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

async def handle_leaderboard(interaction: discord.Interaction, value: str = None):
    """Handle leaderboard command"""
    try:
        # Parse season number if provided
        season_number = None
        if value:
            try:
                season_number = int(value)
            except ValueError:
                await interaction.response.send_message("❌ Invalid season number.", ephemeral=True)
                return
        
        # Get season
        if season_number:
            season = await db_manager.get_season_by_number(season_number)
            if not season:
                await interaction.response.send_message(f"❌ Season {season_number} not found.", ephemeral=True)
                return
        else:
            season = await db_manager.get_active_season()
            if not season:
                await interaction.response.send_message("❌ No active season found.", ephemeral=True)
                return
        
        # Get leaderboard
        leaderboard = await db_manager.get_season_leaderboard_with_projections(season['id'])
        
        embed = discord.Embed(
            title=f"🏆 Season {season['season_number']} Leaderboard",
            color=discord.Color.gold()
        )
        
        if season['title']:
            embed.add_field(name="Title", value=season['title'], inline=False)
        
        status = "🟢 Active" if season.get('is_active') else "🔴 Ended"
        embed.add_field(name="Status", value=status, inline=True)
        
        if not leaderboard:
            embed.add_field(name="Leaderboard", value="No results yet", inline=False)
        else:
            # Show top 10
            top_10 = leaderboard[:10]
            leaderboard_text = []
            
            for player in top_10:
                medal = "🥇" if player['position'] == 1 else "🥈" if player['position'] == 2 else "🥉" if player['position'] == 3 else f"{player['position']}."
                leaderboard_text.append(f"{medal} {player['username']} - {player['total_points']} pts ({player['courses_completed']} courses)")
            
            embed.add_field(name="Top 10", value="\n".join(leaderboard_text), inline=False)
            
            if len(leaderboard) > 10:
                embed.add_field(name="Total Players", value=str(len(leaderboard)), inline=True)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in leaderboard command: {e}")
        await interaction.response.send_message("❌ An error occurred while getting the leaderboard.", ephemeral=True)

async def handle_courses_list(interaction: discord.Interaction, value: str = None):
    """Handle courses list command"""
    try:
        active_only = value and value.lower() in ['true', 'active', 'yes', '1']
        
        season = await db_manager.get_active_season()
        if not season:
            await interaction.response.send_message("❌ No active season found.", ephemeral=True)
            return
        
        courses = await db_manager.get_active_courses(season['id'])
        
        if not courses:
            await interaction.response.send_message("❌ No courses found for current season.", ephemeral=True)
            return
        
        active_courses = [c for c in courses if not c['expired']]
        expired_courses = [c for c in courses if c['expired']]
        
        embed = discord.Embed(
            title=f"📋 Season {season['season_number']} Courses",
            color=discord.Color.blue()
        )
        
        if season['title']:
            embed.description = season['title']
        
        # Active courses
        if active_courses:
            active_list = []
            for course in sorted(active_courses, key=lambda x: x['secret_until']):
                expiry = datetime.fromtimestamp(course['secret_until'])
                now = datetime.now()
                
                # Calculate time remaining
                time_diff = expiry - now
                if time_diff.total_seconds() > 0:
                    days = time_diff.days
                    hours = time_diff.seconds // 3600
                    minutes = (time_diff.seconds % 3600) // 60
                    
                    time_str = []
                    if days > 0:
                        time_str.append(f"{days}d")
                    if hours > 0:
                        time_str.append(f"{hours}h")
                    if minutes > 0:
                        time_str.append(f"{minutes}m")
                    
                    time_remaining = " ".join(time_str) if time_str else "< 1m"
                    active_list.append(f"🟢 {course['course_name']} - expires in {time_remaining}")
                else:
                    active_list.append(f"🔴 {course['course_name']} - EXPIRED")
            
            embed.add_field(
                name=f"Active Courses ({len(active_courses)})",
                value="\n".join(active_list) if active_list else "None",
                inline=False
            )
        
        # Expired courses (unless active_only is specified)
        if expired_courses and not active_only:
            expired_list = []
            for course in sorted(expired_courses, key=lambda x: x['secret_until'], reverse=True)[:10]:
                standings_count = len(course['final_standings']['standings']) if course['final_standings'] else 0
                expired_list.append(f"⚫ {course['course_name']} - {standings_count} results")
            
            embed.add_field(
                name=f"Expired Courses ({len(expired_courses)})",
                value="\n".join(expired_list),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in courses command: {e}")
        await interaction.response.send_message("❌ An error occurred while getting courses.", ephemeral=True)

async def handle_test(interaction: discord.Interaction):
    """Handle test command - for development purposes"""
    try:
        season = await db_manager.get_active_season()
        
        embed = discord.Embed(
            title="🧪 Bot Test Results",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Database", value="✅ Connected", inline=True)
        embed.add_field(name="Configuration", value="✅ Loaded", inline=True)
        embed.add_field(name="Active Season", value=f"Season {season['season_number']}" if season else "None", inline=True)
        
        # Test database paths
        import os
        main_db_exists = os.path.exists(config.get("main_db_path"))
        log_file_exists = os.path.exists(config.get("log_file_path"))
        
        embed.add_field(name="Main DB Access", value="✅ Found" if main_db_exists else "❌ Not Found", inline=True)
        embed.add_field(name="Log File Access", value="✅ Found" if log_file_exists else "❌ Not Found", inline=True)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in test command: {e}")
        await interaction.response.send_message("❌ Test failed. Check logs for details.", ephemeral=True)

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    
    logger.error(f"Command error: {error}")

@has_admin_role()
async def handle_config_messages(interaction: discord.Interaction, value: str):
    """Handle config messages command to toggle live messages"""
    if not value or value.lower() not in ['on', 'off', 'enable', 'disable', 'true', 'false']:
        await interaction.response.send_message(
            "❌ Usage: `/secretcourse config messages <on|off>`", 
            ephemeral=True
        )
        return
    
    try:
        enable = value.lower() in ['on', 'enable', 'true']
        config.set("live_messages_enabled", enable)
        
        if enable:
            if not config.get("announcement_channel_id"):
                await interaction.response.send_message(
                    "⚠️ Live messages enabled but no announcement channel set. Use `/secretcourse config channel` first.",
                    ephemeral=True
                )
                return
            
            await message_manager.start_live_updates()
            status = "✅ Live messages enabled and started"
        else:
            await message_manager.stop_live_updates()
            status = "🔴 Live messages disabled and stopped"
        
        embed = discord.Embed(
            title="🔧 Message Configuration Updated",
            description=status,
            color=discord.Color.green() if enable else discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"Live messages {'enabled' if enable else 'disabled'} by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error configuring messages: {e}")
        await interaction.response.send_message("❌ An error occurred while configuring messages.", ephemeral=True)

async def handle_update_messages(interaction: discord.Interaction):
    """Handle manual message update command"""
    try:
        if not config.get("announcement_channel_id"):
            await interaction.response.send_message("❌ No announcement channel configured.", ephemeral=True)
            return
        
        success = await message_manager.force_update()
        
        if success:
            embed = discord.Embed(
                title="✅ Messages Updated",
                description="All live messages have been updated manually.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Update Failed", 
                description="Error occurred while updating messages. Check logs.",
                color=discord.Color.red()
            )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in manual update: {e}")
        await interaction.response.send_message("❌ An error occurred while updating messages.", ephemeral=True)

@has_admin_role()
async def handle_toggle_message(interaction: discord.Interaction, message_type: str, value: str):
    """Handle message type toggles"""
    if not value or value.lower() not in ['on', 'off', 'true', 'false']:
        await interaction.response.send_message(f"❌ Usage: `/secretcourse toggle {message_type} <on|off>`", ephemeral=True)
        return
    
    try:
        enable = value.lower() in ['on', 'true']
        
        # Map command names to config keys
        type_map = {
            "summary": "season_summary",
            "standings": "season_standings", 
            "grid": "course_grid"
        }
        
        config_key = type_map[message_type]
        toggles = config.get("message_toggles", {})
        toggles[config_key] = enable
        config.set("message_toggles", toggles)
        
        status = "enabled" if enable else "disabled"
        embed = discord.Embed(
            title="🔧 Message Toggle Updated",
            description=f"{message_type.title()} messages {status}",
            color=discord.Color.green() if enable else discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"{message_type} messages {status} by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error toggling {message_type}: {e}")
        await interaction.response.send_message("❌ Error updating toggle.", ephemeral=True)

async def handle_debug_logstatus(interaction: discord.Interaction):
    """Handle debug logstatus command - shows log monitoring status"""
    try:
        embed = discord.Embed(
            title="🔍 Log Monitoring Status",
            color=discord.Color.blue()
        )
        
        # Log watcher status
        status = "🟢 Running" if log_watcher.running else "🔴 Stopped"
        embed.add_field(name="Log Watcher", value=status, inline=True)
        
        # File info
        import os
        log_path = config.get("log_file_path")
        if os.path.exists(log_path):
            file_size = os.path.getsize(log_path)
            file_size_mb = round(file_size / 1024 / 1024, 2)
            embed.add_field(name="Log File Size", value=f"{file_size_mb} MB", inline=True)
        else:
            embed.add_field(name="Log File", value="❌ Not Found", inline=True)
        
        # Last position
        embed.add_field(name="Last Position", value=f"{log_watcher.last_position} bytes", inline=True)
        
        # Position file status
        pos_file_exists = os.path.exists(log_watcher.position_file)
        pos_status = "✅ Exists" if pos_file_exists else "❌ Missing"
        embed.add_field(name="Position File", value=pos_status, inline=True)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in debug logstatus: {e}")
        await interaction.response.send_message("❌ Error getting log status.", ephemeral=True)

async def handle_debug_courses(interaction: discord.Interaction):
    """Handle debug courses command - shows current courses in database"""
    try:
        season = await db_manager.get_active_season()
        if not season:
            await interaction.response.send_message("❌ No active season found.", ephemeral=True)
            return
        
        courses = await db_manager.get_active_courses(season['id'])
        
        embed = discord.Embed(
            title=f"📋 Season {season['season_number']} Courses",
            color=discord.Color.blue()
        )
        
        if not courses:
            embed.add_field(name="Courses", value="No courses found", inline=False)
        else:
            active_courses = [c for c in courses if not c['expired']]
            expired_courses = [c for c in courses if c['expired']]
            
            if active_courses:
                active_list = []
                for course in active_courses:
                    # expiry = datetime.fromtimestamp(course['secret_until']).strftime("%m-%d %H:%M")
                    expiry = f"<t:{str(course['secret_until'])}>"
                    active_list.append(f"• {course['course_name']} (expires {expiry})")
                
                embed.add_field(
                    name=f"🟢 Active Courses ({len(active_courses)})",
                    value="\n".join(active_list),
                    inline=False
                )
            
            if expired_courses:
                expired_list = []
                for course in expired_courses:
                    standings_count = len(course['final_standings']['standings']) if course['final_standings'] else 0
                    expired_list.append(f"• {course['course_name']} ({standings_count} results)")
                
                embed.add_field(
                    name=f"🔴 Expired Courses ({len(expired_courses)})", 
                    value="\n".join(expired_list), 
                    inline=False
                )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in debug courses: {e}")
        await interaction.response.send_message("❌ Error getting courses.", ephemeral=True)

class SeasonEndConfirmView(discord.ui.View):
    """Confirmation view for ending seasons"""
    
    def __init__(self, season: Dict, active_courses: List[Dict]):
        super().__init__(timeout=300)
        self.season = season
        self.active_courses = active_courses
    
    @discord.ui.button(label="End Season", style=discord.ButtonStyle.red, emoji="🏁")
    async def confirm_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # End the season
            await db_manager.end_season(self.season['id'])
            
            # Stop live updates
            await message_manager.stop_live_updates()
            
            # Get final leaderboard
            leaderboard = await db_manager.get_season_leaderboard(self.season['id'])
            
            embed = discord.Embed(
                title=f"🏁 Season {self.season['season_number']} Ended",
                color=discord.Color.red()
            )
            
            if self.season['title']:
                embed.add_field(name="Title", value=self.season['title'], inline=False)
            
            embed.add_field(
                name="Duration", 
                value=f"{datetime.fromtimestamp(self.season['start_date']).strftime('%Y-%m-%d')} - {datetime.now().strftime('%Y-%m-%d')}", 
                inline=False
            )
            
            if leaderboard:
                champion = leaderboard[0]
                embed.add_field(
                    name="🏆 Season Champion", 
                    value=f"{champion['username']} - {champion['total_points']} points", 
                    inline=False
                )
                
                if len(leaderboard) > 1:
                    top_5 = leaderboard[:5]
                    top_5_str = "\n".join([f"{p['position']}. {p['username']} - {p['total_points']} pts" for p in top_5])
                    embed.add_field(name="Final Top 5", value=top_5_str, inline=False)
            
            # Clear the view
            self.clear_items()
            await interaction.response.edit_message(embed=embed, view=self)
            
            logger.info(f"Season {self.season['season_number']} ended by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error ending season: {e}")
            await interaction.response.send_message("❌ Error ending season.", ephemeral=True)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, emoji="❌")
    async def cancel_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="✅ Season End Cancelled",
            description=f"Season {self.season['season_number']} will continue.",
            color=discord.Color.green()
        )
        
        self.clear_items()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def on_timeout(self):
        # Disable buttons on timeout
        for item in self.children:
            item.disabled = True

async def main():
    """Main bot startup function"""
    token = config.get("discord_token")
    
    if not token:
        logger.error("No Discord token found in configuration. Please add your bot token to config.json")
        return
    
    try:
        await bot.start(token)
    except discord.LoginFailure:
        logger.error("Invalid Discord token. Please check your token in config.json")
    except Exception as e:
        logger.error(f"An error occurred while starting the bot: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    """Entry point for the bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        logger.info("Bot shutdown complete")