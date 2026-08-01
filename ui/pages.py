"""
UI components and pages.
Add your UI elements here.
"""

from bisect import bisect_left
from pathlib import Path
from nicegui import ui
from ui.path_picker import pick_file, pick_file_or_folder, pick_path
from api.beat_detection import detect_beats_and_downbeats
from api.export_rpp import export_to_rpp
from api.schema import Downbeat, DownbeatTimeline
from api import state
import asyncio
import json
import queue
from api.thumbnails import get_thumbnail_data_url, get_video_duration
from ui.native_drop import drop_queue
import librosa

AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.webm']
JSON_EXTENSIONS = ['.json']
RPP_EXTENSIONS = ['.rpp']

PX_PER_SEC = 30  # pixels per second of audio; determines interval box height
MARKER_MATCH_TOLERANCE = 0.05  # seconds; used to test "is this beat also a downbeat/marker"

_config_path = Path.home() / '.wavesurfer' / 'config.json'
_config = json.loads(_config_path.read_text()) if _config_path.exists() else {}


def _persist_config() -> None:
    try:
        _config_path.parent.mkdir(parents=True, exist_ok=True)
        _config_path.write_text(json.dumps(_config, indent=2))
    except OSError:
        pass


def _last_folder() -> str:
    return _config.get('last_folder', '')


def _set_last_folder(folder: str) -> None:
    _config['last_folder'] = folder
    _persist_config()


def _audio_folder() -> str:
    return _config.get('audio_folder', '')


def _set_audio_folder(folder: str) -> None:
    _config['audio_folder'] = folder
    _persist_config()


def _video_folder() -> str:
    return _config.get('video_folder', '')


def _set_video_folder(folder: str) -> None:
    _config['video_folder'] = folder
    _persist_config()


def _timeline_to_dict(timeline: DownbeatTimeline) -> dict:
    """Serialize a DownbeatTimeline to a plain dict for JSON saving."""
    return timeline.model_dump()


def _timeline_from_dict(data: dict) -> DownbeatTimeline:
    """Deserialize a dict (from JSON) into a DownbeatTimeline."""
    downbeats = [Downbeat(**db) for db in data.get('downbeats', [])]
    return DownbeatTimeline(
        path=data['path'],
        beats=data.get('beats', []),
        downbeats=downbeats,
        tempo=data.get('tempo'),
        duration=data.get('duration'),
    )


async def _save_timeline(library_files: list[Path], thumbnails: dict, video_durations: dict,
                          results_container: ui.element, current_json_name: dict):
    """Save the current timeline state as a JSON file."""
    if not state.timeline:
        ui.notify('No timeline to save', color='warning')
        return

    suggested = current_json_name['value'] or (Path(state.timeline.path).stem + '.json')
    save_path = await pick_path(
        start_path=_last_folder(),
        mode='file',
        extensions=JSON_EXTENSIONS,
        default_filename=suggested,
    )
    if not save_path:
        return

    _set_last_folder(str(Path(save_path).parent))
    current_json_name['value'] = Path(save_path).name

    try:
        data = _timeline_to_dict(state.timeline)
        Path(save_path).write_text(json.dumps(data, indent=2))
        ui.notify(f'Saved to {Path(save_path).name}', color='positive')
    except Exception as e:
        ui.notify(f'Failed to save: {e}', color='negative')


