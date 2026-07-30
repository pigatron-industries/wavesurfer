"""
API routes for the backend.
Add your API endpoints here.
"""

from nicegui import app


@app.get('/api/health')
def health_check():
    """Health check endpoint."""
    return {'status': 'ok'}
