"""Synchronize JKA exports into bot persistence."""
import time
from secretcourse_types import SyncReport
from secretcourse_source import SecretCourseSourceError

class SecretCourseSynchronizer:
 def __init__(self,source,database):self.source,self.database,self.last_report=source,database,None
 async def sync_once(self):
  try: status=await self.source.load_status()
  except SecretCourseSourceError as e:
   self.last_report=SyncReport(None,int(time.time()),warnings=(str(e),));return self.last_report
  cups=[c for c in status.courses if c.type=='cup']; await self.database.apply_status(status,int(time.time()))
  warnings=[]; finalized=[]
  for c in cups:
   if c.lifecycle=='scheduled':continue
   try: entries=await self.source.load_leaderboard(c,status.revision)
   except SecretCourseSourceError as e:warnings.append(f'{c.id}: {e}');continue
   if c.lifecycle=='expired' and c.finalized_at is not None:
    if await self.database.finalize_course(c.id,c.finalized_at,entries):finalized.append(c.id)
   else: await self.database.replace_live_results(c.id,entries)
  await self.database.mark_missing_courses({c.id for c in cups},int(time.time()))
  self.last_report=SyncReport(status.revision,int(time.time()),len(cups),tuple(finalized),tuple(warnings));return self.last_report
