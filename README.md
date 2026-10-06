# SecretCourse Discord Bot

Discord bot for tracking TaystJK game server Secret Course competitions. It polls JKA's `secretcourses-status.json` and per-course leaderboard exports, tracks cup scores by JKA season/course IDs, and posts live Discord dashboards.

## Requirements

- Python 3.11+
- JKA Secret Course JSON exports accessible to the bot process

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
   - `secretcourses.export_root` - Directory containing JKA's `secretcourses/` exports
   - `bot_db_path` - Path for bot's SQLite database (created automatically)
   - `discord.default_channel_id` - Shared Discord channel ID for season dashboards
   - `discord.season_channel_ids` - Optional per-JKA-season channel overrides
   - `admin_role` - Role name required to run admin commands

## Running the Bot

```bash
source venv/bin/activate
python bot.py
```

## Commands

All commands use `/secretcourse <action> [subaction] [value]`.

### Configuration (Admin)

| Command | Description |
|---------|-------------|
| `config default-channel <channel_id>` | Set the default dashboard channel |
| `config season-channel <season-id> <channel-id>` | Override the dashboard channel for one JKA season |
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
| `leaderboard <season-id>` | Show a JKA season's standings |
| `courses <season-id>` | List a JKA season's cup courses |
| `update` | Force refresh all live messages |

### Debug

| Command | Description |
|---------|-------------|
| `debug sync` | Show the latest JSON import revision and warning count |

JKA owns course schedules, finalization, and season names. The bot imports only cup courses automatically; permanent courses are ignored. An active course that disappears is cancelled without points, while a finalized snapshot is retained. All seasons use the default channel unless `discord.season_channel_ids` provides an override.
