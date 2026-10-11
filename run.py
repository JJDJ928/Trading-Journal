"""Start Rinse Tracker.

    python run.py            your real records, stored in ./data
    python run.py --demo     sample data in ./demo-data (never touches ./data)
"""
import argparse
import os
import webbrowser
from threading import Timer

from rinse_tracker import create_app
from rinse_tracker.sample_data import seed_if_empty

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="Rinse Tracker")
    parser.add_argument("--demo", action="store_true", help="run with sample data in ./demo-data")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.demo:
        app = create_app(os.path.join(ROOT, "demo-data"), demo=True)
        seed_if_empty(app)
    else:
        app = create_app()

    url = f"http://{args.host}:{args.port}"
    print(f"Rinse Tracker running at {url}")
    print(f"Data folder: {app.config['DATA_DIR']}" + ("  (DEMO DATA)" if args.demo else ""))
    if not args.no_browser:
        Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
