import asyncio,discord
from config import config
class MessageManager:
 def __init__(self):self.bot=None;self.sync=None;self.running=False
 def set_bot(self,bot):self.bot=bot
 def set_synchronizer(self,sync):self.sync=sync
 async def start_live_updates(self):
  if self.running:return
  self.running=True
  while self.running:
   await self.update_all_messages();await asyncio.sleep(config.get_path('secretcourses.poll_interval_seconds',30))
 async def update_all_messages(self):
  if not self.sync:return None
  report=await self.sync.sync_once()
  if not self.bot:return report
  for season in await self.sync.database.get_imported_seasons():
   channel_id=config.get_path(f"discord.season_channel_ids.{season['id']}",config.get_path('discord.default_channel_id'))
   channel=self.bot.get_channel(channel_id) if channel_id else None
   if channel:
    courses=await self.sync.database.get_season_courses(season['id'])
    lines=[f"{c['course_name']} — {c['lifecycle']}" for c in courses] or ['No cup courses']
    embed=discord.Embed(title=f"🏆 {season['name']}",description='\n'.join(lines),color=discord.Color.green())
    saved=await self.sync.database.get_message(season['id'])
    try:
     message=await channel.fetch_message(saved[1]) if saved and saved[0]==channel.id else None
    except discord.NotFound: message=None
    if message: await message.edit(embed=embed)
    else:
     message=await channel.send(embed=embed);await self.sync.database.store_message(season['id'],channel.id,message.id)
  return report
 async def force_update(self):await self.update_all_messages();return True
message_manager=MessageManager()
