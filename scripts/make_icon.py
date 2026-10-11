"""Draw the app icon and save it as .icns (macOS), .ico (Windows) or .png.  Usage: make_icon.py OUT"""
import sys

from PIL import Image, ImageDraw

SIZE = 1024


def draw():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 90  # macOS icons sit inside a margin
    d.rounded_rectangle((pad, pad, SIZE - pad, SIZE - pad), radius=190, fill=(17, 22, 29, 255),
                        outline=(47, 58, 73, 255), width=8)
    # The rising line from the in-app logo (viewBox 32: 7,22 -> 13,15 -> 18,19 -> 25,10).
    scale, off = (SIZE - 2 * pad) / 32 * 0.9, pad + (SIZE - 2 * pad) * 0.05
    pts = [(off + x * scale, off + y * scale) for x, y in ((6, 22), (13, 14.5), (18.5, 19), (26, 9.5))]
    d.line(pts, fill=(52, 211, 153, 255), width=70, joint="curve")
    r = 35
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=(52, 211, 153, 255))
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
