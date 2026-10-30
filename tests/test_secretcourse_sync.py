import tempfile
import unittest
from pathlib import Path

from db_manager import DatabaseManager
from secretcourse_sync import SecretCourseSynchronizer
from secretcourse_types import ExportCourse, ExportSeason, LeaderboardEntry, StatusExport

class SyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_source_failure_returns_health_report(self):
  class Source:
   async def load_status(self):
    from secretcourse_source import SecretCourseSourceError
    raise SecretCourseSourceError('missing')
  report=await SecretCourseSynchronizer(Source(),None).sync_once()
  self.assertEqual(report.warnings,('missing',))
  self.assertFalse(report.successful)

 async def test_expired_course_without_jka_finalization_is_not_loaded_or_scored(self):
  class Source:
   def __init__(self): self.leaderboard_course_ids=[]
   async def load_status(self):
    return StatusExport('rev-1',(ExportSeason('cc-s3','Cup 3',1,100),),(ExportCourse('sumot','Sumo','cup','cc-s3',10,20,'expired',10,None,'private','/leaderboard.json'),))
   async def load_leaderboard(self,course,revision):
    self.leaderboard_course_ids.append(course.id)
    return [LeaderboardEntry('thndr',1,'35.000',35000,2000,600,100)]

  with tempfile.TemporaryDirectory() as directory:
   database=DatabaseManager(str(Path(directory)/'bot.db'))
   await database.init_bot_database()
   source=Source()

   report=await SecretCourseSynchronizer(source,database).sync_once()

   self.assertEqual(source.leaderboard_course_ids, [])
   self.assertEqual(report.finalized_course_ids, ())
   self.assertEqual(await database.get_season_leaderboard('cc-s3'), [])

 async def test_rejected_final_leaderboard_preserves_active_lifecycle_and_projection(self):
  class Source:
   def __init__(self): self.expired=False
   async def load_status(self):
    lifecycle,finalized=('expired',30) if self.expired else ('active',None)
    return StatusExport('rev-1',(ExportSeason('cc-s3','Cup 3',1,100),),(ExportCourse('sumot','Sumo','cup','cc-s3',10,20,lifecycle,10,finalized,'private','/leaderboard.json'),))
   async def load_leaderboard(self,course,revision):
    if self.expired:
     from secretcourse_source import SecretCourseSourceError
     raise SecretCourseSourceError('revision mismatch')
    return [LeaderboardEntry('thndr',1,'35.000',35000,2000,600,100)]

  with tempfile.TemporaryDirectory() as directory:
   database=DatabaseManager(str(Path(directory)/'bot.db'))
   await database.init_bot_database()
   source=Source()
   await SecretCourseSynchronizer(source,database).sync_once()
   source.expired=True
   report=await SecretCourseSynchronizer(source,database).sync_once()

   self.assertEqual(report.warnings, ('sumot: revision mismatch',))
   self.assertEqual((await database.get_season_courses('cc-s3'))[0]['lifecycle'], 'active')
   self.assertEqual((await database.get_season_leaderboard('cc-s3'))[0]['projected_points'], 30)
