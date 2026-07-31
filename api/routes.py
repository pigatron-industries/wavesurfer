"""
API routes for the backend.
Add your API endpoints here.
"""

from fastapi import Request
from nicegui import app
from ui.native_drop import drop_queue


@app.get('/api/health')
def health_check():
    """Health check endpoint."""
    return {'status': 'ok'}


@app.post('/api/native-drop')
async def native_drop(request: Request):
    """Receive dropped file paths from the pywebview process (see ui/native_drop.py)."""
    data = await request.json()
    paths = data.get('paths', [])
    if paths:
        drop_queue.put(paths)
    return {'status': 'ok'}
