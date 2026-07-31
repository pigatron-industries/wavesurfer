from pydantic import BaseModel
from typing import Optional


class Downbeat(BaseModel):
    id: int
    time: float
    path: Optional[str] = None  # Video file path associated with downbeat
    path_outer: Optional[str] = None  # Second video file path (outer column)


class DownbeatTimeline(BaseModel):
    path: str  # Audio file path
    beats: list[float] = []
    downbeats: list[Downbeat] = []
    tempo: Optional[float] = None
    duration: Optional[float] = None
