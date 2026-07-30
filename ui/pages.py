"""
UI components and pages.
Add your UI elements here.
"""

from bisect import bisect_left
from pathlib import Path
from nicegui import ui
from ui.path_picker import pick_file, pick_file_or_folder
from api.beat_detection import detect_beats_and_downbeats
import asyncio
from api.thumbnails import get_thumbnail_data_url


AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.webm']

TIMELINE_HEIGHT_PX = 3800
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
        handle_audio_file(str(path), results_container)

    def render_library():
        library_list.clear()
        with library_list:
            if not library_files:
                ui.label('No videos yet').classes('text-sm text-gray-400 italic p-2')
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

    async def on_add_to_library():
        path_str = await pick_file_or_folder(extensions=VIDEO_EXTENSIONS)
        if not path_str:
            return
        path = Path(path_str)
        existing = {str(v) for v in library_files}
        new_files: list[Path] = []
        if path.is_dir():
            for video in _scan_videos(path):
                if str(video) not in existing:
                    library_files.append(video)
                    new_files.append(video)
        elif path.is_file() and str(path) not in existing:
            library_files.append(path)
            new_files.append(path)
        library_files.sort(key=lambda e: e.name.lower())

        for video in new_files:
            thumbnails[str(video)] = await asyncio.to_thread(get_thumbnail_data_url, str(video))

        render_library()


    # Left sidebar: video library
    with ui.left_drawer(value=True).classes('bg-gray-50 p-2').props('width=280 bordered'):
        ui.label('Video Library').classes('text-base font-medium mb-2')
        ui.button('Add File or Folder', icon='add', on_click=on_add_to_library).classes('w-full mb-2')
        ui.separator()
        library_list = ui.column().classes('w-full gap-1 overflow-y-auto mt-1')
        render_library()


    # Toolbar at the top
    with ui.header().classes('flex items-center p-2 bg-gray-800 text-white'):
        with ui.row().classes('gap-4 items-center'):
            async def on_pick():
                file_path = await pick_file(extensions=AUDIO_EXTENSIONS)
                if file_path:
                    selected_path_label.set_text(file_path)
                    handle_audio_file(file_path, results_container)

            ui.button(icon='audiotrack', on_click=on_pick).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0 mr-2')
            selected_path_label = ui.label('Select an audio file to get started').classes('text-sm text-gray-300 truncate max-w-[400px]')

    # Main content area
    with ui.column().classes('w-full h-full items-center justify-center p-4'):
        ui.label('Select an audio file to get started').classes('text-xl text-gray-500')
        results_container = ui.column().classes('w-full max-w-2xl mt-4')


def _is_marker_near(timestamp: float, sorted_markers: list, tolerance: float = MARKER_MATCH_TOLERANCE) -> bool:
    """
    Check whether `timestamp` falls within `tolerance` seconds of any value in
    `sorted_markers`. Uses binary search instead of a linear scan, so this stays
    cheap regardless of how many markers there are or what ratio they bear to
    the beat list — works the same whether `sorted_markers` is downbeats,
    structural section boundaries, or anything else timestamp-based later.
    """
    if not sorted_markers:
        return False
    i = bisect_left(sorted_markers, timestamp)
    candidates = sorted_markers[max(0, i - 1):i + 1]
    return any(abs(timestamp - m) < tolerance for m in candidates)


def _render_marker_column(container_classes: str, markers: list, timeline_start: float, px_per_sec: float,
                           bg_class: str = 'bg-gray-400', label_fmt=lambda t: f'{t:.2f}s'):
    """
    Render one timeline column as absolutely-positioned boxes, one per interval
    between consecutive `markers`. Position/height are computed from real time
    via `px_per_sec`, so any column built this way lines up exactly with any
    other column built the same way, regardless of how many markers each has.
    """
    with ui.element('div').classes(container_classes).style(f'height: {TIMELINE_HEIGHT_PX}px;'):
        for i in range(len(markers) - 1):
            top = (markers[i] - timeline_start) * px_per_sec
            height = (markers[i + 1] - markers[i]) * px_per_sec
            with ui.element('div').classes(f'absolute w-full {bg_class} flex items-center justify-center') \
                    .style(f'top: {top:.2f}px; height: {height:.2f}px; border: 1px solid black; box-sizing: border-box;'):
                ui.label(label_fmt(markers[i])).classes('text-white text-xs')


