"""
UI components and pages.
Add your UI elements here.
"""

from nicegui import ui
from ui.path_picker import pick_file
from api.beat_detection import detect_beats_and_downbeats


AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']


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
                    downbeats = result.get('downbeats', [])
                    if len(beats) > 1:
                        durations = [beats[i+1] - beats[i] for i in range(len(beats)-1)]
                        total_dur = sum(durations)
                    else:
                        total_dur = 1.0  # Avoid division by zero
                    
                    # Determine the timeline bounds from beats
                    timeline_start = beats[0] if beats else 0
                    timeline_end = beats[-1] if beats else total_dur
                    
                    with ui.row().classes('w-full gap-1 flex-nowrap'):
                        # Left: Beats
                        with ui.element('div').classes('flex-1 flex flex-col gap-0').style('height: 3800px;'):
                            if len(beats) > 1:
                                for i, dur in enumerate(durations):
                                    is_downbeat = any(abs(beats[i] - db) < 0.05 for db in downbeats)
                                    bg_class = 'bg-gray-400' if is_downbeat else 'bg-gray-300'
                                    with ui.element('div').classes(f'w-full {bg_class} flex items-center justify-center').style(f'height: {dur/total_dur*100:.2f}%; border: 1px solid black;'):
                                        ui.label(f'{beats[i]:.2f}s').classes('text-white text-xs')
                        
                        # Right: Downbeats - aligned with beat timeline
                        with ui.element('div').classes('flex-1 flex flex-col gap-0').style('height: 3800px;'):
                            if len(downbeats) > 1:
                                # Calculate downbeat intervals relative to the beat timeline
                                # Add padding if downbeats don't start at timeline_start
                                pad_start = max(0, downbeats[0] - timeline_start)
                                pad_end = max(0, timeline_end - downbeats[-1])
                                
                                # Add top padding if downbeats start after beats
                                if pad_start > 0.001:
                                    with ui.element('div').classes('w-full bg-gray-200').style(f'height: {pad_start/total_dur*100:.2f}%;'):
                                        ui.label('').classes('text-white text-xs')
                                
                                # Downbeat intervals
                                for i in range(len(downbeats)-1):
                                    db_dur = downbeats[i+1] - downbeats[i]
                                    with ui.element('div').classes('w-full bg-gray-400 flex items-center justify-center').style(f'height: {db_dur/total_dur*100:.2f}%; border: 1px solid black;'):
                                        ui.label(f'{downbeats[i]:.2f}s').classes('text-white text-xs')
                                
                                # Add bottom padding if downbeats end before beats
                                if pad_end > 0.001:
                                    with ui.element('div').classes('w-full bg-gray-200').style(f'height: {pad_end/total_dur*100:.2f}%;'):
                                        ui.label('').classes('text-white text-xs')
                            elif len(downbeats) == 1:
                                # Single downbeat - pad to align with beat timeline
                                pad_start = max(0, downbeats[0] - timeline_start)
                                pad_end = max(0, timeline_end - downbeats[0])
                                box_height = total_dur - pad_start - pad_end
                                
                                if pad_start > 0.001:
                                    with ui.element('div').classes('w-full bg-gray-200').style(f'height: {pad_start/total_dur*100:.2f}%;'):
                                        ui.label('').classes('text-white text-xs')
                                if box_height > 0.001:
                                    with ui.element('div').classes('w-full bg-gray-400 flex items-center justify-center').style(f'height: {box_height/total_dur*100:.2f}%; border: 1px solid black;'):
                                        ui.label(f'{downbeats[0]:.2f}s').classes('text-white text-xs')
                                if pad_end > 0.001:
                                    with ui.element('div').classes('w-full bg-gray-200').style(f'height: {pad_end/total_dur*100:.2f}%;'):
                                        ui.label('').classes('text-white text-xs')
                            else:
                                with ui.element('div').classes('w-full bg-gray-200').style('height: 100%;'):
                                    ui.label('No downbeats').classes('text-gray-500 absolute inset-0 flex items-center justify-center')
                
                # Display beat timestamps
                with ui.expansion('Beat Timestamps', icon='music_note').classes('w-full mt-2'):
                    with ui.column().classes('max-h-48 overflow-y-auto'):
                        for i, beat in enumerate(beats):
                            ui.label(f'Beat {i+1}: {beat:.3f}s').classes('text-sm')
                
                # Display downbeat timestamps
                with ui.expansion('Downbeat Timestamps', icon='jump_to').classes('w-full mt-2'):
                    with ui.column().classes('max-h-48 overflow-y-auto'):
                        for i, downbeat in enumerate(downbeats):
                            ui.label(f'Downbeat {i+1}: {downbeat:.3f}s').classes('text-sm text-blue-600')
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
