"""Local RAW decoding and metadata. No changes are made to source files."""

from io import BytesIO
from pathlib import Path
from fractions import Fraction
from math import isfinite
from contextlib import contextmanager
import mmap

import exifread
import numpy as np
import rawpy
from PIL import Image, ImageOps

DETAIL_FIELDS = (
    "Filename", "Resolution", "DPI", "File size", "Device", "Date taken",
    "Lens", "Aperture", "Shutter speed", "ISO", "Focal length",
    "35mm equivalent", "Exposure compensation", "Exposure program",
    "Metering mode", "Flash", "White balance", "Color space",
    "Bits per sample", "Color encoding",
)

RAW_EXTENSIONS = {
    ".raw",
    ".cr2",
    ".cr3",
    ".crw",
    ".nef",
    ".nrw",
    ".arw",
    ".srf",
    ".sr2",
    ".raf",
    ".orf",
    ".rw2",
    ".rwl",
    ".pef",
    ".ptx",
    ".srw",
    ".3fr",
    ".fff",
    ".iiq",
    ".kdc",
    ".dcr",
    ".mos",
    ".mrw",
    ".erf",
}


def category(path):
    suffix = Path(path).suffix.lower()
    return "DNG" if suffix == ".dng" else "RAW" if suffix in RAW_EXTENSIONS else None


def read_tags(path):
    try:
        with open(path, "rb") as stream:
            return exifread.process_file(stream, details=False, strict=False)
    except Exception:
        return {}


def metadata(path, tags=None, dimensions=None):
    path = Path(path)
    tags = read_tags(path) if tags is None else tags

    def value(*keys):
        for key in keys:
            if key in tags and str(tags[key]).strip():
                return str(tags[key])
        return None

    def numeric(key):
        try:
            tag = tags[key]
            raw = tag.values[0] if hasattr(tag, "values") else tag
            result = float(Fraction(str(raw)))
            return result if isfinite(result) else None
        except (KeyError, ValueError, TypeError, IndexError, ZeroDivisionError, OverflowError):
            return None

    def measured(key, suffix="", prefix="", positive=False):
        number = numeric(key)
        if number is None or (positive and number <= 0):
            return "N/A"
        return f"{prefix}{number:g}{suffix}"

    exposure = numeric("EXIF ExposureTime")
    shutter = "N/A"
    if exposure is not None and exposure > 0:
        shutter = (f"{Fraction(exposure).limit_denominator(1000000)} s"
                   if exposure < 1 else f"{exposure:g} s")
    bias = numeric("EXIF ExposureBiasValue")
    color_code = numeric("EXIF ColorSpace")
    color_space = {1: "sRGB", 2: "Adobe RGB", 65535: "Uncalibrated"}.get(
        color_code, value("EXIF ColorSpace") or "N/A")
    encoding_code = numeric("Image PhotometricInterpretation")
    encoding = {0: "White is zero", 1: "Black is zero", 2: "RGB", 3: "Palette",
                5: "CMYK", 6: "YCbCr", 8: "CIELab", 32803: "Color filter array (RAW)",
                34892: "Linear RAW"}.get(encoding_code,
                    value("Image PhotometricInterpretation") or "N/A")
    bit_depth = "N/A"
    try:
        bits = [int(bit) for bit in tags["Image BitsPerSample"].values]
        if bits and all(bit > 0 for bit in bits):
            bit_depth = (str(bits[0]) if len(set(bits)) == 1 else " / ".join(map(str, bits))) + " bits"
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
        pass

    width = value("EXIF ExifImageWidth", "Image ImageWidth")
    height = value("EXIF ExifImageLength", "Image ImageLength")
    resolution = (
        f"{dimensions[0]} × {dimensions[1]}"
        if dimensions
        else (f"{width} × {height}" if width and height else "N/A")
    )
    dpi = "N/A"
    try:

        def number(key):
            raw = tags[key].values[0]
            return float(raw.num) / raw.den if hasattr(raw, "num") else float(raw)

        unit = number("Image ResolutionUnit")
        if unit in (2, 3):
            factor = 2.54 if unit == 3 else 1
            x, y = (
                number("Image XResolution") * factor,
                number("Image YResolution") * factor,
            )
            dpi = f"{x:g} × {y:g} DPI"
    except (
        KeyError,
        ValueError,
        TypeError,
        AttributeError,
        ZeroDivisionError,
        IndexError,
    ):
        pass
    try:
        size = path.stat().st_size
        filesize = f"{size / (1024 * 1024):.2f} MB ({size:,} bytes)"
    except OSError:
        filesize = "N/A"
    device = " ".join(
        dict.fromkeys(filter(None, [value("Image Make"), value("Image Model")]))
    )
    return {
        "Filename": path.name or "N/A",
        "Resolution": resolution,
        "DPI": dpi,
        "File size": filesize,
        "Device": device or "N/A",
        "Date taken": value("EXIF DateTimeOriginal", "EXIF DateTimeDigitized") or "N/A",
        "Lens": value("EXIF LensModel", "Image LensModel") or "N/A",
        "Aperture": measured("EXIF FNumber", prefix="f/", positive=True),
        "Shutter speed": shutter,
        "ISO": measured("EXIF ISOSpeedRatings", positive=True),
        "Focal length": measured("EXIF FocalLength", " mm", positive=True),
        "35mm equivalent": measured("EXIF FocalLengthIn35mmFilm", " mm", positive=True),
        "Exposure compensation": f"{bias:+.2f} EV" if bias is not None else "N/A",
        "Exposure program": value("EXIF ExposureProgram") or "N/A",
        "Metering mode": value("EXIF MeteringMode") or "N/A",
        "Flash": value("EXIF Flash") or "N/A",
        "White balance": value("EXIF WhiteBalance") or "N/A",
        "Color space": color_space,
        "Bits per sample": bit_depth,
        "Color encoding": encoding,
    }


