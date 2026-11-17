"""Trading Journal as a desktop app (its own window, no browser).

    python journal_desktop.py              run the desktop window from source
    python journal_desktop.py --self-test  start the server, check it responds, exit (used by the builds)

Data lives in ~/Library/Application Support/Trading Journal on macOS and
%APPDATA%\\Trading Journal on Windows (override with JOURNAL_DATA_DIR).
"""
import logging
import os
import sys
import tempfile
import threading
import urllib.request

from werkzeug.serving import make_server

from journal import create_app

APP_NAME = "Trading Journal"


def default_data_dir():
    if sys.platform == "darwin":
        return os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".trading-journal")


def start_server(app):
    """Serve the app on a free local port in a background thread."""
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/"


def self_test():
    # The exit code reports the result: a packaged windowed app has no console.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            server, url = start_server(create_app(tmp))
            try:
                for path in ("", "api/accounts", "api/trades", "api/settings", "static/js/app.js",
                             "static/js/atom.js", "static/css/app.css", "static/fonts/inter-variable.woff2"):
                    with urllib.request.urlopen(url + path, timeout=10) as resp:
                        assert resp.status == 200, path
            finally:
                server.shutdown()
    except Exception as err:  # noqa: BLE001 - any failure means the build is broken
        print(f"self-test FAILED: {err!r}")
        sys.exit(1)
    print("self-test OK")


def main():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    if "--self-test" in sys.argv:
        return self_test()

    import webview

    data_dir = os.environ.get("JOURNAL_DATA_DIR") or default_data_dir()
    server, url = start_server(create_app(data_dir))
    webview.create_window(APP_NAME, url, width=1440, height=900, min_size=(1100, 700),
                          background_color="#000000")
    # private_mode=False keeps small preferences (last account used) between launches.
    webview.start(private_mode=False, storage_path=os.path.join(data_dir, "webview"))
    server.shutdown()


if __name__ == "__main__":
    main()
