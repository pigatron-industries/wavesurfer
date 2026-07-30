"""A server-side folder browser dialog.

The app server and the browser usually run on the same machine, and project
paths are absolute paths on that machine's filesystem. Browsers don't expose
real filesystem paths from their native folder pickers (for security reasons),
so instead this walks the server's own filesystem and returns the absolute
path the user picks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from nicegui import ui


def _resolve_start(path: str) -> Path:
    if path:
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            return candidate
        if candidate.parent.is_dir():
            return candidate.parent
    return Path.home()


def _subdirs(path: Path) -> list[Path]:
    try:
        entries = [e for e in path.iterdir() if e.is_dir() and not e.name.startswith(".")]
    except (PermissionError, OSError):
        return []
    return sorted(entries, key=lambda e: e.name.lower())


def _files(path: Path, accepted_extensions: list[str] | None = None) -> list[Path]:
    """List files in a directory, optionally filtered by extensions."""
    try:
        entries = [e for e in path.iterdir() if e.is_file() and not e.name.startswith(".")]
        if accepted_extensions:
            entries = [e for e in entries if e.suffix.lower() in accepted_extensions]
    except (PermissionError, OSError):
        return []
    return sorted(entries, key=lambda e: e.name.lower())


async def pick_folder(start_path: str = "") -> str | None:
    """Open a dialog to browse the server's filesystem and pick a folder.

    Returns the chosen absolute path, or ``None`` if the user cancels.
    """
    result: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
    current = {"path": _resolve_start(start_path)}

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[480px]"):
        ui.label("Choose a folder").classes("text-base font-medium")
        path_label = ui.label().classes("text-xs text-gray-500 break-all")
        list_container = ui.column().classes("w-full max-h-80 overflow-y-auto gap-0 mt-1")

        def render() -> None:
            path_label.set_text(str(current["path"]))
            list_container.clear()
            with list_container:
                parent = current["path"].parent
                if parent != current["path"]:
                    ui.button("..", on_click=lambda: navigate(parent)).props(
                        "flat dense no-caps align=left"
                    ).classes("w-full justify-start")
                for entry in _subdirs(current["path"]):
                    ui.button(entry.name, icon="folder", on_click=lambda e=entry: navigate(e)).props(
                        "flat dense no-caps align=left"
                    ).classes("w-full justify-start")

        def navigate(path: Path) -> None:
            current["path"] = path
            render()

        render()

        def finish(value: str | None) -> None:
            if not result.done():
                result.set_result(value)
            dialog.close()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=lambda: finish(None)).props("flat")
            ui.button(
                "Select this folder", on_click=lambda: finish(str(current["path"]))
            ).props("flat")

    dialog.on("hide", lambda: finish(None))
    dialog.open()
    return await result


async def pick_file(
    start_path: str = "",
    accepted_extensions: list[str] | None = None,
    title: str = "Choose a file",
) -> str | None:
    """Open a dialog to browse the server's filesystem and pick a file.

    Args:
        start_path: The starting directory for browsing.
        accepted_extensions: List of file extensions to show (e.g., ['.mp3', '.wav']).
                            If None, all files are shown.
        title: The title displayed in the dialog.

    Returns the chosen absolute file path, or ``None`` if the user cancels.
    """
    result: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
    current = {"path": _resolve_start(start_path)}

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[480px]"):
        ui.label(title).classes("text-base font-medium")
        path_label = ui.label().classes("text-xs text-gray-500 break-all")
        list_container = ui.column().classes("w-full max-h-80 overflow-y-auto gap-0 mt-1")

        def render() -> None:
            path_label.set_text(str(current["path"]))
            list_container.clear()
            with list_container:
                parent = current["path"].parent
                if parent != current["path"]:
                    ui.button("..", on_click=lambda: navigate(parent)).props(
                        "flat dense no-caps align=left"
                    ).classes("w-full justify-start")
                for entry in _subdirs(current["path"]):
                    ui.button(entry.name, icon="folder", on_click=lambda e=entry: navigate(e)).props(
                        "flat dense no-caps align=left"
                    ).classes("w-full justify-start")
                for entry in _files(current["path"], accepted_extensions):
                    ui.button(entry.name, icon="insert_drive_file", on_click=lambda e=entry: select_file(e)).props(
                        "flat dense no-caps align=left"
                    ).classes("w-full justify-start")

        def navigate(path: Path) -> None:
            current["path"] = path
            render()

        def select_file(path: Path) -> None:
            finish(str(path))

        render()

        def finish(value: str | None) -> None:
            if not result.done():
                result.set_result(value)
            dialog.close()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button("Cancel", on_click=lambda: finish(None)).props("flat")

    dialog.on("hide", lambda: finish(None))
    dialog.open()
    return await result
