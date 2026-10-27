import io
import os

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

MAX_SIDE = 1800
QUALITY_CHOICES = [
    ("90", "Alta calidad (archivo más grande)"),
    ("80", "Media (recomendada)"),
    ("60", "Baja (máxima compresión)"),
]
DEFAULT_QUALITY = "80"


def to_jpeg(uploaded, quality=DEFAULT_QUALITY):
    """Convierte la imagen subida a JPEG, la reduce si es muy grande y la comprime."""
    try:
        quality = int(quality)
    except (TypeError, ValueError):
        quality = int(DEFAULT_QUALITY)
    quality = min(max(quality, 30), 95)
    uploaded.seek(0)
    image = ImageOps.exif_transpose(Image.open(uploaded))
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    stem = os.path.splitext(os.path.basename(getattr(uploaded, "name", "ficha")))[0] or "ficha"
    return ContentFile(buffer.getvalue(), name=f"{stem[:80]}.jpg")
