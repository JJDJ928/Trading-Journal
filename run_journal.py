"""Run Trading Journal in your web browser (records stored in ./journal-data).

    python run_journal.py
"""
import argparse
import webbrowser
from threading import Timer

from journal import create_app


def main():
    parser = argparse.ArgumentParser(description="Trading Journal")
    parser.add_argument("--port", type=int, default=5070)
    parser.add_argument("--data-dir", help="folder for your records (default ./journal-data)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = create_app(args.data_dir)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Trading Journal running at {url}")
    print(f"Data folder: {app.config['DATA_DIR']}")
    if not args.no_browser:
        Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