@contextmanager
def open_raw(path):
    """Open camera RAWs, or a uint16 pixel dump using its companion DNG."""
    path = Path(path)
    try:
        raw = rawpy.imread(str(path))
    except rawpy.LibRawFileUnsupportedError:
        if path.suffix.lower() != ".raw":
            raise
        companions = [p for p in path.parent.iterdir()
                      if p.is_file() and p.stem == path.stem
                      and p.suffix.lower() == ".dng"]
        if len(companions) != 1:
            raise ValueError(
                "Headerless RAW requires one matching DNG in the same folder "
                "(same filename stem)."
            ) from None
        companion = companions[0]
        with rawpy.imread(str(companion)) as raw:
            pixels = raw.raw_image
            if pixels.dtype != np.uint16 or path.stat().st_size != pixels.nbytes:
                raise ValueError("RAW byte size does not match the companion DNG's uint16 pixels.")
            # Read into LibRaw's writable buffer, retaining the DNG's calibration.
            # Memory mapping avoids an additional full-size copy of the dump.
            with path.open("rb") as stream:
                with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                    pixels[:] = np.ndarray(pixels.shape, dtype="<u2", buffer=mapped)
            yield raw, read_tags(companion), False
    else:
        with raw:
            yield raw, read_tags(path), True


def decode(path, preview=True):
    with open_raw(path) as (raw, tags, has_embedded_preview):
        dimensions = (raw.sizes.width, raw.sizes.height)
        embedded = False
        if preview and has_embedded_preview:
            try:
                thumb = raw.extract_thumb()
                image = (
                    Image.open(BytesIO(thumb.data)).convert("RGB")
                    if thumb.format == rawpy.ThumbFormat.JPEG
                    else Image.fromarray(thumb.data)
                )
                embedded = True
            except (
                rawpy.LibRawNoThumbnailError,
                rawpy.LibRawUnsupportedThumbnailError,
            ):
                image = Image.fromarray(
                    raw.postprocess(half_size=True, use_camera_wb=True)
                )
        else:
            image = Image.fromarray(raw.postprocess(half_size=preview, use_camera_wb=True))
        if embedded:
            # LibRaw rotates postprocessed output; embedded previews need EXIF orientation.
            try:
                orientation = int(tags["Image Orientation"].values[0])
                transforms = {
                    2: Image.Transpose.FLIP_LEFT_RIGHT,
                    3: Image.Transpose.ROTATE_180,
                    4: Image.Transpose.FLIP_TOP_BOTTOM,
                    5: Image.Transpose.TRANSPOSE,
                    6: Image.Transpose.ROTATE_270,
                    7: Image.Transpose.TRANSVERSE,
                    8: Image.Transpose.ROTATE_90,
                }
                if orientation in transforms:
                    image = image.transpose(transforms[orientation])
            except (KeyError, ValueError, TypeError, IndexError):
                image = ImageOps.exif_transpose(image)
        image.thumbnail(
            (640, 640) if preview else (6000, 6000), Image.Resampling.LANCZOS
        )
        return image.convert("RGB"), metadata(path, tags, dimensions)
