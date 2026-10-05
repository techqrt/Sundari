import os
from urllib.parse import urlsplit

from PIL import Image

from sunndari.constants import Constants

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024

# Pillow format name -> extensions that are acceptable for it
IMAGE_FORMATS = {
    'JPEG': ('.jpg', '.jpeg'),
    'PNG': ('.png',),
    'WEBP': ('.webp',),
}
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.webm')

# Extension -> the only Content-Type we ever serve a stored upload with.
SAFE_CONTENT_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.webp': 'image/webp', '.pdf': 'application/pdf',
}


def _extension(file) -> str:
    return os.path.splitext(file.name or '')[1].lower()


def _check_size(file, max_bytes: int) -> None:
    if file.size is None or file.size <= 0:
        raise ValueError(Constants.upload_empty)
    if file.size > max_bytes:
        raise ValueError(f'{Constants.upload_too_large} ({max_bytes // (1024 * 1024)} MB maximum)')


def validate_image(file, max_bytes: int = MAX_IMAGE_BYTES) -> None:
    """Accepts only real JPEG/PNG/WEBP images: the bytes must decode as an image whose
    detected format matches the file extension — the client-supplied Content-Type and
    file name alone are never trusted."""
    _check_size(file, max_bytes)
    extension = _extension(file)
    try:
        file.seek(0)
        with Image.open(file) as image:
            detected = image.format
            image.verify()
    except Exception:
        raise ValueError(Constants.upload_invalid_image)
    finally:
        file.seek(0)
    if detected not in IMAGE_FORMATS or extension not in IMAGE_FORMATS[detected]:
        raise ValueError(Constants.upload_invalid_image)


def validate_image_or_pdf(file, max_bytes: int = MAX_IMAGE_BYTES) -> None:
    if _extension(file) != '.pdf':
        validate_image(file, max_bytes=max_bytes)
        return
    _check_size(file, max_bytes)
    file.seek(0)
    header = file.read(1024)
    file.seek(0)
    if b'%PDF-' not in header:
        raise ValueError(Constants.upload_invalid_document)


def validate_video(file, max_bytes: int = MAX_VIDEO_BYTES) -> None:
    _check_size(file, max_bytes)
    extension = _extension(file)
    if extension not in VIDEO_EXTENSIONS:
        raise ValueError(Constants.upload_invalid_video)
    file.seek(0)
    header = file.read(12)
    file.seek(0)
    is_isobmff = header[4:8] == b'ftyp'  # mp4 / mov
    is_webm = header[:4] == b'\x1a\x45\xdf\xa3'
    if not ((extension in ('.mp4', '.mov') and is_isobmff) or (extension == '.webm' and is_webm)):
        raise ValueError(Constants.upload_invalid_video)


def validate_portfolio_media(file, media_type: str) -> None:
    if media_type == 'video':
        validate_video(file)
    else:
        validate_image(file)


def absolute_file_url(model_field, name, present_url: str):
    """Public media URL for a stored file name, made absolute with the host of the request
    being served (None when no file is set)."""
    if not name:
        return None
    parts = urlsplit(present_url or '')
    origin = f'{parts.scheme}://{parts.netloc}' if parts.netloc else ''
    return origin + model_field.storage.url(name)
