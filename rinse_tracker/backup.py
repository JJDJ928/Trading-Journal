"""Backup and restore of the whole data set (database + screenshots) as one .zip.

A backup zip contains:
  manifest.json      app name, schema version, creation time, record counts
  rinse.db           a consistent SQLite snapshot (sqlite3 backup API)
  uploads/<file>     every screenshot file

Before a restore replaces anything, the current data is saved to
<data dir>/backups/pre-restore-<timestamp>.zip so a restore can be undone.
"""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, send_file

from . import db as dbmod
from . import images
from .validation import ValidationError

bp = Blueprint("backup", __name__)

APP_ID = "rinse-tracker"


def _counts(conn):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("accounts", "trades", "screenshots", "payouts")}


def create_backup(db_path, upload_dir, dest_path):
    """Write a backup zip to dest_path and return its manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = os.path.join(tmp, "rinse.db")
        src = dbmod.connect(db_path)
        dst = sqlite3.connect(snapshot)
        try:
            src.backup(dst)
            counts = _counts(src)
            version = src.execute("PRAGMA user_version").fetchone()[0]
        finally:
            dst.close()
            src.close()
        manifest = {"app": APP_ID, "schema_version": version,
                    "created_at": datetime.now().isoformat(timespec="seconds"), "counts": counts}
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.write(snapshot, "rinse.db")
            if os.path.isdir(upload_dir):
                for name in sorted(os.listdir(upload_dir)):
                    path = os.path.join(upload_dir, name)
                    if os.path.isfile(path) and images.SAFE_NAME.match(name):
                        # Images are already compressed; store them as-is.
                        zf.write(path, f"uploads/{name}", compress_type=zipfile.ZIP_STORED)
    return manifest


def restore_backup(zip_path, db_path, upload_dir, safety_dir):
    """Validate a backup zip, save the current data, then swap the backup in."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValidationError("That file is not a valid backup (.zip) file.")

    with zf, tempfile.TemporaryDirectory(dir=os.path.dirname(db_path)) as tmp:
        names = zf.namelist()
        if "rinse.db" not in names or "manifest.json" not in names:
            raise ValidationError("This zip is not a Rinse Tracker backup "
                                  "(missing rinse.db or manifest.json).")
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except ValueError:
            raise ValidationError("The backup manifest is damaged.")
        if manifest.get("app") != APP_ID:
            raise ValidationError("This zip was not created by Rinse Tracker.")
        if manifest.get("schema_version", 0) > dbmod.SCHEMA_VERSION:
            raise ValidationError("This backup is from a newer version of the app.")

        new_db = os.path.join(tmp, "rinse.db")
        with zf.open("rinse.db") as src, open(new_db, "wb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            conn = dbmod.connect(new_db)
            try:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValidationError("The database inside the backup is corrupted.")
                if not dbmod.REQUIRED_TABLES <= dbmod.table_names(conn):
                    raise ValidationError("The backup database is missing required tables.")
                referenced = {r[0] for r in conn.execute("SELECT filename FROM screenshots")}
                conn.executescript(dbmod.SCHEMA)
                dbmod.migrate(conn)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            raise ValidationError("The database inside the backup can't be read.")

        new_uploads = os.path.join(tmp, "uploads")
        os.makedirs(new_uploads)
        for name in names:
            if not name.startswith("uploads/") or name.endswith("/"):
                continue
            base = name[len("uploads/"):]
            if not images.SAFE_NAME.match(base):
                continue  # ignore anything that could escape the folder
            with zf.open(name) as src, open(os.path.join(new_uploads, base), "wb") as dst:
                shutil.copyfileobj(src, dst)
        missing = sorted(referenced - set(os.listdir(new_uploads)))

        # Keep a copy of the current data before overwriting it.
        os.makedirs(safety_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_path = os.path.join(safety_dir, f"pre-restore-{stamp}.zip")
        create_backup(db_path, upload_dir, safety_path)

        os.replace(new_db, db_path)
        old_uploads = os.path.join(tmp, "uploads-old")
        if os.path.isdir(upload_dir):
            os.replace(upload_dir, old_uploads)
        shutil.move(new_uploads, upload_dir)

    return {"restored": manifest, "safety_backup": os.path.basename(safety_path),
            "missing_screenshots": len(missing)}


@bp.get("/api/backup")
def download_backup():
    cfg = current_app.config
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        create_backup(cfg["DB_PATH"], cfg["UPLOAD_DIR"], tmp_path)
        with open(tmp_path, "rb") as fh:
            data = fh.read()
    finally:
        os.remove(tmp_path)
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True,
                     download_name=f"rinse-backup-{stamp}.zip")


@bp.post("/api/backup/restore")
def upload_restore():
    cfg = current_app.config
    upload = request.files.get("backup")
    if upload is None or not upload.filename:
        raise ValidationError({"backup": "Choose a backup .zip file to restore."})
    dbmod.close_db()
    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        upload.save(tmp_path)
        result = restore_backup(tmp_path, cfg["DB_PATH"], cfg["UPLOAD_DIR"],
                                os.path.join(cfg["DATA_DIR"], "backups"))
    finally:
        os.remove(tmp_path)
    return jsonify(result)
