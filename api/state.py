"""Shared application state."""

from api.schema import DownbeatTimeline

# Current timeline being edited; None when no audio is loaded.
timeline: DownbeatTimeline | None = None
