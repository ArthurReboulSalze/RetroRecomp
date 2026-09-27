"""Prepare the app icon and UI banner from MEDIAS; preserve the originals."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageOps
from smsrecomp.paths import ROOT
from smsrecomp.artwork import ICON_SIZES

def main():
    directory = ROOT / "assets"
    directory.mkdir(exist_ok=True)
    with Image.open(ROOT / "MEDIAS/RetroRecomp_logo.png") as source:
        logo = ImageOps.exif_transpose(source).convert("RGBA")
    logo = logo.crop(logo.getchannel("A").getbbox())
    logo = ImageOps.contain(logo, (256, 256), Image.Resampling.LANCZOS)
    square = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    square.alpha_composite(logo, ((256-logo.width)//2, (256-logo.height)//2))
    square.save(directory / "Retro-Recomp.ico", sizes=[(n, n) for n in ICON_SIZES])
    # Tk's ICO loader scales the first entry. Supply explicit PNG sizes so
    # its window/taskbar icons retain the same pixels as the EXE resources.
    with Image.open(directory / "Retro-Recomp.ico") as icon:
        for size in ICON_SIZES:
            icon.ico.getimage((size, size)).save(directory / f"Retro-Recomp-icon-{size}.png")
    with Image.open(ROOT / "MEDIAS/RetroRecomp_ban.png") as source:
        banner = ImageOps.exif_transpose(source).convert("RGBA")
    banner = ImageOps.contain(banner, (600, 200), Image.Resampling.LANCZOS)
    # Trim the nearly transparent canvas around the artwork; keep four pixels
    # around its visible glow. The artwork retains its scale and proportions.
    visible = banner.getchannel("A").point(lambda alpha: 255 if alpha >= 32 else 0).getbbox()
    if visible:
        left, top, right, bottom = visible
        banner = banner.crop((max(0, left-4), max(0, top-4),
                              min(banner.width, right+4), min(banner.height, bottom+4)))
    banner.save(directory / "Retro-Recomp-banner.png")
    print(directory / "Retro-Recomp.ico")

if __name__ == "__main__":
    main()
