"""Safe filesystem reader for JKA Secret Course JSON exports."""
import json
from pathlib import Path
from typing import Any, Optional

from secretcourse_types import (
    ExportCourse,
    ExportSeason,
    LeaderboardEntry,
    StatusExport,
)


class SecretCourseSourceError(RuntimeError):
    """Raised when a JKA export cannot be safely consumed."""


class SecretCourseSource:
    """Loads JKA status and leaderboard JSON below one trusted export root."""

    def __init__(self, export_root: Path, jka_style: int = 1):
        self.export_root = Path(export_root).resolve()
        self.jka_style = jka_style
        self.status_path = self.export_root / "secretcourses" / "secretcourses-status.json"

    async def load_status(self) -> StatusExport:
        payload = await self._load_json(self.status_path)
        self._require(payload.get("schema_version") == 2, "unsupported status schema version")
        revision = self._string(payload, "revision")
        seasons = tuple(self._parse_season(item) for item in self._array(payload, "seasons"))
        courses = tuple(self._parse_course(item) for item in self._array(payload, "courses"))
        return StatusExport(revision=revision, seasons=seasons, courses=courses)

    async def load_leaderboard(self, course: ExportCourse, revision: str) -> list[LeaderboardEntry]:
        path = self._resolve_leaderboard_path(course.leaderboard_path)
        payload = await self._load_json(path)
        self._require(payload.get("schema_version") == 1, "unsupported leaderboard schema version")
        self._require(self._string(payload, "revision") == revision, "leaderboard revision mismatch")
        self._require(self._string(payload, "course_id") == course.id, "leaderboard course ID mismatch")
        entries = [self._parse_entry(item) for item in self._array(payload, "entries")]
        return [entry for entry in entries if entry.style == self.jka_style]

    async def _load_json(self, path: Path) -> dict[str, Any]:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.export_root)
        except ValueError as error:
            raise SecretCourseSourceError(f"JSON export path escapes export root: {path}") from error
        try:
            text = resolved.read_text(encoding="utf-8")
            payload = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SecretCourseSourceError(f"could not read JSON export {resolved}: {error}") from error
        if not isinstance(payload, dict):
            raise SecretCourseSourceError(f"JSON export {path} must contain an object")
        return payload

    def _resolve_leaderboard_path(self, leaderboard_path: str) -> Path:
        if not isinstance(leaderboard_path, str) or not leaderboard_path.startswith("/"):
            raise SecretCourseSourceError("leaderboard path must be absolute within export root")
        resolved = (self.export_root / leaderboard_path.lstrip("/")).resolve()
        try:
            resolved.relative_to(self.export_root)
        except ValueError as error:
            raise SecretCourseSourceError("leaderboard path escapes export root") from error
        return resolved

    def _parse_season(self, payload: Any) -> ExportSeason:
        self._require(isinstance(payload, dict), "season must be an object")
        return ExportSeason(
            id=self._string(payload, "id"),
            name=self._string(payload, "name"),
            starts_at=self._integer(payload, "starts_at"),
            expires_at=self._integer(payload, "expires_at"),
        )

    def _parse_course(self, payload: Any) -> ExportCourse:
        self._require(isinstance(payload, dict), "course must be an object")
        course_type = self._string(payload, "type")
        self._require(course_type in {"cup", "permanent"}, "unsupported course type")
        season_id = self._nullable_string(payload, "season_id")
        expires_at = self._nullable_integer(payload, "expires_at")
        if course_type == "cup":
            self._require(season_id is not None, "cup course requires a season ID")
            self._require(expires_at is not None, "cup course requires an expiry")
        else:
            self._require(season_id is None, "permanent course cannot have a season ID")
            self._require(expires_at is None, "permanent course cannot have an expiry")

        lifecycle = self._string(payload, "lifecycle")
        self._require(lifecycle in {"scheduled", "active", "expired"}, "unsupported course lifecycle")
        return ExportCourse(
            id=self._string(payload, "id"),
            course_name=self._string(payload, "course_name"),
            type=course_type,
            season_id=season_id,
            starts_at=self._integer(payload, "starts_at"),
            expires_at=expires_at,
            lifecycle=lifecycle,
            activated_at=self._nullable_integer(payload, "activated_at"),
            finalized_at=self._nullable_integer(payload, "finalized_at"),
            demos_visibility=self._string(payload, "demos_visibility"),
            leaderboard_path=self._string(payload, "leaderboard_path"),
        )

    def _parse_entry(self, payload: Any) -> LeaderboardEntry:
        self._require(isinstance(payload, dict), "leaderboard entry must be an object")
        return LeaderboardEntry(
            username=self._string(payload, "username"),
            style=self._integer(payload, "style"),
            time=self._string(payload, "time"),
            duration_ms=self._integer(payload, "duration_ms"),
            topspeed=self._integer(payload, "topspeed"),
            average=self._integer(payload, "average"),
            end_time=self._integer(payload, "end_time"),
        )

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise SecretCourseSourceError(message)

    def _array(self, payload: dict[str, Any], key: str) -> list[Any]:
        value = payload.get(key)
        self._require(isinstance(value, list), f"{key} must be an array")
        return value

    def _string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        self._require(isinstance(value, str) and bool(value), f"{key} must be a non-empty string")
        return value

    def _nullable_string(self, payload: dict[str, Any], key: str) -> Optional[str]:
        value = payload.get(key)
        self._require(value is None or (isinstance(value, str) and bool(value)), f"{key} must be a string or null")
        return value

    def _integer(self, payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        self._require(isinstance(value, int) and not isinstance(value, bool), f"{key} must be an integer")
        return value

    def _nullable_integer(self, payload: dict[str, Any], key: str) -> Optional[int]:
        value = payload.get(key)
        self._require(value is None or (isinstance(value, int) and not isinstance(value, bool)), f"{key} must be an integer or null")
        return value
