"""
UI components and pages.
Add your UI elements here.
"""

from nicegui import ui
from ui.path_picker import pick_file


AUDIO_EXTENSIONS = ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.aiff', '.mp4', '.avi', '.mkv', '.mov', '.webm']


@ui.page('/')
def main_page():
    """Main page with toolbar and file picker."""
    
    # Label to display the selected file path
    selected_path_label = None
    
    # Toolbar at the top
    with ui.header().classes('flex items-center p-2 bg-gray-800 text-white'):
        with ui.row().classes('gap-4 items-center'):
            
            # File picker button with icon
            async def on_pick():
                file_path = await pick_file(extensions=AUDIO_EXTENSIONS)
                if file_path:
                    selected_path_label.set_text(file_path)
                    handle_audio_file(file_path)
            
            ui.button(icon='audiotrack', on_click=on_pick).classes('bg-gray-600 hover:bg-gray-500 flex-shrink-0 mr-2')
            selected_path_label = ui.label('Select an audio file to get started').classes('text-sm text-gray-300 truncate max-w-[400px]')
    
    # Main content area
    with ui.column().classes('w-full h-full items-center justify-center p-4'):
        ui.label('Select an audio file to get started').classes('text-xl text-gray-500')


def handle_audio_file(file_path: str):
    """Handle selected audio file."""
    ui.notify(f'Loaded audio file: {file_path}')
    # TODO: Process the audio file and display results
