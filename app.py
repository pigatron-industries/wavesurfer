"""
Main application entry point.
NiceGUI app with native mode support.
"""

from nicegui import ui
from api import routes  # noqa: F401 - Import to register API routes
from ui import pages  # noqa: F401 - Import to register UI pages


def main():
    """Start the NiceGUI application."""
    # Run the app with native=True for native app behavior
    ui.run(port=54327, native=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