async def _load_timeline(library_files: list[Path], thumbnails: dict, video_durations: dict,
                          results_container: ui.element, 
                          selected_path_label, active_path, current_json_name: dict):
    """Load a timeline state from a JSON file."""
    json_file = await pick_file(start_path=_last_folder(), extensions=JSON_EXTENSIONS)
    if not json_file:
        return
    _set_last_folder(str(Path(json_file).parent))

    try:
        data = json.loads(Path(json_file).read_text())
        timeline = _timeline_from_dict(data)
        state.timeline = timeline
        active_path['value'] = timeline.path

        # Add audio file to library if not already present
        audio_path = Path(timeline.path)
        if audio_path.exists() and str(audio_path) not in {str(v) for v in library_files}:
            library_files.append(audio_path)
            library_files.sort(key=lambda e: e.name.lower())

        # Collect all video paths from downbeats and add to library
        for db in timeline.downbeats:
            for path_field in ('path', 'path_outer'):
                vid_path_str = getattr(db, path_field)
                if vid_path_str:
                    vid_path = Path(vid_path_str)
                    if vid_path.exists() and str(vid_path) not in {str(v) for v in library_files}:
                        library_files.append(vid_path)
                        library_files.sort(key=lambda e: e.name.lower())

        selected_path_label.set_text(timeline.path)

        # Cache thumbnails and durations for assigned videos
        for db in timeline.downbeats:
            for path_field in ('path', 'path_outer'):
                vid_path_str = getattr(db, path_field)
                if vid_path_str:
                    if vid_path_str not in thumbnails:
                        await _cache_thumbnail(vid_path_str, thumbnails)
                    if vid_path_str not in video_durations:
                        await _cache_video_duration(vid_path_str, video_durations)

        # Render library and timeline
        # We need to access render_library from the closure; handled via the main_page closure
        _render_timeline_from_state(results_container, thumbnails, video_durations)
        current_json_name['value'] = Path(json_file).name
        ui.notify(f'Loaded {Path(json_file).name}', color='positive')

    except json.JSONDecodeError:
        ui.notify('Invalid JSON file', color='negative')
    except Exception as e:
        ui.notify(f'Failed to load: {e}', color='negative')


async def _export_rpp(current_json_name: dict):
    """Export the current timeline as a Reaper (.rpp) project file."""
    if not state.timeline:
        ui.notify('No timeline to export', color='warning')
        return

    if current_json_name['value']:
        suggested = Path(current_json_name['value']).stem + '.rpp'
    else:
        suggested = Path(state.timeline.path).stem + '.rpp'
    export_path = await pick_path(
        start_path=_last_folder(),
        mode='file',
        extensions=RPP_EXTENSIONS,
        default_filename=suggested,
    )
    if not export_path:
        return

    _set_last_folder(str(Path(export_path).parent))

    try:
        export_to_rpp(state.timeline, export_path)
        ui.notify(f'Exported to {Path(export_path).name}', color='positive')
    except Exception as e:
        ui.notify(f'Failed to export: {e}', color='negative')


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
    video_durations: dict[str, float | None] = {}  # str(path) -> duration in seconds
    active_path = {'value': None}
    current_json_name = {'value': None}  # filename last loaded from / saved to

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
                        handle_audio_file(audio_paths[0], results_container, thumbnails, video_durations)
                elif target.startswith('downbeat_outer-'):
                    db_id = int(target.rsplit('-', 1)[-1])
                    video_paths = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
                    if video_paths and state.timeline:
                        asyncio.create_task(_handle_downbeat_drop(db_id, video_paths, 'path_outer', results_container, thumbnails, video_durations))
                elif target.startswith('downbeat-'):
                    db_id = int(target.rsplit('-', 1)[-1])
                    video_paths = [p for p in paths if Path(p).suffix.lower() in VIDEO_EXTENSIONS]
                    if video_paths and state.timeline:
                        asyncio.create_task(_handle_downbeat_drop(db_id, video_paths, 'path', results_container, thumbnails, video_durations))

    ui.timer(0.3, poll_native_drops)

    # Toolbar at the top — also the native drop target for audio files
    with ui.header().classes('flex items-center p-2 bg-gray-800 text-white') \
            .props('data-drop-target="audio"'):
        with ui.row().classes('gap-4 items-center'):
            async def on_save():
                await _save_timeline(library_files, thumbnails, video_durations, results_container, current_json_name)

            async def on_load():
                await _load_timeline(library_files, thumbnails, video_durations,
                                     results_container, 
                                     selected_path_label, active_path, current_json_name)

            async def on_pick():
                file_path = await pick_file(start_path=_audio_folder(), extensions=AUDIO_EXTENSIONS)
                if file_path:
                    _set_audio_folder(str(Path(file_path).parent))
                    selected_path_label.set_text(file_path)
                    handle_audio_file(file_path, results_container, thumbnails, video_durations)

            async def on_export():
                await _export_rpp(current_json_name)

            ui.button(icon='audiotrack', on_click=on_pick).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0 mr-2')
            ui.button(icon='folder_open', on_click=on_load).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0').tooltip('Load timeline')
            ui.button(icon='save', on_click=on_save).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0').tooltip('Save timeline')
            ui.button(icon='import_contacts', on_click=on_export).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0').tooltip('Export to Reaper')
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
                           thumbnails: dict, video_durations: dict,
                           path_field: str = 'path', drop_prefix: str = 'downbeat',
                           bg_class: str = 'bg-gray-400'):
    """Render downbeat boxes as drop targets with thumbnail + info.

    ``path_field`` selects which path attribute to display ('path' or 'path_outer').
    ``drop_prefix`` sets the drop target prefix ('downbeat' or 'downbeat_outer').
    """
    sorted_dbs = sorted(downbeats, key=lambda db: db.time)
    with ui.element('div').classes(container_classes).style(f'height: {timeline_height:.2f}px;'):
        for i in range(len(sorted_dbs) - 1):
            db = sorted_dbs[i]
            top = (db.time - timeline_start) * PX_PER_SEC
            interval = sorted_dbs[i + 1].time - db.time
            height = interval * PX_PER_SEC
            with ui.element('div') \
                    .classes(f'absolute w-full {bg_class} flex items-start gap-1 cursor-pointer') \
                    .style(f'top: {top:.2f}px; height: {height:.2f}px; border: 1px solid black; box-sizing: border-box; padding: 2px;') \
                    .props('data-drop-target="%s-%d"' % (drop_prefix, db.id)):
                # Left: thumbnail or icon
                vid_path = getattr(db, path_field)
                if vid_path:
                    thumb = thumbnails.get(vid_path)
                    if thumb:
                        ui.image(thumb).classes('w-8 h-8 object-cover rounded flex-shrink-0 mt-0.5')
                    else:
                        ui.icon('movie').classes('text-white text-sm flex-shrink-0 mt-0.5')
                # Right: info column
                with ui.column().classes('gap-0 text-[10px] text-white leading-tight'):
                    ui.label(f'{db.time:.2f}s').classes('font-medium')
                    ui.label(f'Δ {interval:.2f}s')
                    vid_dur = video_durations.get(vid_path) if vid_path else None
                    if vid_dur is not None:
                        ui.label(f'🎬 {vid_dur:.1f}s')


