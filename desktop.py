"""Rinse Tracker as a desktop app: the same app in its own native window.

    python desktop.py              run the desktop window from source
    python desktop.py --self-test  start the server, check it responds, exit (used by the build)

The packaged macOS app (scripts/build_mac.sh) runs this file. Data lives in
~/Library/Application Support/Rinse Tracker on macOS (override with RINSE_DATA_DIR).
"""
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
    with tempfile.TemporaryDirectory() as tmp:
        server, url = start_server(create_app(tmp))
        try:
            for path in ("", "api/meta", "api/dashboard", "static/js/app.js", "static/css/app.css"):
                with urllib.request.urlopen(url + path, timeout=10) as resp:
                    assert resp.status == 200, path
        finally:
            server.shutdown()
    print("self-test OK")


def main():
    if "--self-test" in sys.argv:
        return self_test()

    import webview

    data_dir = os.environ.get("RINSE_DATA_DIR") or default_data_dir()
    app = create_app(data_dir)
    server, url = start_server(app)

    bridge = Bridge(app)
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(APP_NAME, url, js_api=bridge, width=1360, height=900,
                                   min_size=(900, 600), background_color="#0b0f14")
    bridge._window = window
    # private_mode=False keeps small UI preferences (last account used, etc.) between launches.
    webview.start(private_mode=False, storage_path=os.path.join(data_dir, "webview"))
    server.shutdown()


if __name__ == "__main__":
    main()
