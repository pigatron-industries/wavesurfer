"""A server-side folder/file browser dialog.

The app server and the browser usually run on the same machine, and project
paths are absolute paths on that machine's filesystem. Browsers don't expose
real filesystem paths from their native folder pickers (for security reasons),
so instead this walks the server's own filesystem and returns the absolute
path the user picks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from nicegui import ui


def _resolve_start(path: str) -> Path:
    if path:
        candidate = Path(path).expanduser()
        if candidate.is_dir():
            return candidate
        if candidate.parent.is_dir():
            return candidate.parent
    return Path.home()


def _normalize_extensions(extensions: Sequence[str] | None) -> set[str] | None:
    if not extensions:
        return None
    return {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}


def _volumes() -> list[Path]:
    volumes = Path("/Volumes")
    try:
        entries = [e for e in volumes.iterdir() if e.is_dir()]
    except (PermissionError, OSError):
        return []
    return sorted(entries, key=lambda e: e.name.lower())


def _entries(path: Path, *, include_files: bool, extensions: set[str] | None) -> tuple[list[Path], list[Path]]:
    try:
        children = [e for e in path.iterdir() if not e.name.startswith(".")]
    except (PermissionError, OSError):
        return [], []
    dirs = sorted((e for e in children if e.is_dir()), key=lambda e: e.name.lower())
    if not include_files:
        return dirs, []
    files = [e for e in children if e.is_file() and (extensions is None or e.suffix.lower() in extensions)]
    return dirs, sorted(files, key=lambda e: e.name.lower())


async def pick_path(
    start_path: str = "",
    *,
    mode: Literal["folder", "file", "any"] = "folder",
    extensions: Sequence[str] | None = None,
    default_filename: str | None = None,
) -> str | None:
    """Open a dialog to browse the server's filesystem and pick a folder or file.

    ``extensions`` (e.g. ``[".py", "txt"]``) restricts which files are shown and
    is used when ``mode`` is ``"file"`` or ``"any"``.

    ``mode="any"`` lets the user either click a file to select it directly,
    or click "Select this folder" to pick the current directory instead.

    When ``default_filename`` is provided, the dialog enters *save* mode:
    a filename input is shown at the bottom, clicking a file pre-fills that
    input (so the user can overwrite it), and the confirm button saves to
    ``current_dir / filename``.

    Returns the chosen absolute path, or ``None`` if the user cancels.
    """
    result: asyncio.Future[str | None] = asyncio.get_event_loop().create_future()
    current = {"path": _resolve_start(start_path)}
    normalized_extensions = _normalize_extensions(extensions)
    is_save_mode = default_filename is not None

    titles = {
        "folder": "Choose a folder",
        "file": "Choose a file",
        "any": "Choose a file or folder",
    }

    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[480px]"):
        ui.label(titles.get(mode, "Choose")).classes("text-base font-medium")

        volumes = _volumes()
        if len(volumes) >= 2:
            with ui.row().classes("w-full gap-1 mt-1"):
                for volume in volumes:
                    with ui.column().classes("items-center gap-0 w-14"):
                        ui.button(icon="storage", on_click=lambda v=volume: navigate(v)).props(
                            "flat dense round size=sm"
                        ).tooltip(volume.name)
                        ui.label(volume.name).classes(
                            "text-[10px] text-gray-500 w-full text-center truncate"
                        ).tooltip(volume.name)

        path_label = ui.label().classes("text-xs text-gray-500 break-all")
        list_container = ui.column().classes("w-full max-h-64 overflow-y-auto gap-1 mt-1")

        # Filename input for save mode
        name_input = None
        if is_save_mode:
            name_input = ui.input("File name", value=default_filename).props("autocomplete=off").classes("w-full")

        def make_row_button(label_text: str, icon_name: str | None, on_click):
            b = ui.button(on_click=on_click).props(
                "flat dense no-caps align=left"
            ).classes("w-full justify-start normal-case")
            with b:
                with ui.row().classes("items-start gap-2 w-full flex-nowrap py-1"):
                    if icon_name:
                        ui.icon(icon_name).classes("flex-shrink-0 mt-0.5")
                    ui.label(label_text).classes("text-left").style(
                        "white-space: normal; word-break: break-word; line-height: 1.3;"
                    )
            return b

        def render() -> None:
            path_label.set_text(str(current["path"]))
            list_container.clear()

            with list_container:
                parent = current["path"].parent
                if parent != current["path"]:
                    make_row_button("..", None, lambda: navigate(parent))
                dirs, files = _entries(
                    current["path"],
                    include_files=mode in ("file", "any") or is_save_mode,
                    extensions=normalized_extensions,
                )
                for entry in dirs:
                    make_row_button(entry.name, "folder", lambda e=entry: navigate(e))
                for entry in files:
                    if is_save_mode and name_input is not None:
                        # In save mode, clicking a file pre-fills the name input
                        make_row_button(
                            entry.name, "description",
                            lambda e=entry: name_input.set_value(e.name),
                        )
                    else:
                        make_row_button(entry.name, "description", lambda e=entry: finish(str(e)))

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
            if is_save_mode and name_input is not None:
                ui.button(
                    "Save",
                    on_click=lambda: finish(
                        str(current["path"] / (name_input.value or ""))
                    ),
                ).props("color=primary")
            elif mode in ("folder", "any"):
                ui.button(
                    "Select this folder", on_click=lambda: finish(str(current["path"]))
                ).props("flat")

    dialog.on("hide", lambda: finish(None))
    dialog.open()
    return await result


async def pick_folder(start_path: str = "") -> str | None:
    """Open a dialog to browse the server's filesystem and pick a folder."""
    return await pick_path(start_path, mode="folder")


async def pick_file(start_path: str = "", extensions: Sequence[str] | None = None) -> str | None:
    """Open a dialog to browse the server's filesystem and pick a file.

    ``extensions`` (e.g. ``[".py", "txt"]``) restricts which files are shown.
    """
    return await pick_path(start_path, mode="file", extensions=extensions)


async def pick_file_or_folder(
    start_path: str = "", extensions: Sequence[str] | None = None
) -> str | None:
    """Open a dialog letting the user pick either a single file or an entire folder."""
    return await pick_path(start_path, mode="any", extensions=extensions)
