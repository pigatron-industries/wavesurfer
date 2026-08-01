"""
API routes for the backend.
Add your API endpoints here.
"""

from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse
from nicegui import app
from ui.native_drop import drop_queue


@app.get('/api/audio')
def serve_audio(path: str):
    """Stream a local audio file so the browser <audio> element can play it.
    Starlette's FileResponse supports Range requests, so seeking works."""
    file_path = Path(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail='File not found')
    return FileResponse(file_path)


@app.post('/api/native-drop')
async def native_drop(request: Request):
    """Receive dropped file paths from the pywebview process (see ui/native_drop.py)."""
    data = await request.json()
    paths = data.get('paths', [])
    target = data.get('target', '')
    if paths:
        drop_queue.put({'target': target, 'paths': paths})
    return {'status': 'ok'}
