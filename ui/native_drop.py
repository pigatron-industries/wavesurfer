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

    window = webview.windows[0]

    # Collect all drop targets upfront so we can check containment in JS later.
    drop_target_ids = window.evaluate_js(
        "Array.from(document.querySelectorAll('[data-drop-target]'))."
        "map(el => ({id: el.id, target: el.getAttribute('data-drop-target')}))"
    ) or []
    drop_target_map = {d['id']: d['target'] for d in drop_target_ids}
    print(f'[native_drop] drop targets: {drop_target_map}', flush=True)

    def _find_drop_target_for_event(e):
        """Use JS to find which drop target contains the event's target element."""
        target_id = (e.get('target') or e.get('srcElement') or {}).get('id', '')
        if not target_id or not drop_target_map:
            return None
        containing_id = window.evaluate_js(
            f"(() => {{ "
            f"const t = document.getElementById({target_id!r}); "
            f"if (!t) return null; "
            f"const hits = Array.from(document.querySelectorAll('[data-drop-target]')); "
            f"const hit = hits.find(h => h.contains(t)); "
            f"return hit ? hit.id : null; "
            f"}})()"
        )
        return drop_target_map.get(containing_id) if containing_id else None

    def on_drag(e):
        target_type = _find_drop_target_for_event(e)
        if target_type:
            print(f'[native_drag] {e["type"]} fired (target: {target_type})', flush=True)
        else:
            print(f'[native_drag] {e["type"]} fired (no drop target, ignoring)', flush=True)

    def on_drop(e):
        target_type = _find_drop_target_for_event(e)
        if target_type:
            files = e.get('dataTransfer', {}).get('files', [])
            paths = [f['pywebviewFullPath'] for f in files if f.get('pywebviewFullPath')]
            print(f'[native_drop] drop (target: {target_type}): {paths}', flush=True)
            if paths:
                body = json.dumps({'target': target_type, 'paths': paths}).encode()
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
            print('[native_drop] drop outside drop target, ignoring', flush=True)

    window.dom.document.events.dragenter += DOMEventHandler(on_drag, True, True)
    window.dom.document.events.dragover += DOMEventHandler(on_drag, True, True, debounce=500)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    print('[native_drop] DOM events bound (scoped via JS containment check)', flush=True)