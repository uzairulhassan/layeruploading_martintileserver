"""Avatar sanitization — re-encode uploads with Pillow before storage."""
from __future__ import annotations

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import serializers

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_MAX_EDGE = 512


def sanitize_avatar_upload(uploaded_file) -> ContentFile:
    """Decode pixels and rewrite as JPEG/PNG (drops EXIF / polyglot payloads)."""
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > AVATAR_MAX_BYTES:
        raise serializers.ValidationError("Image must be 2 MB or smaller.")

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise serializers.ValidationError("Use a valid JPG or PNG image.") from exc

    image = ImageOps.exif_transpose(image) or image
    image.thumbnail((AVATAR_MAX_EDGE, AVATAR_MAX_EDGE), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image.convert("RGBA").save(buffer, format="PNG", optimize=True)
        filename = "avatar.png"
    else:
        image.convert("RGB").save(buffer, format="JPEG", quality=85, optimize=True)
        filename = "avatar.jpg"

    data = buffer.getvalue()
    if len(data) > AVATAR_MAX_BYTES:
        raise serializers.ValidationError("Image must be 2 MB or smaller after processing.")
    return ContentFile(data, name=filename)
