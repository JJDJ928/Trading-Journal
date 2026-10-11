"""Screenshot file storage. Files live in UPLOAD_DIR; the DB stores their names."""
import os
import re
import uuid

from .validation import ValidationError

MAX_IMAGE_BYTES = 25 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")

# Detected by file contents (magic bytes), not by the uploaded name.
SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
    (b"BM", "bmp", "image/bmp"),
)


def detect(head):
    for magic, ext, mime in SIGNATURES:
        if head.startswith(magic):
            return ext, mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def read_uploads(files):
    """Validate every uploaded file up front, so nothing is saved if one is bad."""
    images = []
    for f in files:
        if not f or not f.filename:
            continue
        data = f.read(MAX_IMAGE_BYTES + 1)
        name = os.path.basename(f.filename)[:200]
        if len(data) > MAX_IMAGE_BYTES:
            raise ValidationError({"screenshots": f"'{name}' is larger than 25 MB."})
        kind = detect(data[:16])
        if kind is None:
            raise ValidationError({"screenshots": f"'{name}' is not a supported image "
                                                  "(PNG, JPG, GIF, WEBP or BMP)."})
        images.append({"data": data, "original_name": name, "ext": kind[0], "mime": kind[1]})
    return images


def save_files(upload_dir, images):
    """Write images to disk with random names. Returns the saved records."""
    os.makedirs(upload_dir, exist_ok=True)
    saved = []
    try:
        for img in images:
            filename = f"{uuid.uuid4().hex}.{img['ext']}"
            path = os.path.join(upload_dir, filename)
            with open(path, "wb") as fh:
                fh.write(img["data"])
                fh.flush()
                os.fsync(fh.fileno())
            saved.append({"filename": filename, "original_name": img["original_name"],
                          "content_type": img["mime"], "size_bytes": len(img["data"])})
    except OSError:
        delete_files(upload_dir, [s["filename"] for s in saved])
        raise
    return saved


def delete_files(upload_dir, filenames):
    for name in filenames:
        if not SAFE_NAME.match(name or ""):
            continue
        try:
            os.remove(os.path.join(upload_dir, name))
        except FileNotFoundError:
            pass
