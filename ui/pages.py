"""
UI components and pages.
Add your UI elements here.
"""

from bisect import bisect_left
from pathlib import Path
from nicegui import ui
from ui.path_picker import pick_file, pick_file_or_folder
from api.beat_detection import detect_beats_and_downbeats
from api.schema import Downbeat, DownbeatTimeline
from api import state
import asyncio
import queue
from api.thumbnails import get_thumbnail_data_url
from ui.native_drop import drop_queue
import librosa

AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.webm']

PX_PER_SEC = 30  # pixels per second of audio; determines interval box height
MARKER_MATCH_TOLERANCE = 0.05  # seconds; used to test "is this beat also a downbeat/marker"


def _scan_videos(folder: Path) -> list[Path]:
    """Return video/audio files directly inside ``folder``, sorted by name."""
    try:
        entries = [
            e for e in folder.iterdir()
            if e.is_file() and e.suffix.lower() in VIDEO_EXTENSIONS
        ]
    except (PermissionError, OSError):
        return []
    return sorted(entries, key=lambda e: e.name.lower())


@ui.page('/')
def main_page():
    """Main page with toolbar and file picker."""

    selected_path_label = None
    results_container = None
    library_files: list[Path] = []
    thumbnails: dict[str, str | None] = {}   # str(path) -> data URL, or None if extraction failed
    active_path = {'value': None}

    def select_library_file(path: Path):
        active_path['value'] = str(path)
        selected_path_label.set_text(str(path))
        render_library()
        handle_audio_file(str(path), results_container, thumbnails)

    def render_library():
        library_list.clear()
        with library_list:
            if not library_files:
                ui.label('No videos yet — drag files or a folder in').classes('text-sm text-gray-400 italic p-2')
            for video in library_files:
                btn = ui.button(on_click=lambda v=video: select_library_file(v)).props(
                    'flat dense no-caps align=left'
                ).classes('w-full justify-start text-left normal-case')
                with btn:
                    with ui.row().classes('items-start gap-2 w-full flex-nowrap py-1'):
                        thumb = thumbnails.get(str(video))
                        if thumb:
                            ui.image(thumb).classes(
                                'w-10 h-10 object-cover rounded flex-shrink-0'
                            )
                        else:
                            ui.icon('movie').classes('flex-shrink-0 mt-0.5')
                        ui.label(video.name).classes('text-left').style(
                            'white-space: normal; word-break: break-word; line-height: 1.3;'
                        )
                if active_path['value'] == str(video):
                    btn.classes('bg-blue-100 text-blue-800')
                btn.tooltip(str(video))

    async def add_paths_to_library(path_strs: list[str]) -> None:
        """Add one or more filesystem paths (files or folders) to the library.

        Shared by the manual "Add File or Folder" picker and native OS
        drag-and-drop, so both routes stay in sync and dedupe the same way.
        """
        existing = {str(v) for v in library_files}
        new_files: list[Path] = []

        for path_str in path_strs:
            path = Path(path_str)
            if path.is_dir():
                for video in _scan_videos(path):
                    if str(video) not in existing:
                        library_files.append(video)
                        new_files.append(video)
                        existing.add(str(video))
            elif path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and str(path) not in existing:
                library_files.append(path)
                new_files.append(path)
                existing.add(str(path))

        if not new_files:
            return

        library_files.sort(key=lambda e: e.name.lower())
        for video in new_files:
            thumbnails[str(video)] = await asyncio.to_thread(get_thumbnail_data_url, str(video))

        render_library()

    async def on_add_to_library():
        path_str = await pick_file_or_folder(extensions=VIDEO_EXTENSIONS)
        if path_str:
            await add_paths_to_library([path_str])

    def poll_native_drops() -> None:
        while True:
            try:
                entry = drop_queue.get_nowait()
            except queue.Empty:
                break
            else:
                target = entry.get('target', '')
                paths = entry.get('paths', [])
                print(f'got from queue: target={target!r}, paths={paths}', flush=True)
                if target == 'audio':
                    audio_paths = [p for p in paths if Path(p).suffix.lower() in AUDIO_EXTENSIONS]
                    if audio_paths:
                        selected_path_label.set_text(audio_paths[0])
                        handle_audio_file(audio_paths[0], results_container, thumbnails)
                elif target == 'library':
                    asyncio.create_task(add_paths_to_library(paths))
                elif target.startswith('downbeat-'):
                    db_id = int(target.split('-')[1])
                    video_paths = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
                    if video_paths and state.timeline:
                        asyncio.create_task(_handle_downbeat_drop(db_id, video_paths[0], results_container, thumbnails))

    ui.timer(0.3, poll_native_drops)

    # Left sidebar: video library
    with ui.left_drawer(value=True).classes('bg-gray-50 p-2').props('width=280 bordered behavior=desktop') \
            .props('data-drop-target="library"'):
        ui.label('Video Library').classes('text-base font-medium mb-2')
        ui.label('Drag files or a folder here').classes('text-xs text-gray-400 italic mb-1')
        ui.button('Add File or Folder', icon='add', on_click=on_add_to_library).classes('w-full mb-2')
        ui.separator()
        library_list = ui.column().classes('w-full gap-1 overflow-y-auto mt-1')
        render_library()


    # Toolbar at the top — also the native drop target for audio files
    with ui.header().classes('flex items-center p-2 bg-gray-800 text-white') \
            .props('data-drop-target="audio"'):
        with ui.row().classes('gap-4 items-center'):
            async def on_pick():
                file_path = await pick_file(extensions=AUDIO_EXTENSIONS)
                if file_path:
                    selected_path_label.set_text(file_path)
                    handle_audio_file(file_path, results_container, thumbnails)

            ui.button(icon='audiotrack', on_click=on_pick).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0 mr-2')
            selected_path_label = ui.label('Select an audio file to get started').classes('text-sm text-gray-300 truncate max-w-[400px]')

    # Main content area
    with ui.column().classes('w-full h-full items-center justify-center p-4'):
        ui.label('Select an audio file to get started').classes('text-xl text-gray-500')
        results_container = ui.column().classes('w-full max-w-2xl mt-4')


