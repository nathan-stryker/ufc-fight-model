"""Profile picture + banner for the site's social accounts, written to brand/.

Same identity as the favicon (web/make_icons.py) and the masthead wordmark:
CALL in red, THE stacked in brass, CARD in blue, on the ring-canvas black.

Run: python web/make_social_images.py
"""
import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from make_icons import draw as draw_icon

WEB_DIR = Path(__file__).resolve().parent
OUT_DIR = WEB_DIR.parent / "brand"
CANVAS, RED, BLUE, GOLD, INK_DIM = "#16130E", "#D20A0A", "#6376E9", "#C6963C", "#A99878"


def font(name, px):
    f = TTFont(WEB_DIR / "fonts" / name)
    f.flavor = None
    buf = io.BytesIO()
    f.save(buf)
    buf.seek(0)
    return ImageFont.truetype(buf, px)


def banner(w=1920, h=384, k=1.0):
    """k scales the type; layout is proportional to the canvas."""
    im = Image.new("RGB", (w, h), CANVAS)
    d = ImageDraw.Draw(im)
    big, the = font("oswald-700.woff2", int(150 * k)), font("oswald-700.woff2", int(34 * k))
    tag = font("barlow-700.woff2", int(34 * k))
    cx, cy = w / 2, h * 0.43
    gap = 26 * k
    # CALL | T-H-E | CARD, laid out like the masthead's three-column grid
    tw = max(d.textbbox((0, 0), ch, font=the)[2] for ch in "THE")
    l, t, r, b = d.textbbox((0, 0), "CALL", font=big)
    d.text((cx - tw / 2 - gap - r, cy - (t + b) / 2), "CALL", font=big, fill=RED)
    l, t, r, b = d.textbbox((0, 0), "CARD", font=big)
    d.text((cx + tw / 2 + gap - l, cy - (t + b) / 2), "CARD", font=big, fill=BLUE)
    for i, ch in enumerate("THE"):
        l, t, r, b = d.textbbox((0, 0), ch, font=the)
        d.text((cx - (l + r) / 2, cy + (i - 1) * 40 * k - (t + b) / 2), ch, font=the, fill=GOLD)
    # red / brass / blue rule
    ry, rw, rh = h * 0.70, 300 * k, 6 * k
    d.rectangle((cx - rw / 2, ry, cx + rw / 2, ry + rh), fill=GOLD)
    d.rectangle((cx - rw / 2, ry, cx - rw * 0.05, ry + rh), fill=RED)
    d.rectangle((cx + rw * 0.05, ry, cx + rw / 2, ry + rh), fill=BLUE)
    text = "UFC PREDICTIONS FOR EVERY FIGHT, EVERY WEEK"
    l, t, r, b = d.textbbox((0, 0), text, font=tag)
    d.text((cx - (l + r) / 2, h * 0.84 - (t + b) / 2), text, font=tag, fill=INK_DIM)
    return im


def main():
    OUT_DIR.mkdir(exist_ok=True)
    # square, no rounded corners -- Reddit/X crop avatars to a circle themselves
    draw_icon(rounded=False).convert("RGB").resize((512, 512), Image.LANCZOS).save(OUT_DIR / "avatar.png")
    banner().save(OUT_DIR / "banner.png")  # Reddit profile banner
    # X header is 3:1, and the profile picture overlaps its bottom-left corner,
    # so the wordmark stays centred and clear of that area
    banner(1500, 500, k=1.15).save(OUT_DIR / "x-header.png")
    print(f"wrote avatar.png, banner.png, x-header.png -> {OUT_DIR}")


if __name__ == "__main__":
    main()
