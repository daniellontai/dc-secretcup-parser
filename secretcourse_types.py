"""Typed contracts for JKA Secret Course JSON exports."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExportSeason:
    id: str
    name: str
    starts_at: int
    expires_at: int


@dataclass(frozen=True)
class ExportCourse:
    id: str
    course_name: str
    type: str
    season_id: Optional[str]
    starts_at: int
    expires_at: Optional[int]
    lifecycle: str
    activated_at: Optional[int]
    finalized_at: Optional[int]
    demos_visibility: str
    leaderboard_path: str


@dataclass(frozen=True)
class LeaderboardEntry:
    username: str
    style: int
    time: str
    duration_ms: int
    topspeed: int
    average: int
    end_time: int


@dataclass(frozen=True)
class StatusExport:
    revision: str
    seasons: tuple[ExportSeason, ...]
    courses: tuple[ExportCourse, ...]


@dataclass(frozen=True)
class SyncReport:
    revision: Optional[str]
    synced_at: int
    imported_courses: int = 0
    finalized_course_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    successful: bool = True