def _is_marker_near(timestamp: float, sorted_markers: list, tolerance: float = MARKER_MATCH_TOLERANCE) -> bool:
    if not sorted_markers:
        return False
    i = bisect_left(sorted_markers, timestamp)
    candidates = sorted_markers[max(0, i - 1):i + 1]
    return any(abs(timestamp - m) < tolerance for m in candidates)


def _render_marker_column(container_classes: str, downbeats: list[Downbeat], timeline_start: float, timeline_height: float,
                           thumbnails: dict, bg_class: str = 'bg-gray-400'):
    """Render downbeat boxes as drop targets with optional video thumbnails."""
    sorted_dbs = sorted(downbeats, key=lambda db: db.time)
    with ui.element('div').classes(container_classes).style(f'height: {timeline_height:.2f}px;'):
        for i in range(len(sorted_dbs) - 1):
            db = sorted_dbs[i]
            top = (db.time - timeline_start) * PX_PER_SEC
            height = (sorted_dbs[i + 1].time - db.time) * PX_PER_SEC
            with ui.element('div') \
                    .classes(f'absolute w-full {bg_class} flex items-center justify-center cursor-pointer') \
                    .style(f'top: {top:.2f}px; height: {height:.2f}px; border: 1px solid black; box-sizing: border-box;') \
                    .props('data-drop-target="downbeat-%d"' % db.id):
                if db.path:
                    thumb = thumbnails.get(db.path)
                    if thumb:
                        ui.image(thumb).classes('w-8 h-8 object-cover rounded')
                    else:
                        ui.icon('movie').classes('text-white text-sm')
                ui.label(f'{db.time:.2f}s').classes('text-white text-xs absolute bottom-0.5 right-1')


def _init_timeline(file_path: str) -> DownbeatTimeline:
    """Create an empty DownbeatTimeline for the given audio file."""
    duration = None
    try:
        y, sr = librosa.load(file_path, sr=None)
        duration = len(y) / sr
    except Exception:
        pass
    timeline = DownbeatTimeline(path=file_path, downbeats=[], duration=duration)
    state.timeline = timeline
    return timeline


