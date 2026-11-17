"""Trading Journal: a local-first journal for trades and accounts."""
import os

from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from . import api, db

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal-data")


def create_app(data_dir=None):
    data_dir = os.path.abspath(data_dir or os.environ.get("JOURNAL_DATA_DIR") or DEFAULT_DATA_DIR)
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=os.path.join(data_dir, "journal.db"),
        UPLOAD_DIR=os.path.join(data_dir, "screenshots"),
        MAX_CONTENT_LENGTH=200 * 1024 * 1024,
    )
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    db.init_db(app.config["DB_PATH"])
    app.json.sort_keys = False
    app.teardown_appcontext(db.close_db)
    app.register_blueprint(api.bp)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html", max_age=0)

    @app.errorhandler(api.ValidationError)
    def on_validation(err):
        return jsonify({"error": "Please fix the highlighted fields.", "fields": err.errors}), 400

    @app.errorhandler(api.NotFound)
    def on_not_found(err):
        return jsonify({"error": str(err)}), 404

    @app.errorhandler(RequestEntityTooLarge)
    def on_too_large(_err):
        return jsonify({"error": "Upload is too large (200 MB limit per save)."}), 413

    @app.errorhandler(HTTPException)
    def on_http(err):
        return jsonify({"error": err.description}), err.code

    @app.errorhandler(Exception)
    def on_error(_err):
        app.logger.exception("Unhandled error")
        return jsonify({"error": "Something went wrong. Your data was not changed."}), 500

    return app
