"""
Configuration management for SecretCourse Discord Bot
"""
import os
import json
import logging
from pathlib import Path
from typing import Any

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
            "bot_db_path": "./bot_data.db",
            "admin_role": "Admin",
            "log_level": "minimal",  # off, minimal, debug
            "secretcourses": {
                "export_root": "/srv/jka/taystjk",
                "poll_interval_seconds": 30,
                "jka_style": 1,
            },
            "discord": {
                "default_channel_id": None,
                "season_channel_ids": {},
                "top_players_count": 10,
                "courses_per_row": 2,
                "show_scheduled_courses": True,
                "show_final_times": True,
                "message_toggles": {
                    "season_summary": True,
                    "season_standings": True,
                    "course_grid": True,
                },
            },
            "scoring": {
                "min_courses_required": 0,
                "best_courses_count": 0,
            },
        }
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    self._merge_defaults(default_config, loaded_config)
            
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

    @staticmethod
    def _merge_defaults(defaults: dict, overrides: dict) -> None:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(defaults.get(key), dict):
                Config._merge_defaults(defaults[key], value)
            else:
                defaults[key] = value

    def get_path(self, path: str, default: Any = None) -> Any:
        """Return a nested configuration value addressed with dots."""
        value: Any = self.config
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                return default
            value = value[part]
        return value

    def set_path(self, path: str, value: Any) -> None:
        """Set a nested configuration value without replacing sibling keys."""
        parts = path.split(".")
        target = self.config
        for part in parts[:-1]:
            child = target.get(part)
            if not isinstance(child, dict):
                child = {}
                target[part] = child
            target = child
        target[parts[-1]] = value
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