def _render_timeline_from_state(results_container: ui.element, thumbnails: dict):
    """Render the UI based on the current state.timeline object."""
    timeline = state.timeline
    if not timeline:
        results_container.clear()
        with results_container:
            ui.label('No audio loaded').classes('text-gray-500')
        return

    downbeats = timeline.downbeats

    # Precompute thumbnails for any downbeat video paths not yet cached.
    # Since we are inside a running event loop, we can't use asyncio.run().
    # Instead, spawn async tasks for any missing thumbnails.
    for db in downbeats:
        if db.path and db.path not in thumbnails:
            asyncio.create_task(_cache_thumbnail(db.path, thumbnails))

    results_container.clear()
    with results_container:
        ui.label(f'Audio: {Path(timeline.path).name}').classes('text-lg font-bold')
        ui.separator()

        # Show metadata
        with ui.row().classes('gap-4'):
            if timeline.tempo is not None:
                with ui.card().classes('w-48 p-2'):
                    ui.label('Tempo').classes('text-sm text-gray-500')
                    ui.label(f"{timeline.tempo:.1f} BPM").classes('text-2xl font-bold')

            with ui.card().classes('w-48 p-2'):
                ui.label('Total Beats').classes('text-sm text-gray-500')
                ui.label(str(len(timeline.beats))).classes('text-2xl font-bold')

            if timeline.duration is not None:
                with ui.card().classes('w-48 p-2'):
                    ui.label('Duration').classes('text-sm text-gray-500')
                    ui.label(f"{timeline.duration:.1f}s").classes('text-2xl font-bold')
            with ui.card().classes('w-48 p-2'):
                ui.label('Downbeats').classes('text-sm text-gray-500')
                ui.label(str(len(downbeats))).classes('text-2xl font-bold')

        # Visual timeline — two columns: beats (left), downbeats (right)
        if timeline.duration is not None and timeline.duration > 0:
            beats = timeline.beats
            timeline_start = beats[0] if beats else 0.0
            timeline_end = beats[-1] if beats else timeline.duration
            total_dur = timeline_end - timeline_start
            timeline_height = total_dur * PX_PER_SEC

            with ui.card().classes('w-full p-2 mt-2 overflow-y-auto'):
                ui.label('Intervals (Left: Beats, Right: Downbeats — drop videos on downbeat boxes)').classes('text-xs text-gray-500 mb-1')

                with ui.row().classes('w-full gap-1 flex-nowrap'):
                    # Left column: beats
                    downbeat_times = [db.time for db in sorted(downbeats, key=lambda db: db.time)]
                    with ui.element('div').classes('flex-1 relative').style(f'height: {timeline_height:.2f}px;'):
                        if len(beats) > 1:
                            for i in range(len(beats) - 1):
                                top = (beats[i] - timeline_start) * PX_PER_SEC
                                height = (beats[i + 1] - beats[i]) * PX_PER_SEC
                                is_marker = _is_marker_near(beats[i], downbeat_times)
                                bg_class = 'bg-gray-400' if is_marker else 'bg-gray-300'
                                with ui.element('div').classes(f'absolute w-full {bg_class} flex items-center justify-center') \
                                        .style(f'top: {top:.2f}px; height: {height:.2f}px; border: 1px solid black; box-sizing: border-box;'):
                                    ui.label(f'{beats[i]:.2f}s').classes('text-white text-xs')
                        else:
                            with ui.element('div').classes('absolute w-full bg-gray-200 flex items-center justify-center') \
                                    .style(f'top: 0; height: {timeline_height:.2f}px; border: 1px solid black; box-sizing: border-box;'):
                                ui.label('No beats').classes('text-gray-500')

                    # Right column: downbeats (drop targets with thumbnails)
                    if len(downbeats) > 1:
                        _render_marker_column('flex-1 relative', downbeats, timeline_start, timeline_height, thumbnails)
                    elif len(downbeats) == 1:
                        db = downbeats[0]
                        with ui.element('div') \
                                .classes('flex-1 relative cursor-pointer') \
                                .style(f'height: {timeline_height:.2f}px;') \
                                .props('data-drop-target="downbeat-%d"' % db.id):
                            if db.path:
                                thumb = thumbnails.get(db.path)
                                if thumb:
                                    ui.image(thumb).classes('w-8 h-8 object-cover rounded absolute') \
                                        .style(f'top: {(db.time - timeline_start) * PX_PER_SEC:.2f}px;')
                                else:
                                    ui.icon('movie').classes('text-white text-sm absolute') \
                                        .style(f'top: {(db.time - timeline_start) * PX_PER_SEC:.2f}px;')
                            ui.label(f'{db.time:.2f}s').classes('text-white text-xs absolute') \
                                .style(f'top: {(db.time - timeline_start) * PX_PER_SEC:.2f}px;')
                    else:
                        with ui.element('div').classes('flex-1 relative').style(f'height: {timeline_height:.2f}px;'):
                            ui.label('No downbeats').classes('text-gray-500 absolute inset-0 flex items-center justify-center')


async def _cache_thumbnail(path: str, thumbnails: dict):
    """Extract a thumbnail for a video and cache it in the thumbnails dict."""
    thumbnails[path] = await asyncio.to_thread(get_thumbnail_data_url, path)


async def _handle_downbeat_drop(db_id: int, video_path: str, results_container: ui.element, thumbnails: dict):
    """Associate a video with a downbeat, extract thumbnail, and re-render."""
    if not state.timeline:
        return
    for db in state.timeline.downbeats:
        if db.id == db_id:
            db.path = video_path
            if db.path not in thumbnails:
                await _cache_thumbnail(db.path, thumbnails)
            _render_timeline_from_state(results_container, thumbnails)
            break


def handle_audio_file(file_path: str, results_container: ui.element, thumbnails: dict):
    """Handle selected audio file: initialise timeline, detect beats, render."""

    # Step 1: initialise empty timeline for this audio file
    timeline = _init_timeline(file_path)

    # Step 2: render empty timeline immediately (shows duration, no downbeats yet)
    _render_timeline_from_state(results_container, thumbnails)

    # Step 3: detect beats and populate downbeats
    try:
        result = detect_beats_and_downbeats(file_path)

        if result.get('success'):
            # Populate the timeline with beats and downbeats
            timeline.tempo = result.get('tempo')
            timeline.beats = result.get('beats', [])
            timeline.downbeats = [
                Downbeat(id=i, time=t)
                for i, t in enumerate(sorted(result.get('downbeats', [])))
            ]
            # Re-render with populated downbeats
            _render_timeline_from_state(results_container, thumbnails)
        else:
            results_container.clear()
            with results_container:
                ui.label('Error detecting beats').classes('text-lg font-bold text-red-600')
                ui.label(result.get('error', 'Unknown error')).classes('text-sm text-red-500')

    except Exception as e:
        results_container.clear()
        with results_container:
            ui.label('Error').classes('text-lg font-bold text-red-600')
            ui.label(str(e)).classes('text-sm text-red-500')