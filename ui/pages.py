"""
UI components and pages.
Add your UI elements here.
"""

from bisect import bisect_left

from nicegui import ui
from ui.path_picker import pick_file
from api.beat_detection import detect_beats_and_downbeats


AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']

TIMELINE_HEIGHT_PX = 3800
MARKER_MATCH_TOLERANCE = 0.05  # seconds; used to test "is this beat also a downbeat/marker"


@ui.page('/')
def main_page():
    """Main page with toolbar and file picker."""

    # Label to display the selected file path
    selected_path_label = None

    # Container for beat detection results
    results_container = None

    # Toolbar at the top
    with ui.header().classes('flex items-center p-2 bg-gray-800 text-white'):
        with ui.row().classes('gap-4 items-center'):

            # File picker button with icon
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