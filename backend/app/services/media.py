"""Bounded image decoding, metadata removal, and transaction-safe replacement."""

import warnings
from io import BytesIO
from threading import BoundedSemaphore

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import delete

from app.models.media import ItemPhoto
from app.schemas.items import ItemRead
from app.services.claims import lock_item, moderator

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 12_000_000
image_slots = BoundedSemaphore(2)


def normalize_image(data, content_type):
    if not data:
        raise HTTPException(422, "Photo is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photo exceeds 2 MiB")
    formats = {"image/jpeg": "JPEG", "image/png": "PNG"}
    if content_type not in formats:
        raise HTTPException(415, "Choose a JPEG or PNG photo")
    if not image_slots.acquire(blocking=False):
        raise HTTPException(
            503, "Image processing temporarily busy", headers={"Retry-After": "1"}
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != formats[content_type]:
                    raise HTTPException(
                        415, "Photo content does not match its media type"
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(415, "Animated images are not supported")
                width, height = source.size
                if width > 6000 or height > 6000 or width * height > 12_000_000:
                    raise HTTPException(
                        422,
                        "Photo dimensions exceed the 12-megapixel or 6000-pixel limit",
                    )
                source.verify()
            with Image.open(BytesIO(data)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((1600, 1600))
                # Fresh canvas drops EXIF/GPS, text, ICC profiles, and filenames.
                rgba = oriented.convert("RGBA")
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                for size in (1600, 1200):
                    clean.thumbnail((size, size))
                    output = BytesIO()
                    clean.save(output, format="JPEG", quality=80)
                    if output.tell() <= 1024 * 1024:
                        return output.getvalue()
                raise HTTPException(
                    413, "Photo remains too large; choose a smaller image"
                )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            422, "Photo is corrupt, unsafe, or cannot be decoded"
        ) from None
    finally:
        image_slots.release()


def change_photo(session, item_id, user, data=None, content_type=None):
    # Verify permissions before decoding, then recheck under the shared report lock.
    from app.models.items import Item

    current = session.get(Item, item_id)
    if current is None:
        raise HTTPException(404, "Item not found")
    moderator(current, user)
    if current.archived:
        raise HTTPException(409, "Archived report photos cannot be changed")
    normalized = normalize_image(data, content_type) if data is not None else None
    item = lock_item(session, item_id)
    moderator(item, user)
    if item.archived:
        raise HTTPException(409, "Archived report photos cannot be changed")
    if normalized is None:
        session.execute(delete(ItemPhoto).where(ItemPhoto.item_id == item_id))
        item.photo_version = 0
    else:
        photo = session.get(ItemPhoto, item_id)
        if photo is None:
            session.add(ItemPhoto(item_id=item_id, data=normalized))
        else:
            photo.data = normalized
        item.photo_version += 1
    from datetime import datetime, timezone

    item.updated_at = datetime.now(timezone.utc)
    result = ItemRead.model_validate(item)
    session.commit()
    return result
