"""
API routes for the backend.
Add your API endpoints here.
"""

from nicegui import app
from fastapi import UploadFile, File
from api.beat_detection import detect_beats_and_downbeats
import os
import tempfile


@app.get('/api/health')
def health_check():
    """Health check endpoint."""
    return {'status': 'ok'}


@app.post('/api/detect-beats')
async def detect_beats(file: UploadFile = File(...)):
    """
    Detect beats and downbeats from an audio file.
    
    Accepts an audio file (mp3, wav, flac, etc.) and returns the detected
    beat and downbeat timestamps.
    
    Returns:
        JSON with beat timestamps and downbeat timestamps
    """
    # Create a temporary file to store the uploaded audio
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    try:
        # Run beat detection
        result = detect_beats_and_downbeats(tmp_path)
        return result
    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
