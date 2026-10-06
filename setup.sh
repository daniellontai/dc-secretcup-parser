#!/bin/bash
set -euo pipefail

echo "Setting up SecretCourse Discord Bot..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
mkdir -p logs

if [ ! -f config.json ]; then
  cp config.json.example config.json
  echo "Created config.json from config.json.example."
fi

echo "Set discord_token, secretcourses.export_root, and discord.default_channel_id in config.json."
