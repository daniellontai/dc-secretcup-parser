#!/bin/bash
# Setup script for SecretCourse Discord Bot

echo "Setting up SecretCourse Discord Bot..."

# Create project directory
PROJECT_DIR="/home/jka/dc-secretcourse-parser"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing Python packages..."
pip install discord.py==2.3.2 watchdog==3.0.0 python-dateutil==2.8.2 aiosqlite==0.19.0

# Create logs directory
mkdir -p logs

# Create initial config.json
echo "Creating initial config.json..."
cat > config.json << 'EOF'
{
  "discord_token": "YOUR_BOT_TOKEN_HERE",
  "main_db_path": "/home/jka/jka-server-staging/taystjk/data.db",
  "log_file_path": "/home/jka/jka-server-staging/logs/jka-server.log",
  "bot_db_path": "./bot_data.db",
  "admin_role": "Admin",
  "update_interval": 300,
  "log_level": "minimal",
  "announcement_channel_id": null,
  "show_times_expired": true,
  "courses_per_row": 3,
  "message_toggles": {
    "season_summary": true,
    "season_standings": true,
    "course_grid": true
  }
}
EOF

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.json and add your Discord bot token"
echo "2. Copy the Python files (bot.py, config.py, db_manager.py) to this directory"
echo "3. Activate the virtual environment: source venv/bin/activate"
echo "4. Run the bot: python bot.py"
echo ""
echo "Project directory: $PROJECT_DIR"