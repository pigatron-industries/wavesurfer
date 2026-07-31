"""
Native OS drag-and-drop for pywebview.

pywebview's DOM API only reports the real filesystem path
(`pywebviewFullPath`) to Python-side event handlers, and that has to be
wired up from inside the pywebview process itself via `func`, passed to
webview.start() through app.native.start_args. Dropped paths cross back to
the main NiceGUI/uvicorn process over a multiprocessing.Queue.

`drop_queue` must be created once in the main process and the *same
object* passed into `setup_native_drop` (via functools.partial in app.py)
so multiprocessing's Queue pickling reconnects it to the same pipe in the
child process, instead of each process getting its own independent Queue
from re-importing this module.
"""

import multiprocessing

drop_queue: "multiprocessing.Queue" = multiprocessing.Queue()


def setup_native_drop(queue: "multiprocessing.Queue") -> None:
    """Runs inside the pywebview process, right as the GUI loop starts."""
    print('[native_drop] setup_native_drop() called', flush=True)
    import webview
    from webview.dom import DOMEventHandler

    def on_drag(e):
        print(f'[native_drag] {e["type"]} fired', flush=True)
        pass

    def on_drop(e):
        files = e.get('dataTransfer', {}).get('files', [])
        paths = [f['pywebviewFullPath'] for f in files if f.get('pywebviewFullPath')]
        print(f'[native_drop] drop: {paths}', flush=True)
        if paths:
            queue.put(paths)

    window = webview.windows[0]
    window.dom.document.events.dragenter += DOMEventHandler(on_drag, True, True)
    window.dom.document.events.dragover += DOMEventHandler(on_drag, True, True, debounce=500)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    print('[native_drop] DOM events bound', flush=True)