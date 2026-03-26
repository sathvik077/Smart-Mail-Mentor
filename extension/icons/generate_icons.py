"""
Generate extension icons (icon16.png, icon48.png, icon128.png) without any
third-party dependencies — uses only Python's built-in struct and zlib.

Run once during setup:
  python extension/icons/generate_icons.py
"""
import os
import struct
import zlib

# Smart Mail Mentor brand blue
ICON_COLOR = (66, 133, 244)   # #4285f4


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    length  = struct.pack(">I", len(data))
    payload = chunk_type + data
    crc     = struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    return length + payload + crc


def make_png(size: int, rgb: tuple) -> bytes:
    """Return raw bytes of a solid-color PNG of the given size."""
    r, g, b = rgb

    # IHDR: width, height, bit-depth=8, color-type=2 (RGB), rest zeros
    ihdr_data = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)

    # Raw image data: one filter byte (0) + RGB pixels per row
    row   = b"\x00" + bytes([r, g, b] * size)
    raw   = row * size
    idat  = zlib.compress(raw, level=9)

    png  = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr_data)
    png += _chunk(b"IDAT", idat)
    png += _chunk(b"IEND", b"")
    return png


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    for size in (16, 48, 128):
        path = os.path.join(out_dir, f"icon{size}.png")
        with open(path, "wb") as f:
            f.write(make_png(size, ICON_COLOR))
        print(f"  Created {path}")
    print("Done.")
