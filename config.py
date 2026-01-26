"""
Configuration management for SecretCourse Discord Bot
"""
import os
import json
import logging
from pathlib import Path

class Config:
    """Configuration manager for the bot"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from file or create defaults"""
        default_config = {
            "discord_token": "",
            "main_db_path": "/home/jka/jka-server-staging/taystjk/data.db",
            "log_file_path": "/home/jka/jka-server-staging/logs/jka-server.log",
            "bot_db_path": "./bot_data.db",
            "admin_role": "Admin",
            "update_interval": 300,  # 5 minutes in seconds
            "log_level": "minimal",  # off, minimal, debug
            "announcement_channel_id": None,
            "show_times_expired": True,
            "courses_per_row": 2,
            "message_toggles": {
                "season_summary": True,
                "season_standings": True, 
                "course_grid": True
            },
            "live_messages_enabled": False,
            "message_update_interval": 300,  # 5 minutes
            "show_spoilers": True,
            "top_players_count": 5,
            "min_courses_required": 0,  # 0 = disabled (no minimum participation requirement)
            "best_courses_count": 0,    # 0 = all courses count toward score
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            
            self.config = default_config
            self.save_config()
            
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = default_config
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """Set configuration value"""
        self.config[key] = value
        self.save_config()
    
    def setup_logging(self):
        """Setup logging based on configuration"""
        log_level_map = {
            "off": logging.CRITICAL + 1,  # Disable all logging
            "minimal": logging.INFO,
            "debug": logging.DEBUG
        }
        
        log_level = log_level_map.get(self.get("log_level", "minimal"), logging.INFO)
        
        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/bot.log'),
                logging.StreamHandler()  # Also log to console
            ]
        )
        
        # Setup separate error log
        error_handler = logging.FileHandler('logs/error.log')
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        error_handler.setFormatter(error_formatter)
        
        # Add error handler to root logger
        logging.getLogger().addHandler(error_handler)

# Global config instance
config = Config()