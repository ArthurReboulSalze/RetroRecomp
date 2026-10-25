"""The start-up picture the packaged converter shows while it unpacks: the
application's own banner (as in the header and on the site) and its version.
Packaging writes it next to its work files, so the version always matches."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path, version: str) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    banner = Image.open(ROOT / 'assets/Retro-Recomp-banner.png').convert('RGBA')
    banner = banner.resize((420, round(banner.height * 420 / banner.width)), Image.LANCZOS)
    width, height = 480, 170
    image = Image.new('RGB', (width, height), '#1c1c1c')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline='#d4a737', width=2)
    image.paste(banner, ((width - banner.width) // 2, 26), banner)
    draw.rectangle((150, 132, width - 150, 134), fill='#d4a737')
    # The interface font subset carries the Latin digits and letters.
    font = ImageFont.truetype(str(ROOT / 'assets/RetroRecomp-UI-JP.otf'), 13)
    text = f'v{version}'
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((width - 14 - (right - left), height - 12 - bottom), text, font=font, fill='#9a9a9a')
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, optimize=True)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--version')
    args = parser.parse_args()
    if args.version is None:
        sys.path.insert(0, str(ROOT))
        from retrorecomp import __version__
        args.version = __version__
    print(build(args.destination, args.version))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
