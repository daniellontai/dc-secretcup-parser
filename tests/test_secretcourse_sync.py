import unittest
from secretcourse_sync import SecretCourseSynchronizer
from secretcourse_types import SyncReport

class SyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_source_failure_returns_health_report(self):
  class Source:
   async def load_status(self):
    from secretcourse_source import SecretCourseSourceError
    raise SecretCourseSourceError('missing')
  report=await SecretCourseSynchronizer(Source(),None).sync_once()
  self.assertEqual(report.warnings,('missing',))
