"""Durable, JKA-ID-keyed storage for imported Secret Course state."""

import sqlite3
import time
from collections import defaultdict
from typing import Sequence

from config import config
from secretcourse_types import LeaderboardEntry, StatusExport


class DatabaseManager:
    def __init__(self, path: str | None = None):
        self.bot_db_path = path or config.get("bot_db_path")

    def _db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.bot_db_path)
        connection.row_factory = sqlite3.Row
        return connection

    async def init_bot_database(self) -> None:
        with self._db() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS sc_imported_seasons (id TEXT PRIMARY KEY, name TEXT NOT NULL, starts_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, revision TEXT NOT NULL, last_seen_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sc_imported_courses (id TEXT PRIMARY KEY, season_id TEXT NOT NULL, course_name TEXT NOT NULL, starts_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, lifecycle TEXT NOT NULL, activated_at INTEGER, finalized_at INTEGER, revision TEXT NOT NULL, last_seen_at INTEGER NOT NULL, retired_at INTEGER, final_imported_at INTEGER, announced_at INTEGER, announcement_claimed_at INTEGER);
                CREATE TABLE IF NOT EXISTS sc_course_results (course_id TEXT NOT NULL, username TEXT NOT NULL, style INTEGER NOT NULL, rank INTEGER NOT NULL, time TEXT NOT NULL, duration_ms INTEGER NOT NULL, topspeed INTEGER NOT NULL, average INTEGER NOT NULL, end_time INTEGER NOT NULL, is_final INTEGER NOT NULL, PRIMARY KEY(course_id, username, style));
                CREATE TABLE IF NOT EXISTS sc_final_points (course_id TEXT NOT NULL, username TEXT NOT NULL, points INTEGER NOT NULL, PRIMARY KEY(course_id, username));
                CREATE TABLE IF NOT EXISTS sc_season_messages (season_id TEXT NOT NULL, message_type TEXT NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(season_id, message_type));
                CREATE TABLE IF NOT EXISTS sc_final_announcement_pages (course_id TEXT NOT NULL, page_index INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(course_id, page_index));
                CREATE TABLE IF NOT EXISTS sc_final_announcement_page_payloads (course_id TEXT NOT NULL, page_index INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(course_id, page_index));
            """)
            columns = {row["name"] for row in database.execute("PRAGMA table_info(sc_imported_courses)")}
            for name in ("announced_at", "announcement_claimed_at"):
                if name not in columns:
                    database.execute(f"ALTER TABLE sc_imported_courses ADD COLUMN {name} INTEGER")

    async def apply_status(self, status: StatusExport, seen_at: int) -> None:
        with self._db() as database:
            for season in status.seasons:
                database.execute("""INSERT INTO sc_imported_seasons VALUES(?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name, starts_at=excluded.starts_at, expires_at=excluded.expires_at, revision=excluded.revision, last_seen_at=excluded.last_seen_at""", (season.id, season.name, season.starts_at, season.expires_at, status.revision, seen_at))
            for course in status.courses:
                if course.type != "cup":
                    continue
                database.execute("""INSERT INTO sc_imported_courses (id,season_id,course_name,starts_at,expires_at,lifecycle,activated_at,finalized_at,revision,last_seen_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET season_id=excluded.season_id, course_name=excluded.course_name, starts_at=excluded.starts_at, expires_at=excluded.expires_at, lifecycle=CASE WHEN excluded.lifecycle='scheduled' THEN 'scheduled' ELSE lifecycle END, activated_at=excluded.activated_at, revision=excluded.revision, last_seen_at=excluded.last_seen_at, retired_at=NULL""", (course.id, course.season_id, course.course_name, course.starts_at, course.expires_at, course.lifecycle, course.activated_at, course.finalized_at, status.revision, seen_at))

    @staticmethod
    def _insert_results(database: sqlite3.Connection, course_id: str, entries: Sequence[LeaderboardEntry], is_final: bool) -> None:
        for rank, entry in enumerate(entries, start=1):
            database.execute("INSERT INTO sc_course_results (course_id,username,style,rank,time,duration_ms,topspeed,average,end_time,is_final) VALUES(?,?,?,?,?,?,?,?,?,?)", (course_id, entry.username, entry.style, rank, entry.time, entry.duration_ms, entry.topspeed, entry.average, entry.end_time, int(is_final)))

    async def replace_live_results(self, course_id: str, entries: Sequence[LeaderboardEntry]) -> None:
        with self._db() as database:
            course = database.execute("SELECT final_imported_at FROM sc_imported_courses WHERE id=?", (course_id,)).fetchone()
            if course is None or course["final_imported_at"] is not None:
                return
            database.execute("DELETE FROM sc_course_results WHERE course_id=? AND is_final=0", (course_id,))
            self._insert_results(database, course_id, entries, False)
            database.execute("UPDATE sc_imported_courses SET lifecycle='active', finalized_at=NULL WHERE id=?", (course_id,))

    async def finalize_course(self, course_id: str, finalized_at: int, entries: Sequence[LeaderboardEntry]) -> bool:
        with self._db() as database:
            course = database.execute("SELECT final_imported_at FROM sc_imported_courses WHERE id=?", (course_id,)).fetchone()
            if course is None or course["final_imported_at"] is not None:
                return False
            database.execute("DELETE FROM sc_course_results WHERE course_id=?", (course_id,))
            database.execute("DELETE FROM sc_final_points WHERE course_id=?", (course_id,))
            self._insert_results(database, course_id, entries, True)
            for rank, entry in enumerate(entries, start=1):
                database.execute("INSERT INTO sc_final_points VALUES(?,?,?)", (course_id, entry.username, self.calculate_points(rank)))
            database.execute("UPDATE sc_imported_courses SET lifecycle='expired', finalized_at=?, final_imported_at=? WHERE id=?", (finalized_at, int(time.time()), course_id))
            return True

    async def mark_missing_courses(self, seen_course_ids: set[str], seen_at: int) -> None:
        with self._db() as database:
            for row in database.execute("SELECT id FROM sc_imported_courses WHERE final_imported_at IS NULL AND lifecycle='active'"):
                if row["id"] not in seen_course_ids:
                    database.execute("UPDATE sc_imported_courses SET lifecycle='cancelled', retired_at=? WHERE id=?", (seen_at, row["id"]))

    async def get_imported_seasons(self) -> list[dict]:
        with self._db() as database:
            return [dict(row) for row in database.execute("SELECT id,name,starts_at,expires_at FROM sc_imported_seasons ORDER BY starts_at,id")]

    async def get_season_courses(self, season_id: str) -> list[dict]:
        with self._db() as database:
            return [dict(row) for row in database.execute("SELECT id,season_id,course_name,starts_at,expires_at,lifecycle,finalized_at FROM sc_imported_courses WHERE season_id=? ORDER BY expires_at,id", (season_id,))]

    async def get_course(self, course_id: str) -> dict | None:
        with self._db() as database:
            row = database.execute("SELECT * FROM sc_imported_courses WHERE id=?", (course_id,)).fetchone()
            return dict(row) if row else None

    async def get_course_results(self, course_id: str) -> list[dict]:
        with self._db() as database:
            return [dict(row) for row in database.execute("SELECT username,rank,time,is_final FROM sc_course_results WHERE course_id=? ORDER BY rank,username", (course_id,))]

    async def get_season_leaderboard(self, season_id: str, include_projections: bool = True) -> list[dict]:
        final_points: dict[str, list[int]] = defaultdict(list)
        projected_points: dict[str, list[int]] = defaultdict(list)
        courses_run: dict[str, set[str]] = defaultdict(set)
        with self._db() as database:
            for row in database.execute("SELECT point.course_id,points,username FROM sc_final_points point JOIN sc_imported_courses course ON course.id=point.course_id WHERE course.season_id=?", (season_id,)):
                final_points[row["username"]].append(row["points"])
                projected_points[row["username"]].append(row["points"])
                courses_run[row["username"]].add(row["course_id"])
            if include_projections:
                for row in database.execute("SELECT result.course_id,result.username,result.rank FROM sc_course_results result JOIN sc_imported_courses course ON course.id=result.course_id WHERE course.season_id=? AND course.lifecycle='active' AND result.is_final=0", (season_id,)):
                    projected_points[row["username"]].append(self.calculate_points(row["rank"]))
                    courses_run[row["username"]].add(row["course_id"])
        best_count = config.get_path("scoring.best_courses_count", 0)
        minimum = config.get_path("scoring.min_courses_required", 0)
        def scored(points):
            values = sorted(points, reverse=True)
            return sum(values[:best_count] if best_count else values)
        usernames = set(final_points) | set(projected_points)
        leaderboard = [{
            "username": username,
            "total_points": scored(final_points[username]),
            "projected_points": scored(projected_points[username]),
            "courses_completed": len(final_points[username]),
            "courses_run": len(courses_run[username]),
            "qualified": not minimum or len(final_points[username]) >= minimum,
        } for username in usernames]
        leaderboard.sort(key=lambda row: (not row["qualified"], -row["total_points"], -row["projected_points"], row["username"]))
        for position, row in enumerate(leaderboard, start=1):
            row["position"] = position
        return leaderboard

    async def get_message(self, season_id: str, message_type: str = "dashboard"):
        with self._db() as database:
            return database.execute("SELECT channel_id,message_id FROM sc_season_messages WHERE season_id=? AND message_type=?", (season_id, message_type)).fetchone()

    async def store_message(self, season_id: str, message_type: str, channel_id: int, message_id: int) -> None:
        with self._db() as database:
            database.execute("""INSERT INTO sc_season_messages VALUES(?,?,?,?)
                ON CONFLICT(season_id,message_type) DO UPDATE SET channel_id=excluded.channel_id,message_id=excluded.message_id""", (season_id, message_type, channel_id, message_id))

    async def delete_message(self, season_id: str, message_type: str) -> None:
        with self._db() as database:
            database.execute("DELETE FROM sc_season_messages WHERE season_id=? AND message_type=?", (season_id, message_type))

    async def claim_final_announcement(self, course_id: str) -> bool:
        with self._db() as database:
            result = database.execute("UPDATE sc_imported_courses SET announcement_claimed_at=? WHERE id=? AND final_imported_at IS NOT NULL AND announced_at IS NULL AND announcement_claimed_at IS NULL", (int(time.time()), course_id))
            return result.rowcount == 1

    async def mark_final_announced(self, course_id: str) -> None:
        with self._db() as database:
            database.execute("UPDATE sc_imported_courses SET announced_at=?, announcement_claimed_at=NULL WHERE id=?", (int(time.time()), course_id))

    async def release_final_announcement(self, course_id: str) -> None:
        with self._db() as database:
            database.execute("UPDATE sc_imported_courses SET announcement_claimed_at=NULL WHERE id=? AND announced_at IS NULL", (course_id,))

    async def release_pending_final_announcement_claims(self) -> None:
        with self._db() as database:
            database.execute("UPDATE sc_imported_courses SET announcement_claimed_at=NULL WHERE announced_at IS NULL")

    async def get_unannounced_final_courses(self) -> list[dict]:
        with self._db() as database:
            return [dict(row) for row in database.execute("SELECT * FROM sc_imported_courses WHERE final_imported_at IS NOT NULL AND announced_at IS NULL")]

    async def get_final_announcement_pages(self, course_id: str) -> set[int]:
        with self._db() as database:
            return {row["page_index"] for row in database.execute("SELECT page_index FROM sc_final_announcement_pages WHERE course_id=?", (course_id,))}

    async def store_final_announcement_page(self, course_id: str, page_index: int, channel_id: int, message_id: int) -> None:
        with self._db() as database:
            database.execute("INSERT OR REPLACE INTO sc_final_announcement_pages VALUES(?,?,?,?)", (course_id, page_index, channel_id, message_id))

    async def get_final_announcement_page_payloads(self, course_id: str) -> list[str]:
        with self._db() as database:
            return [row["payload"] for row in database.execute("SELECT payload FROM sc_final_announcement_page_payloads WHERE course_id=? ORDER BY page_index", (course_id,))]

    async def store_final_announcement_page_payloads(self, course_id: str, payloads: Sequence[str]) -> None:
        with self._db() as database:
            database.executemany("INSERT INTO sc_final_announcement_page_payloads VALUES(?,?,?)", [(course_id, index, payload) for index, payload in enumerate(payloads)])

    @staticmethod
    def calculate_points(position: int) -> int:
        return {1: 30, 2: 25, 3: 21, 4: 18, 5: 16, 6: 14, 7: 12, 8: 10, 9: 8, 10: 6}.get(position, 4 if position <= 15 else 3 if position <= 20 else 2 if position <= 25 else 1 if position <= 30 else 0)


db_manager = DatabaseManager()
