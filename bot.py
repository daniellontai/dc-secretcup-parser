import asyncio,logging
from pathlib import Path
import discord
from discord.ext import commands
from config import config
from db_manager import db_manager
from message_manager import message_manager
from secretcourse_source import SecretCourseSource
from secretcourse_sync import SecretCourseSynchronizer
config.setup_logging();logger=logging.getLogger(__name__)
def is_admin(interaction):
 user=getattr(interaction,'user',None);permissions=getattr(user,'guild_permissions',None)
 if getattr(permissions,'administrator',False):return True
 return any(getattr(role,'name',None)==config.get('admin_role') for role in getattr(user,'roles',()))
class SecretCourseBot(commands.Bot):
 def __init__(self):super().__init__(command_prefix='!',intents=discord.Intents.default(),help_command=None);self.synchronizer=None
 async def setup_hook(self):
  await db_manager.init_bot_database();self.synchronizer=SecretCourseSynchronizer(SecretCourseSource(Path(config.get_path('secretcourses.export_root')),config.get_path('secretcourses.jka_style',1)),db_manager);message_manager.set_bot(self);message_manager.set_synchronizer(self.synchronizer);await self.tree.sync()
 async def on_ready(self):asyncio.create_task(message_manager.start_live_updates())
bot=SecretCourseBot()
@bot.tree.command(name='secretcourse',description='Secret Course commands')
async def secretcourse(interaction:discord.Interaction,action:str,subaction:str=None,value:str=None):
 if action=='update':await message_manager.force_update();await interaction.response.send_message('Updated.',ephemeral=True);return
 if action=='debug' and subaction=='sync':
  r=bot.synchronizer.last_report if bot.synchronizer else None;await interaction.response.send_message('No sync yet.' if not r else f"Revision: {r.revision}; synced: {r.synced_at}; warnings: {'; '.join(r.warnings) or 'none'}",ephemeral=True);return
 if action=='leaderboard' and subaction:
  rows=await db_manager.get_season_leaderboard(subaction);await interaction.response.send_message('\n'.join(f"{x['position']}. {x['username']} — {x['total_points']} pts" for x in rows) or 'No results.');return
 if action=='courses' and subaction:
  courses=await db_manager.get_season_courses(subaction);await interaction.response.send_message('\n'.join(f"{course['course_name']} — {course['lifecycle']}" for course in courses) or 'No imported cup courses.');return
 if action=='config' and subaction=='default-channel':
  if not is_admin(interaction):await interaction.response.send_message('You are not authorized to change configuration.',ephemeral=True);return
  try: channel_id=int(value)
  except (TypeError,ValueError):await interaction.response.send_message('Provide a numeric channel ID.',ephemeral=True);return
  config.set_path('discord.default_channel_id',channel_id);await interaction.response.send_message(f'Default channel set to {channel_id}.',ephemeral=True);return
 if action=='config' and subaction=='season-channel':
  if not is_admin(interaction):await interaction.response.send_message('You are not authorized to change configuration.',ephemeral=True);return
  try: season_id,channel_text=value.split(maxsplit=1);channel_id=int(channel_text)
  except (AttributeError,ValueError):await interaction.response.send_message('Use `config season-channel <season-id> <channel-id>`.',ephemeral=True);return
  config.set_path(f'discord.season_channel_ids.{season_id}',channel_id);await interaction.response.send_message(f'Channel for {season_id} set to {channel_id}.',ephemeral=True);return
 if action=='config' and subaction=='scoring':
  if not is_admin(interaction):await interaction.response.send_message('You are not authorized to change configuration.',ephemeral=True);return
  try: mode,count_text=value.split(maxsplit=1);count=int(count_text);assert mode in {'min','best'} and count>=0
  except (AttributeError,TypeError,ValueError,AssertionError):await interaction.response.send_message('Use `config scoring min|best <non-negative-count>`.',ephemeral=True);return
  key='scoring.min_courses_required' if mode=='min' else 'scoring.best_courses_count'
  config.set_path(key,count);await interaction.response.send_message('Scoring configuration updated.',ephemeral=True);return
 if action=='toggle' and subaction in {'summary','standings','grid'}:
  if not is_admin(interaction):await interaction.response.send_message('You are not authorized to change configuration.',ephemeral=True);return
  if value not in {'on','off'}:await interaction.response.send_message('Use `on` or `off`.',ephemeral=True);return
  key={'summary':'season_summary','standings':'season_standings','grid':'course_grid'}[subaction]
  config.set_path(f'discord.message_toggles.{key}',value=='on');await interaction.response.send_message('Message toggle updated.',ephemeral=True);return
 await interaction.response.send_message('Actions: `update`, `leaderboard <season-id>`, `courses <season-id>`, `debug sync`, `config default-channel <channel-id>`, `config season-channel <season-id> <channel-id>`, `config scoring min|best <count>`, `toggle summary|standings|grid on|off`.',ephemeral=True)
if __name__=='__main__':bot.run(config.get('discord_token'))
