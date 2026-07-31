from pydantic import BaseModel
from typing import Optional


class Downbeat(BaseModel):
    id: int
    time: float
    path: Optional[str] = None


class DownbeatTimeline(BaseModel):
    downbeats: list[Downbeat] = []