def handle_audio_file(file_path: str, results_container: ui.element):
    """Handle selected audio file by calling beat detection directly."""

    # Clear previous results
    results_container.clear()

    # Show loading state
    with results_container:
        ui.label('Detecting beats...').classes('text-lg text-gray-500')
        ui.linear_progress().props('indeterminate')

    try:
        # Call beat detection directly (server has access to the file path)
        result = detect_beats_and_downbeats(file_path)

        if result.get('success'):
            # Display successful beat detection results
            results_container.clear()
            with results_container:
                ui.label('Beat Detection Results').classes('text-lg font-bold text-green-600')
                ui.separator()

                with ui.row().classes('gap-4'):
                    with ui.card().classes('w-48 p-2'):
                        ui.label('Tempo').classes('text-sm text-gray-500')
                        ui.label(f"{result['tempo']:.1f} BPM").classes('text-2xl font-bold')

                    with ui.card().classes('w-48 p-2'):
                        ui.label('Total Beats').classes('text-sm text-gray-500')
                        ui.label(str(result['total_beats'])).classes('text-2xl font-bold')

                    with ui.card().classes('w-48 p-2'):
                        ui.label('Downbeats').classes('text-sm text-gray-500')
                        ui.label(str(result['total_downbeats'])).classes('text-2xl font-bold')

                if result.get('downbeats_estimated'):
                    ui.label('Note: Downbeats are estimated (naive 4/4 time assumption)').classes('text-xs text-gray-400 italic mt-1')

                # Beat visualization
                with ui.card().classes('w-full p-2 mt-2 overflow-y-auto'):
                    ui.label('Intervals (Left: Beats, Right: Downbeats)').classes('text-xs text-gray-500 mb-1')
                    beats = result['beats']
                    downbeats = sorted(result.get('downbeats', []))

                    if len(beats) > 1:
                        # Shared time scale for both columns — this is what guarantees
                        # alignment. Any column rendered with this same
                        # timeline_start/px_per_sec lines up exactly with any other,
                        # regardless of how many markers it has or what ratio they
                        # bear to each other.
                        timeline_start = beats[0]
                        timeline_end = beats[-1]
                        total_dur = timeline_end - timeline_start
                        px_per_sec = TIMELINE_HEIGHT_PX / total_dur if total_dur > 0 else 0

                        with ui.row().classes('w-full gap-1 flex-nowrap'):
                            # Left: Beats (colored by whether a downbeat/marker falls near this beat)
                            with ui.element('div').classes('flex-1 relative').style(f'height: {TIMELINE_HEIGHT_PX}px;'):
                                for i in range(len(beats) - 1):
                                    top = (beats[i] - timeline_start) * px_per_sec
                                    height = (beats[i + 1] - beats[i]) * px_per_sec
                                    is_marker = _is_marker_near(beats[i], downbeats)
                                    bg_class = 'bg-gray-400' if is_marker else 'bg-gray-300'
                                    with ui.element('div').classes(f'absolute w-full {bg_class} flex items-center justify-center') \
                                            .style(f'top: {top:.2f}px; height: {height:.2f}px; border: 1px solid black; box-sizing: border-box;'):
                                        ui.label(f'{beats[i]:.2f}s').classes('text-white text-xs')

                            # Right: Downbeats — same timeline_start/px_per_sec as the
                            # beats column above, so a downbeat and its matching beat
                            # land at identical pixel offsets. No padding-box
                            # bookkeeping needed even if downbeats don't start/end
                            # exactly at the beat timeline's bounds.
                            if len(downbeats) > 1:
                                _render_marker_column('flex-1 relative', downbeats, timeline_start, px_per_sec)
                            elif len(downbeats) == 1:
                                with ui.element('div').classes('flex-1 relative').style(f'height: {TIMELINE_HEIGHT_PX}px;'):
                                    ui.label(f'{downbeats[0]:.2f}s').classes('text-white text-xs absolute') \
                                        .style(f'top: {(downbeats[0] - timeline_start) * px_per_sec:.2f}px;')
                            else:
                                with ui.element('div').classes('flex-1 relative').style(f'height: {TIMELINE_HEIGHT_PX}px;'):
                                    ui.label('No downbeats').classes('text-gray-500 absolute inset-0 flex items-center justify-center')

        else:
            # Display error from beat detection
            results_container.clear()
            with results_container:
                ui.label('Error detecting beats').classes('text-lg font-bold text-red-600')
                ui.label(result.get('error', 'Unknown error')).classes('text-sm text-red-500')

    except Exception as e:
        # Display unexpected error
        results_container.clear()
        with results_container:
            ui.label('Error').classes('text-lg font-bold text-red-600')
            ui.label(str(e)).classes('text-sm text-red-500')