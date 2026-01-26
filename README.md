# SecretCourse Discord Bot

Discord bot for tracking TaystJK game server secret course competitions. Monitors server logs for course events, tracks player scores across seasons, and posts live leaderboard updates to Discord.

## Requirements

- Python 3.11+
- TaystJK game server with accessible log file and database

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd dc-secretcup-parser

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy the example config:

   ```bash
   cp config.json.example config.json
   ```

2. Edit `config.json` with your settings:
   - `discord_token` - Bot token from [Discord Developer Portal](https://discord.com/developers/applications)
   - `main_db_path` - Path to TaystJK game's `data.db`
   - `log_file_path` - Path to TaystJK server log file
   - `bot_db_path` - Path for bot's SQLite database (created automatically)
   - `announcement_channel_id` - Discord channel ID for live messages
   - `admin_role` - Role name required to run admin commands

## Running the Bot

```bash
source venv/bin/activate
python bot.py
```

## Commands

All commands use `/secretcourse <action> [subaction] [value]`.

### Season Management

| Command | Description |
|---------|-------------|
| `season info` | Show current season status and course count |
| `season start <number> [title]` | Start a new season (Admin) |
| `season end` | End the current season with confirmation (Admin) |

### Configuration (Admin)

| Command | Description |
|---------|-------------|
| `config channel <channel_id>` | Set the announcement channel for live messages |
| `config loglevel <off\|minimal\|debug>` | Set bot logging verbosity |
| `config messages <on\|off>` | Enable/disable live message updates |
| `config scoring` | View current scoring settings |
| `config scoring min <number>` | Set minimum courses required to qualify (0 = disabled) |
| `config scoring best <number>` | Only count best N courses (0 = all courses) |

### Message Toggles (Admin)

| Command | Description |
|---------|-------------|
| `toggle summary <on\|off>` | Toggle the season summary message |
| `toggle standings <on\|off>` | Toggle the standings leaderboard message |
| `toggle grid <on\|off>` | Toggle the course grid message |

### Leaderboard & Courses

| Command | Description |
|---------|-------------|
| `leaderboard [season_number]` | Show top 10 leaderboard (current or specified season) |
| `courses [active]` | List all courses (or only active ones) |
| `update` | Force refresh all live messages |

### Debug

| Command | Description |
|---------|-------------|
| `test` | Test bot connectivity and file access |
| `debug logstatus` | Show log watcher status and file position |
| `debug courses` | Show all courses in database with expiry times |

## Starting a New Season

1. **Start the season:**

   ```text
   /secretcourse season start <number> [title]
   ```

   Example: `/secretcourse season start 1 Summer 2024`

2. **Set the announcement channel:**

   ```text
   /secretcourse config channel <channel_id>
   ```

3. **Enable live messages:**

   ```text
   /secretcourse config messages on
   ```

4. **Verify setup:**

   ```text
   /secretcourse season info
   /secretcourse test
   ```

The bot will automatically track courses from server logs and update live leaderboard messages in the configured channel.

For consistency's sake, create the season in the Discord bot first, then add the SecretCourses (/addsecretcourse) on the JKA server.
