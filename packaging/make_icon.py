"""Draw the app icon (build time only; needs Pillow, MIT-CMU license).

Drawn in code so the repo holds no binary image files. PyInstaller converts
the PNG to .ico (Windows) / .icns (macOS) using Pillow.

    python packaging/make_icon.py build/icon.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
BLUE = (47, 91, 211, 255)
WHITE = (255, 255, 255, 255)


def draw(path: Path) -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, SIZE - 40, SIZE - 40], radius=200, fill=BLUE)
    w = 64
    # A radical sign: small tick, long stroke down, long stroke up, then the bar.
    d.line([(210, 560), (300, 510), (420, 780), (560, 260), (840, 260)], fill=WHITE, width=w, joint="curve")
    # "x" under the bar.
    d.line([(620, 400), (800, 640)], fill=WHITE, width=w)
    d.line([(800, 400), (620, 640)], fill=WHITE, width=w)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


if __name__ == "__main__":
    draw(Path(sys.argv[1] if len(sys.argv) > 1 else "build/icon.png"))
