"""Rinse Tracker as a desktop app: the same app in its own native window.

    python desktop.py              run the desktop window from source
    python desktop.py --self-test  start the server, check it responds, exit (used by the build)

The packaged apps (scripts/build_mac.sh, scripts/build_windows.ps1) run this file.
Data lives in ~/Library/Application Support/Rinse Tracker on macOS and
%APPDATA%\\Rinse Tracker on Windows (override with RINSE_DATA_DIR).
"""
import logging
import os
import sys
import tempfile
import threading
import urllib.request
from datetime import datetime

from werkzeug.serving import make_server

from rinse_tracker import backup as backup_mod
from rinse_tracker import create_app

APP_NAME = "Rinse Tracker"


def default_data_dir():
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".rinse-tracker")


def start_server(app):
    """Serve the app on a free local port in a background thread."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/"


class Bridge:
    """Functions the page can call as window.pywebview.api.* (underscored names stay private)."""

    def __init__(self, app):
        self._app = app
        self._window = None

    def save_backup(self):
        import webview
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE, directory=os.path.expanduser("~/Documents"),
            save_filename=f"rinse-backup-{stamp}.zip")
        if not result:
            return {"saved": False}
        path = result if isinstance(result, str) else result[0]
        if not path.endswith(".zip"):
            path += ".zip"
        cfg = self._app.config
        backup_mod.create_backup(cfg["DB_PATH"], cfg["UPLOAD_DIR"], path)
        return {"saved": True, "path": path}


def self_test():
    # Exit codes (not output) report the result: a packaged windowed app has no console.
    try:
        _check_server()
    except Exception as err:  # noqa: BLE001 - any failure means the build is broken
        print(f"self-test FAILED: {err!r}")
        sys.exit(1)
    print("self-test OK")


def _check_server():
    with tempfile.TemporaryDirectory() as tmp:
        server, url = start_server(create_app(tmp))
        try:
            for path in ("", "api/meta", "api/dashboard", "static/js/app.js", "static/css/app.css"):
                with urllib.request.urlopen(url + path, timeout=10) as resp:
                    assert resp.status == 200, path
        finally:
            server.shutdown()


def main():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # no per-request log lines
    if "--self-test" in sys.argv:
        return self_test()

    import webview

    data_dir = os.environ.get("RINSE_DATA_DIR") or default_data_dir()
    app = create_app(data_dir)
    server, url = start_server(app)

    bridge = Bridge(app)
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(APP_NAME, url, js_api=bridge, width=1360, height=900,
                                   min_size=(900, 600), background_color="#0a0a0a")
    bridge._window = window
    # private_mode=False keeps small UI preferences (last account used, etc.) between launches.
    webview.start(private_mode=False, storage_path=os.path.join(data_dir, "webview"))
    server.shutdown()


if __name__ == "__main__":
    main()
