import sqlite3,time
from config import config
class DatabaseManager:
 def __init__(self,path=None):self.bot_db_path=path or config.get('bot_db_path')
 def _db(self):return sqlite3.connect(self.bot_db_path)
 async def init_bot_database(self):
  with self._db() as d:d.executescript('CREATE TABLE IF NOT EXISTS sc_imported_seasons(id TEXT PRIMARY KEY,name TEXT,starts_at INTEGER,expires_at INTEGER,revision TEXT,last_seen_at INTEGER);CREATE TABLE IF NOT EXISTS sc_imported_courses(id TEXT PRIMARY KEY,season_id TEXT,course_name TEXT,starts_at INTEGER,expires_at INTEGER,lifecycle TEXT,activated_at INTEGER,finalized_at INTEGER,revision TEXT,last_seen_at INTEGER,retired_at INTEGER,final_imported_at INTEGER);CREATE TABLE IF NOT EXISTS sc_course_results(course_id TEXT,username TEXT,style INTEGER,rank INTEGER,time TEXT,duration_ms INTEGER,topspeed INTEGER,average INTEGER,end_time INTEGER,is_final INTEGER,PRIMARY KEY(course_id,username,style));CREATE TABLE IF NOT EXISTS sc_final_points(course_id TEXT,username TEXT,points INTEGER,PRIMARY KEY(course_id,username));')
 async def apply_status(self,s,seen_at):
  with self._db() as d:
   for x in s.seasons:d.execute('INSERT OR REPLACE INTO sc_imported_seasons VALUES(?,?,?,?,?,?)',(x.id,x.name,x.starts_at,x.expires_at,s.revision,seen_at))
   for c in s.courses:
    if c.type=='cup':d.execute('INSERT OR REPLACE INTO sc_imported_courses(id,season_id,course_name,starts_at,expires_at,lifecycle,activated_at,finalized_at,revision,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(c.id,c.season_id,c.course_name,c.starts_at,c.expires_at,c.lifecycle,c.activated_at,c.finalized_at,s.revision,seen_at))
 async def finalize_course(self,id,at,rows):
  with self._db() as d:
   if d.execute('SELECT final_imported_at FROM sc_imported_courses WHERE id=?',(id,)).fetchone()[0] is not None:return False
   d.execute('DELETE FROM sc_course_results WHERE course_id=?',(id,))
   for n,x in enumerate(rows,1):
    d.execute('INSERT INTO sc_course_results VALUES(?,?,?,?,?,?,?,?,?,1)',(id,x.username,x.style,n,x.time,x.duration_ms,x.topspeed,x.average,x.end_time));d.execute('INSERT INTO sc_final_points VALUES(?,?,?)',(id,x.username,self.calculate_points(n)))
   d.execute("UPDATE sc_imported_courses SET lifecycle='expired',finalized_at=?,final_imported_at=? WHERE id=?",(at,int(time.time()),id));return True
 async def replace_live_results(self,course_id,entries):
  with self._db() as d:
   row=d.execute('SELECT final_imported_at FROM sc_imported_courses WHERE id=?',(course_id,)).fetchone()
   if row and row[0] is None:
    d.execute('DELETE FROM sc_course_results WHERE course_id=?',(course_id,))
    for n,x in enumerate(entries,1):d.execute('INSERT INTO sc_course_results VALUES(?,?,?,?,?,?,?,?,?,0)',(course_id,x.username,x.style,n,x.time,x.duration_ms,x.topspeed,x.average,x.end_time))
 async def mark_missing_courses(self,seen_course_ids,seen_at):
  with self._db() as d:
   for (id,) in d.execute('SELECT id FROM sc_imported_courses WHERE final_imported_at IS NULL'):
    if id not in seen_course_ids:d.execute("UPDATE sc_imported_courses SET lifecycle='cancelled',retired_at=? WHERE id=?",(seen_at,id))
 async def get_season_courses(self,s):
  with self._db() as d:return [dict(zip(('id','course_name','starts_at','expires_at','lifecycle','finalized_at'),r)) for r in d.execute('SELECT id,course_name,starts_at,expires_at,lifecycle,finalized_at FROM sc_imported_courses WHERE season_id=?',(s,))]
 async def get_imported_seasons(self):
  with self._db() as d:return [dict(zip(('id','name','starts_at','expires_at'),r)) for r in d.execute('SELECT id,name,starts_at,expires_at FROM sc_imported_seasons ORDER BY starts_at,id')]
 async def get_season_leaderboard(self,s,include_projections=True):
  with self._db() as d:r=d.execute('SELECT username,points FROM sc_final_points p JOIN sc_imported_courses c ON c.id=p.course_id WHERE c.season_id=?',(s,)).fetchall()
  x={}
  for n,p in r:x.setdefault(n,[]).append(p)
  o=[{'username':n,'total_points':sum(v),'projected_points':sum(v),'courses_completed':len(v)} for n,v in x.items()];o.sort(key=lambda z:(-z['total_points'],z['username']))
  for n,z in enumerate(o,1):z['position']=n
  return o
 @staticmethod
 def calculate_points(n):return {1:30,2:25,3:21,4:18,5:16,6:14,7:12,8:10,9:8,10:6}.get(n,4 if n<=15 else 3 if n<=20 else 2 if n<=25 else 1 if n<=30 else 0)
db_manager=DatabaseManager()
