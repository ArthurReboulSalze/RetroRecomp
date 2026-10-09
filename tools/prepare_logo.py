"""Prepare the app icon and UI banner from MEDIAS; preserve the originals."""
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont, ImageOps
from smsrecomp.paths import ROOT
from smsrecomp.artwork import ICON_SIZES
from smsrecomp.branding import COLORS, wordmark_rectangles

def main():
    directory = ROOT / "assets"
    directory.mkdir(exist_ok=True)
    with Image.open(ROOT / "MEDIAS/RetroRecomp_logo_outlined.png") as source:
        logo = ImageOps.exif_transpose(source).convert("RGBA")
    # Ignore the almost invisible pixels around the supplied transparent logo.
    # Keep the source PNG intact, including its original colors and geometry.
    visible = logo.getchannel("A").point(lambda alpha: 255 if alpha >= 16 else 0).getbbox()
    if not visible:
        raise ValueError('The application logo is empty')
    logo = logo.crop(visible)
    original_logo = logo.copy()
    logo = ImageOps.contain(logo, (256, 256), Image.Resampling.LANCZOS)
    square = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    square.alpha_composite(logo, ((256-logo.width)//2, (256-logo.height)//2))
    square.save(directory / "Retro-Recomp.ico", sizes=[(n, n) for n in ICON_SIZES])
    # Tk's ICO loader scales the first entry. Supply explicit PNG sizes so
    # its window/taskbar icons retain the same pixels as the EXE resources.
    with Image.open(directory / "Retro-Recomp.ico") as icon:
        for size in ICON_SIZES:
            icon.ico.getimage((size, size)).save(directory / f"Retro-Recomp-icon-{size}.png")
    # Reproducible native artwork: supplied logo + original pixel wordmark.
    # The GUI adds a translated tagline; the README banner uses English.
    factor = 3
    banner = Image.new('RGBA', (600*factor, 132*factor))
    emblem = ImageOps.contain(original_logo, (150*factor, 106*factor), Image.Resampling.LANCZOS)
    banner.alpha_composite(emblem, (0, (132*factor-emblem.height)//2))
    draw = ImageDraw.Draw(banner)
    for box, color in wordmark_rectangles(172*factor, 40*factor, 5*factor):
        left, top, right, bottom = box
        draw.rectangle((left, top, right-1, bottom-1), fill=color)
    banner.resize((600, 132), Image.Resampling.LANCZOS).save(directory / 'Retro-Recomp-banner.png')
    try:
        font = ImageFont.truetype('segoeui.ttf', 9*factor)
    except OSError:
        font = ImageFont.load_default(size=9*factor)
    draw.text((172*factor, 94*factor), 'YOUR ROMS. EVERY PLATFORM. MADE SIMPLE.',
              font=font, fill=COLORS['muted'], spacing=0)
    # Use the generated transparent artwork; only trim and scale for the header.
    with Image.open(ROOT / 'MEDIAS/RetroRecomp_consoles.png') as source:
        consoles = ImageOps.exif_transpose(source).convert('RGBA')
    bounds = consoles.getchannel('A').point(lambda alpha: 255 if alpha >= 16 else 0).getbbox()
    if not bounds:
        raise ValueError('The header illustration is empty')
    ImageOps.contain(consoles.crop(bounds), (238, 76), Image.Resampling.LANCZOS).save(
        directory / 'Retro-Recomp-consoles.png')
    # An opaque charcoal banner keeps the white wordmark readable in either
    # GitHub theme, using the same artwork and neutral palette as the app.
    published = Image.new('RGBA', (900*factor, 132*factor), COLORS['header'])
    published.alpha_composite(banner, (24*factor, 0))
    hardware = ImageOps.contain(consoles.crop(bounds), (238*factor, 76*factor), Image.Resampling.LANCZOS)
    published.alpha_composite(hardware, (570*factor, 56*factor))
    published_draw = ImageDraw.Draw(published)
    for x, y, size in ((900-56, 104, 10), (900-43, 91, 12)):
        published_draw.rectangle((x*factor, y*factor, (x+size)*factor-1, (y+size)*factor-1),
                                 fill=COLORS['gold'])
    published.save(ROOT / 'MEDIAS/RetroRecomp_ban.png')
    shutil.copyfile(ROOT / "MEDIAS/TAG_SHOOTING.png", directory / "tag-shooting.png")
    print(directory / "Retro-Recomp.ico")

if __name__ == "__main__":
    main()
