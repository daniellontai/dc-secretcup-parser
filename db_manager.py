"""
Database manager for SecretCourse Discord Bot
Handles both bot's own database and reading from main TaystJK database
"""
import aiosqlite
import sqlite3
import logging
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages all database operations for the bot"""
    
    def __init__(self):
        self.bot_db_path = config.get("bot_db_path")
        self.main_db_path = config.get("main_db_path")
    
    async def init_bot_database(self):
        """Initialize the bot's SQLite database with required tables"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                # Seasons table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS seasons (
                        id INTEGER PRIMARY KEY,
                        season_number INTEGER UNIQUE,
                        title TEXT,
                        start_date INTEGER,
                        end_date INTEGER,
                        is_active BOOLEAN DEFAULT FALSE
                    )
                """)
                
                # Season courses table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS season_courses (
                        id INTEGER PRIMARY KEY,
                        season_id INTEGER,
                        course_name TEXT,
                        full_course_name TEXT,
                        secret_until INTEGER,
                        expired BOOLEAN DEFAULT FALSE,
                        final_standings TEXT,
                        FOREIGN KEY (season_id) REFERENCES seasons (id)
                    )
                """)
                
                # Player scores table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS player_scores (
                        id INTEGER PRIMARY KEY,
                        season_id INTEGER,
                        player_name TEXT,
                        total_points INTEGER DEFAULT 0,
                        courses_completed INTEGER DEFAULT 0,
                        FOREIGN KEY (season_id) REFERENCES seasons (id),
                        UNIQUE(season_id, player_name)
                    )
                """)
                
                # Course results table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS course_results (
                        id INTEGER PRIMARY KEY,
                        season_id INTEGER,
                        course_name TEXT,
                        player_name TEXT,
                        position INTEGER,
                        points INTEGER,
                        duration_ms INTEGER,
                        time_str TEXT,
                        FOREIGN KEY (season_id) REFERENCES seasons (id)
                    )
                """)
                
                # Bot messages table for Discord message tracking
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS bot_messages (
                        id INTEGER PRIMARY KEY,
                        message_type TEXT,
                        channel_id INTEGER,
                        message_id INTEGER,
                        season_id INTEGER,
                        created_at INTEGER
                    )
                """)
                
                await db.commit()
                logger.info("Bot database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing bot database: {e}")
            raise
    
    async def create_season(self, season_number: int, title: str = None) -> int:
        """Create a new season and return its ID"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                # Deactivate any existing active seasons
                await db.execute("UPDATE seasons SET is_active = FALSE WHERE is_active = TRUE")
                
                # Create new season
                start_time = int(datetime.now().timestamp())
                cursor = await db.execute("""
                    INSERT INTO seasons (season_number, title, start_date, is_active)
                    VALUES (?, ?, ?, TRUE)
                """, (season_number, title, start_time))
                
                await db.commit()
                season_id = cursor.lastrowid
                
                logger.info(f"Created season {season_number} with ID {season_id}")
                return season_id
                
        except Exception as e:
            logger.error(f"Error creating season: {e}")
            raise
    
    async def get_active_season(self) -> Optional[Dict]:
        """Get the currently active season"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                cursor = await db.execute("""
                    SELECT id, season_number, title, start_date, end_date
                    FROM seasons WHERE is_active = TRUE
                """)
                
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'season_number': row[1],
                        'title': row[2],
                        'start_date': row[3],
                        'end_date': row[4]
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting active season: {e}")
            return None
    
    async def add_season_course(self, season_id: int, full_course_name: str, secret_until: int):
        """Add a course to the current season"""
        try:
            # Extract course name from full name (part in parentheses)
            course_name = full_course_name.split('(')[1].split(')')[0] if '(' in full_course_name else full_course_name
            
            async with aiosqlite.connect(self.bot_db_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO season_courses 
                    (season_id, course_name, full_course_name, secret_until, expired)
                    VALUES (?, ?, ?, ?, FALSE)
                """, (season_id, course_name, full_course_name, secret_until))
                
                await db.commit()
                logger.info(f"Added course {full_course_name} to season {season_id}")
                
        except Exception as e:
            logger.error(f"Error adding season course: {e}")
            raise
    
    async def expire_course(self, full_course_name: str, standings_data: Dict):
        """Mark a course as expired and store final standings"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                # Get active season
                season = await self.get_active_season()
                if not season:
                    logger.warning("No active season found when expiring course")
                    return
                
                # Update course as expired
                await db.execute("""
                    UPDATE season_courses 
                    SET expired = TRUE, final_standings = ?
                    WHERE full_course_name = ? AND season_id = ?
                """, (json.dumps(standings_data), full_course_name, season['id']))
                
                # Store individual results and calculate points
                course_name = full_course_name.split('(')[1].split(')')[0] if '(' in full_course_name else full_course_name
                
                for result in standings_data.get('standings', []):
                    points = self.calculate_points(result['rank'])
                    
                    # Store course result
                    await db.execute("""
                        INSERT INTO course_results 
                        (season_id, course_name, player_name, position, points, duration_ms, time_str)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (season['id'], course_name, result['username'], result['rank'], 
                          points, result['duration_ms'], result['time_str']))
                    
                    # Update player total score
                    await db.execute("""
                        INSERT INTO player_scores (season_id, player_name, total_points, courses_completed)
                        VALUES (?, ?, ?, 1)
                        ON CONFLICT(season_id, player_name) DO UPDATE SET
                            total_points = total_points + ?,
                            courses_completed = courses_completed + 1
                    """, (season['id'], result['username'], points, points))
                
                await db.commit()
                logger.info(f"Course {full_course_name} marked as expired with {len(standings_data.get('standings', []))} results")
                
        except Exception as e:
            logger.error(f"Error expiring course: {e}")
            raise
    
    def calculate_points(self, position: int) -> int:
        """Calculate points based on position using Formula 1 style scoring"""
        points_map = {
            1: 30, 2: 25, 3: 20, 4: 18, 5: 16, 6: 14, 7: 12, 8: 10, 9: 8, 10: 6
        }
        
        if position <= 10:
            return points_map[position]
        elif position <= 15:
            return 4
        elif position <= 20:
            return 3
        elif position <= 25:
            return 2
        elif position <= 30:
            return 1
        else:
            return 0
    
    async def get_current_standings(self, course_name: str) -> List[Dict]:
        """Get current standings for a course from main database"""
        try:
            async with aiosqlite.connect(self.main_db_path) as db:
                cursor = await db.execute("""
                    SELECT username, MIN(duration_ms) AS duration, 
                           ROW_NUMBER() OVER (ORDER BY MIN(duration_ms)) AS position
                    FROM LocalRun 
                    WHERE coursename = ? AND style = 1 AND invalid = 0
                    GROUP BY username 
                    ORDER BY duration
                """, (course_name,))
                
                results = []
                async for row in cursor:
                    results.append({
                        'username': row[0],
                        'duration_ms': row[1],
                        'position': row[2]
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting current standings for {course_name}: {e}")
            return []
    
    async def get_season_leaderboard(self, season_id: int) -> List[Dict]:
        """Get overall season leaderboard"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                cursor = await db.execute("""
                    SELECT player_name, total_points, courses_completed
                    FROM player_scores 
                    WHERE season_id = ?
                    ORDER BY total_points DESC, courses_completed DESC
                """, (season_id,))
                
                results = []
                position = 1
                async for row in cursor:
                    results.append({
                        'position': position,
                        'username': row[0],
                        'total_points': row[1],
                        'courses_completed': row[2]
                    })
                    position += 1
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting season leaderboard: {e}")
            return []
    
    async def get_active_courses(self, season_id: int) -> List[Dict]:
        """Get all courses for the active season"""
        try:
            async with aiosqlite.connect(self.bot_db_path) as db:
                cursor = await db.execute("""
                    SELECT course_name, full_course_name, secret_until, expired, final_standings
                    FROM season_courses 
                    WHERE season_id = ?
                    ORDER BY secret_until ASC
                """, (season_id,))
                
                results = []
                async for row in cursor:
                    final_standings = json.loads(row[4]) if row[4] else None
                    results.append({
                        'course_name': row[0],
                        'full_course_name': row[1],
                        'secret_until': row[2],
                        'expired': bool(row[3]),
                        'final_standings': final_standings
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting active courses: {e}")
            return []

# Global database manager instance
db_manager = DatabaseManager()