def _render_downbeat_single(db: Downbeat, container_classes: str, timeline_start: float, timeline_height: float,
                              thumbnails: dict, video_durations: dict,
                              path_field: str = 'path', drop_prefix: str = 'downbeat'):
    """Render a single downbeat box (when there's only one downbeat)."""
    top = (db.time - timeline_start) * PX_PER_SEC
    vid_path = getattr(db, path_field)
    with ui.element('div') \
            .classes(f'{container_classes} cursor-pointer') \
            .style(f'height: {timeline_height:.2f}px;') \
            .props('data-drop-target="%s-%d"' % (drop_prefix, db.id)):
        with ui.element('div') \
                .classes('flex items-start gap-1 p-1') \
                .style(f'top: {top:.2f}px; position: absolute;'):
            if vid_path:
                thumb = thumbnails.get(vid_path)
                if thumb:
                    ui.image(thumb).classes('w-8 h-8 object-cover rounded flex-shrink-0')
                else:
                    ui.icon('movie').classes('text-white text-sm flex-shrink-0')
            with ui.column().classes('gap-0 text-[10px] text-white leading-tight'):
                ui.label(f'{db.time:.2f}s').classes('font-medium')
                vid_dur = video_durations.get(vid_path) if vid_path else None
                if vid_dur is not None:
                    ui.label(f'🎬 {vid_dur:.1f}s')


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


