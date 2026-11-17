"""Draw the Trading Journal icon (white atom on black) as .icns, .ico or .png.  Usage: make_journal_icon.py OUT"""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024


def draw():
    pad = 90  # macOS icons sit inside a margin
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((pad, pad, SIZE - pad, SIZE - pad), radius=190, fill=(0, 0, 0, 255),
                        outline=(48, 48, 48, 255), width=6)
    c = SIZE / 2

    # soft glow behind the core
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 170, c - 170, c + 170, c + 170), fill=(255, 255, 255, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))

    d = ImageDraw.Draw(img)
    d.ellipse((c - 330, c - 330, c + 330, c + 330), outline=(255, 255, 255, 90), width=10)  # outer ring
    d.ellipse((c - 200, c - 200, c + 200, c + 200), outline=(255, 255, 255, 255), width=22)  # orbit
    d.ellipse((c - 72, c - 72, c + 72, c + 72), fill=(255, 255, 255, 255))  # nucleus
    a = math.radians(-45)  # electron on the outer ring
    ex, ey = c + 330 * math.cos(a), c + 330 * math.sin(a)
    d.ellipse((ex - 52, ey - 52, ex + 52, ey + 52), fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    out = sys.argv[1]
    img = draw()
    if out.endswith(".icns"):
        img.save(out, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    elif out.endswith(".ico"):
        img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    else:
        img.save(out)
