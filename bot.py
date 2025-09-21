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
        
        # Check if Season 1 exists, create if not
        active_season = await db_manager.get_active_season()
        if not active_season:
            logger.info("No active season found, creating Season 1")
            await db_manager.create_season(1, "Haven Climb Cup")
        
        # Setup log watcher with bot reference
        log_watcher.bot = self
        
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
        else:
            await interaction.response.send_message(
                "❌ Available config commands: `channel <channel_id>`, `loglevel <off|minimal|debug>`",
                ephemeral=True
            )
    
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
    
    else:
        await interaction.response.send_message(
            "❌ Available actions: `season`, `config`, `test`, `debug`\n"
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
        
        # TODO: Implement season ending logic in Phase 3
        await interaction.response.send_message("🚧 Season ending functionality will be implemented in Phase 3.", ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error ending season: {e}")
        await interaction.response.send_message("❌ An error occurred while ending the season.", ephemeral=True)

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