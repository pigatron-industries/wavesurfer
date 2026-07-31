"""
Native OS drag-and-drop for pywebview.

pywebview's DOM API only reports the real filesystem path
(`pywebviewFullPath`) to Python-side event handlers, and that has to be
wired up from inside the pywebview process itself via `func`, passed to
webview.start() through app.native.start_args.

NiceGUI's native mode runs the pywebview window in a *separate* process
(spawned in `nicegui.native.native_mode.activate`). On macOS/Windows,
`multiprocessing`'s "spawn" start method re-executes this app's entry
script from scratch in that child process, so a plain module-level
`multiprocessing.Queue()` here would create a second, independent queue
with its own pipe in each process — they'd never be the same queue, no
matter what gets passed to `setup_native_drop`.

Instead, dropped paths are sent back to the main NiceGUI/uvicorn process
over plain HTTP, since that's the one channel already reliably crossing
the process boundary (the webview window is pointed at that server's
URL). `drop_queue` is an ordinary in-process `queue.Queue`, filled by the
`/api/native-drop` endpoint (see api/routes.py) and drained by
`ui.pages.poll_native_drops` — both of which run in the main process.
"""

import json
import queue
import urllib.request

drop_queue: "queue.Queue" = queue.Queue()


def setup_native_drop(port: int) -> None:
    """Runs inside the pywebview process, right as the GUI loop starts."""
    print('[native_drop] setup_native_drop() called', flush=True)
    import webview
    from webview.dom import DOMEventHandler

    def _is_in_drop_target(target_el):
        """Walk up the DOM tree to see if the target (or an ancestor) is the drop target."""
        current = target_el
        while current:
            if current.get('attributes', {}).get('data-drop-target') == 'audio':
                return True
            current = current.get('parentElement')
        return False

    window = webview.windows[0]

    def on_drag(e):
        target = e.get('target') or e.get('srcElement')
        if target and _is_in_drop_target(target):
            print(f'[native_drag] {e["type"]} fired (in header)', flush=True)
        else:
            print(f'[native_drag] {e["type"]} fired (outside header, ignoring)', flush=True)

    def on_drop(e):
        target = e.get('target') or e.get('srcElement')
        if target and _is_in_drop_target(target):
            files = e.get('dataTransfer', {}).get('files', [])
            paths = [f['pywebviewFullPath'] for f in files if f.get('pywebviewFullPath')]
            print(f'[native_drop] drop in header: {paths}', flush=True)
            if paths:
                body = json.dumps({'paths': paths}).encode()
                request = urllib.request.Request(
                    f'http://127.0.0.1:{port}/api/native-drop',
                    data=body,
                    headers={'Content-Type': 'application/json'},
                )
                try:
                    urllib.request.urlopen(request, timeout=5)
                except OSError:
                    print('[native_drop] failed to post dropped paths to server', flush=True)
        else:
            print('[native_drop] drop outside header, ignoring', flush=True)

    window.dom.document.events.dragenter += DOMEventHandler(on_drag, True, True)
    window.dom.document.events.dragover += DOMEventHandler(on_drag, True, True, debounce=500)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    print('[native_drop] DOM events bound (scoped to header via target check)', flush=True)