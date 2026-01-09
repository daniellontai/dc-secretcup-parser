"""
Message formatters for SecretCourse Discord Bot
Handles formatting of live update messages
"""
import discord
from datetime import datetime
from typing import List, Dict, Optional
import math

from config import config

class MessageFormatter:
    """Formats various types of messages for Discord"""
    
    @staticmethod
    def format_time_remaining(timestamp: int) -> str:
        """Format timestamp to countdown string"""
        try:
            expiry = datetime.fromtimestamp(timestamp)
            now = datetime.now()
            time_diff = expiry - now
            
            if time_diff.total_seconds() <= 0:
                return "EXPIRED"
            
            days = time_diff.days
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60
            
            time_parts = []
            if days > 0:
                time_parts.append(f"{days}d")
            if hours > 0:
                time_parts.append(f"{hours}h")
            if minutes > 0:
                time_parts.append(f"{minutes}m")
            
            return " ".join(time_parts) if time_parts else "< 1m"
            
        except Exception:
            return "Unknown"
    
    @staticmethod
    def create_season_summary(season: Dict, leaderboard: List[Dict]) -> discord.Embed:
        """Create the season summary message (message type 1)"""
        embed = discord.Embed(
            title=f"🏆 Season {season['season_number']} - Live Standings",
            color=discord.Color.gold()
        )
        
        # Add subtitle if season has title
        if season.get('title'):
            embed.description = f"**{season['title']}**"
        
        if not leaderboard:
            embed.add_field(name="Top 5", value="No results yet", inline=False)
            return embed
        
        # Top 5 players
        top_5 = leaderboard[:5]
        top_5_text = []
        
        for player in top_5:
            medal = "🥇" if player['position'] == 1 else "🥈" if player['position'] == 2 else "🥉" if player['position'] == 3 else f"{player['position']}."
            top_5_text.append(f"{medal} {player['username']} - {player['total_points']} pts")
        
        embed.add_field(name="Top 5", value="\n".join(top_5_text), inline=False)
        
        # Add spoiler with full rankings if enabled and there are more players
        if config.get("show_spoilers", True) and len(leaderboard) > 5:
            remaining_players = leaderboard[5:]
            remaining_text = []
            
            for player in remaining_players:
                remaining_text.append(f"{player['position']}. {player['username']} - {player['total_points']} pts")
            
            # Discord spoiler limit - split if too long
            remaining_str = "\n".join(remaining_text)
            if len(remaining_str) > 1000:
                remaining_str = remaining_str[:1000] + f"\n... and {len(remaining_players) - remaining_str[:1000].count(chr(10))} more"
            
            embed.add_field(
                name="Full Rankings",
                value=f"||{remaining_str}||",
                inline=False
            )
        
        # Add last updated timestamp
        embed.set_footer(text=f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return embed

    @staticmethod
    def create_season_standings(season: Dict, leaderboard: List[Dict]) -> discord.Embed:
        """Create the detailed season standings table (message type 2)"""
        embed = discord.Embed(
            title=f"📊 Season {season['season_number']} Standings",
            color=discord.Color.blue()
        )
        
        if season.get('title'):
            embed.description = f"**{season['title']}**"
        
        if not leaderboard:
            embed.add_field(name="Standings", value="No results yet", inline=False)
            return embed
        
        # Create table format with new columns
        standings_text = "```\nPos | Player     | Score | Projected | Courses\n"
        standings_text += "    |            |       | Score     | Ran    \n"
        standings_text += "----|------------|-------|-----------|--------\n"
        
        # Show more players in this detailed view
        display_count = min(20, len(leaderboard))
        
        for player in leaderboard[:display_count]:
            # Truncate long usernames
            username = player['username'][:10] if len(player['username']) > 10 else player['username']
            username_padded = f"{username:<10}"
            
            # Current actual score from expired courses
            actual_score = player['total_points']
            
            # Projected score (actual + potential from active courses) 
            projected_score = player.get('projected_points', actual_score)  # Fallback to actual if not calculated
            
            # Courses ran count
            courses_ran = player['courses_completed']
            
            standings_text += f" {player['position']:2d} | {username_padded} | {actual_score:5d} | {projected_score:9d} | {courses_ran:6d}\n"
        
        standings_text += "```"
        
        embed.add_field(name="Detailed Standings", value=standings_text, inline=False)
        
        if len(leaderboard) > display_count:
            embed.add_field(
                name="Total Players",
                value=f"{len(leaderboard)} players competing",
                inline=True
            )
        
        embed.set_footer(text=f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return embed    
 
    @staticmethod 
    def create_course_grid(season: Dict, courses: List[Dict], current_standings: Dict) -> discord.Embed:
        """Create the per-course standings grid (message type 3)"""
        embed = discord.Embed(
            title=f"🗺️ Season {season['season_number']} - Course Progress",
            color=discord.Color.green()
        )
        
        if season.get('title'):
            embed.description = f"**{season['title']}**"
        
        if not courses:
            embed.add_field(name="Courses", value="No courses available", inline=False)
            return embed
        
        # Separate active and expired courses
        active_courses = [c for c in courses if not c['expired']]
        expired_courses = [c for c in courses if c['expired']]
        
        # Sort active by expiry time, expired at the end
        active_courses.sort(key=lambda x: x['secret_until'])
        all_courses = active_courses + expired_courses
        
        # Group courses into rows (3 per row)
        courses_per_row = config.get("courses_per_row", 2)
        course_rows = [all_courses[i:i + courses_per_row] for i in range(0, len(all_courses), courses_per_row)]
        
        for row_index, course_row in enumerate(course_rows):
            # Create course headers with status
            course_columns = []
            
            for course in course_row:
                course_name = course['course_name']
                
                if course['expired']:
                    status = "EXPIRED"
                else:
                    time_remaining = MessageFormatter.format_time_remaining(course['secret_until'])
                    status = f"Expires: {time_remaining}"
                
                # Get standings for this course
                course_standings = current_standings.get(course_name, [])
                
                # Build the column content
                column_lines = [f"{course_name.title()}", status, "-----"]
                
                # Add top 5 players
                top_players = course_standings[:10]
                for standing in top_players:
                    # Handle different field names for active vs expired courses
                    if 'position' in standing:
                        position = standing['position']
                    elif 'rank' in standing:
                        position = standing['rank']
                    else:
                        continue
                    
                    points = MessageFormatter.calculate_points(position)
                    username = standing['username']
                    
                    # Add time for expired courses
                    if course['expired'] and config.get("show_times_expired", True) and 'time_str' in standing:
                        time_str = f"{standing['time_str']}"
                        column_lines.append(f"{(str(position) + '.'):<3} {username[:6]:<6} - {points:<2}pts - {time_str[:7]:<7}")
                    else:
                        column_lines.append(f"{(str(position) + '.'):<3} {username[:10]:<10}")
                
                # Add remaining players in spoiler (positions 6-30)
                # remaining_players = course_standings[5:30]  # Limit to top 30
                # if remaining_players:
                #     spoiler_lines = []
                #     for standing in remaining_players:
                #         # Handle different field names
                #         if 'position' in standing:
                #             position = standing['position']
                #         elif 'rank' in standing:
                #             position = standing['rank']
                #         else:
                #             continue
                        
                #         points = MessageFormatter.calculate_points(position)
                #         username = standing['username']
                        
                #         # Add time for expired courses
                #         if course['expired'] and config.get("show_times_expired", True) and 'time_str' in standing:
                #             time_str = f" - {standing['time_str']}s"
                #             spoiler_lines.append(f"{username} - {points}pts{time_str}")
                #         else:
                #             spoiler_lines.append(f"{username} - {points}pts")
                    
                #     # if spoiler_lines:
                #     #     # Add spoiler content to this column
                #     #     spoiler_text = "\n".join(spoiler_lines)
                #     #     column_lines.append(f"||{spoiler_text}||")
                
                # If no players, show dash
                if len(column_lines) == 2:  # Only header and status
                    column_lines.append("-")
                
                course_columns.append(column_lines)
            
            # Create the formatted output for this row
            row_title = f"Courses {row_index * courses_per_row + 1}-{min((row_index + 1) * courses_per_row, len(all_courses))}"
            
            # Find the maximum number of lines in any column
            max_lines = max(len(column) for column in course_columns)
            
            # Pad shorter columns with empty strings
            for column in course_columns:
                while len(column) < max_lines:
                    column.append("")
            
            # Create the code block format
            formatted_rows = []
            for line_index in range(max_lines):
                row_parts = []
                for column in course_columns:
                    # Get the line for this column, or empty string if column is shorter
                    line_content = column[line_index] if line_index < len(column) else ""
                    # Pad to consistent width (adjust as needed)
                    padded_content = f"{line_content:<25}"
                    row_parts.append(padded_content)
                
                formatted_rows.append(" | ".join(row_parts))
            
            # Join all rows and wrap in code block
            formatted_content = "```\n" + "\n".join(formatted_rows) + "\n```"
            
            embed.add_field(
                name="",
                value=formatted_content,
                inline=False
            )
            
            # Add separator between rows if not last row
            # if row_index < len(course_rows) - 1:
            #     embed.add_field(name="\u200b", value="\u200b", inline=False)
        
        embed.set_footer(text=f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return embed

    @staticmethod
    def calculate_points(position: int) -> int:
        """Calculate points for a given position"""
        points_map = {
            1: 30, 2: 25, 3: 21, 4: 18, 5: 16, 6: 14, 7: 12, 8: 10, 9: 8, 10: 6
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