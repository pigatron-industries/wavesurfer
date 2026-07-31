"""
Main application entry point.
NiceGUI app with native mode support.
"""

import functools
from nicegui import app, ui
from api import routes  # noqa: F401 - Import to register API routes
from ui import pages  # noqa: F401 - Import to register UI pages
from ui.native_drop import setup_native_drop, drop_queue


def main():
    """Start the NiceGUI application."""
    app.native.start_args['func'] = functools.partial(setup_native_drop, drop_queue)
    ui.run(port=54327, native=True, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()