def _render_timeline_from_state(results_container: ui.element, thumbnails: dict, video_durations: dict):
    """Render the UI based on the current state.timeline object."""
    timeline = state.timeline
    if not timeline:
        results_container.clear()
        with results_container:
            ui.label('No audio loaded').classes('text-gray-500')
        return

    downbeats = timeline.downbeats

    # Precompute thumbnails and durations for any downbeat video paths not yet cached.
    for db in downbeats:
        for path_field in ('path', 'path_outer'):
            vid_path = getattr(db, path_field)
            if vid_path:
                if vid_path not in thumbnails:
                    asyncio.create_task(_cache_thumbnail(vid_path, thumbnails))
                if vid_path not in video_durations:
                    asyncio.create_task(_cache_video_duration(vid_path, video_durations))

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

        # Visual timeline — three columns: beats, downbeats, outer downbeats
        if timeline.duration is not None and timeline.duration > 0:
            beats = timeline.beats
            timeline_start = beats[0] if beats else 0.0
            timeline_end = beats[-1] if beats else timeline.duration
            total_dur = timeline_end - timeline_start
            timeline_height = total_dur * PX_PER_SEC

            with ui.card().classes('w-full p-2 mt-2 overflow-y-auto'):
                ui.label('Intervals (Beats | Downbeats | Outer — drop videos on downbeat boxes)').classes('text-xs text-gray-500 mb-1')

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

                    # Middle column: downbeats (inner)
                    if len(downbeats) > 1:
                        _render_marker_column('flex-1 relative', downbeats, timeline_start, timeline_height,
                                               thumbnails, video_durations, path_field='path', drop_prefix='downbeat')
                    elif len(downbeats) == 1:
                        _render_downbeat_single(downbeats[0], 'flex-1 relative', timeline_start, timeline_height,
                                                thumbnails, video_durations, path_field='path', drop_prefix='downbeat')
                    else:
                        with ui.element('div').classes('flex-1 relative').style(f'height: {timeline_height:.2f}px;'):
                            ui.label('No downbeats').classes('text-gray-500 absolute inset-0 flex items-center justify-center')

                    # Right column: downbeats (outer)
                    if len(downbeats) > 1:
                        _render_marker_column('flex-1 relative', downbeats, timeline_start, timeline_height,
                                               thumbnails, video_durations, path_field='path_outer', drop_prefix='downbeat_outer',
                                               bg_class='bg-blue-400')
                    elif len(downbeats) == 1:
                        _render_downbeat_single(downbeats[0], 'flex-1 relative', timeline_start, timeline_height,
                                                thumbnails, video_durations, path_field='path_outer', drop_prefix='downbeat_outer')
                    else:
                        with ui.element('div').classes('flex-1 relative').style(f'height: {timeline_height:.2f}px;'):
                            ui.label('No downbeats').classes('text-gray-500 absolute inset-0 flex items-center justify-center')


async def _cache_thumbnail(path: str, thumbnails: dict):
    """Extract a thumbnail for a video and cache it in the thumbnails dict."""
    thumbnails[path] = await asyncio.to_thread(get_thumbnail_data_url, path)


async def _cache_video_duration(path: str, video_durations: dict):
    """Read video duration and cache it in the durations dict."""
    video_durations[path] = await asyncio.to_thread(get_video_duration, path)


async def _handle_downbeat_drop(db_id: int, video_paths: list[str], path_field: str, results_container: ui.element,
                                  thumbnails: dict, video_durations: dict):
    """Associate one or more videos with consecutive downbeats starting at db_id, then re-render."""
    if not state.timeline:
        return
    sorted_dbs = sorted(state.timeline.downbeats, key=lambda db: db.id)
    start_idx = next((i for i, db in enumerate(sorted_dbs) if db.id == db_id), None)
    if start_idx is None:
        return
    for j, video_path in enumerate(video_paths):
        db_idx = start_idx + j
        if db_idx >= len(sorted_dbs):
            break
        setattr(sorted_dbs[db_idx], path_field, video_path)
        if video_path not in thumbnails:
            asyncio.create_task(_cache_thumbnail(video_path, thumbnails))
        if video_path not in video_durations:
            asyncio.create_task(_cache_video_duration(video_path, video_durations))
    _render_timeline_from_state(results_container, thumbnails, video_durations)


def handle_audio_file(file_path: str, results_container: ui.element, thumbnails: dict, video_durations: dict):
    """Handle selected audio file: initialise timeline, detect beats, render."""

    # Step 1: initialise empty timeline for this audio file
    timeline = _init_timeline(file_path)

    # Step 2: render empty timeline immediately (shows duration, no downbeats yet)
    _render_timeline_from_state(results_container, thumbnails, video_durations)

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
            _render_timeline_from_state(results_container, thumbnails, video_durations)
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