"""
Standalone pywebview drag-and-drop test — no NiceGUI, no multiprocessing
tricks. If pywebviewFullPath doesn't show up here, the problem is at the
pywebview/OS level, not in how we've been wiring it into NiceGUI.
"""

import webview
from webview.dom import DOMEventHandler


def on_drag(e):
    print(f'{e["type"]} fired', flush=True)


def on_drop(e):
    print('drop fired', flush=True)
    files = e.get('dataTransfer', {}).get('files', [])
    print(f'{len(files)} file(s) in drop event', flush=True)
    for f in files:
        print(f' - name={f.get("name")!r} pywebviewFullPath={f.get("pywebviewFullPath")!r}', flush=True)


def bind(window):
    print('bind() called, wiring up DOM events', flush=True)
    window.dom.document.events.dragenter += DOMEventHandler(on_drag, True, True)
    window.dom.document.events.dragover += DOMEventHandler(on_drag, True, True, debounce=500)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


if __name__ == '__main__':
    window = webview.create_window(
        'Drag & Drop Test',
        html="""
        <html>
        <body style="height:100vh; margin:0; display:flex; align-items:center; justify-content:center; font-family:sans-serif;">
          <h1>Drag a file here</h1>
        </body>
        </html>
        """,
    )
    webview.start(bind, window, debug=True)