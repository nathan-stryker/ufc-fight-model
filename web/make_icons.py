"""Draw the site's favicon set into web/icons/ (copied to docs/ by build_site.py).

A cream Oswald "C" on a red/blue corner split with a brass seam -- the same
corner colours and face as the masthead wordmark. Chosen over a "CC"
monogram because it's the only option that stays legible at 16px, which is
the size browser tabs and Google's search results actually show.

Run: python web/make_icons.py   (only needed if the design changes)
"""
import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

WEB_DIR = Path(__file__).resolve().parent
OUT_DIR = WEB_DIR / "icons"
RED, BLUE, GOLD, INK = "#D20A0A", "#6376E9", "#C6963C", "#F0E6D2"
S = 512  # drawn large, downsampled for each size


def oswald(px):
    # Pillow can't read WOFF2, so unwrap the embedded web font to plain TTF.
    f = TTFont(WEB_DIR / "fonts" / "oswald-700.woff2")
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, px)


def draw(rounded=True):
    bg = Image.new("RGBA", (S, S), RED)
    d = ImageDraw.Draw(bg)
    d.rectangle((S / 2, 0, S, S), fill=BLUE)
    d.rectangle((S / 2 - 10, 0, S / 2 + 10, S), fill=GOLD)
    fnt = oswald(470)
    l, t, r, b = d.textbbox((0, 0), "C", font=fnt)
    d.text((S / 2 - (l + r) / 2, S * 0.47 - (t + b) / 2), "C", font=fnt, fill=INK)
    if not rounded:  # iOS rounds the corners itself and fills transparency black
        return bg
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=96, fill=255)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    im.paste(bg, (0, 0), mask)
    return im


def main():
    OUT_DIR.mkdir(exist_ok=True)
    im = draw()
    im.save(OUT_DIR / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    im.resize((192, 192), Image.LANCZOS).save(OUT_DIR / "icon-192.png")
    draw(rounded=False).convert("RGB").resize((180, 180), Image.LANCZOS).save(OUT_DIR / "apple-touch-icon.png")
    print(f"wrote icons -> {OUT_DIR}")


if __name__ == "__main__":
    main()
