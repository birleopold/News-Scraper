"""Draw the app icon (the dashboard's green "W" badge) as a multi-size .ico, so the
installer needs no downloaded artwork. Run by build.ps1."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEAL, GOLD, WHITE = (20, 108, 91), (232, 180, 73), (255, 255, 255)


def badge(size):
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 4, fill=TEAL)
    try:
        font = ImageFont.truetype('segoeuib.ttf', int(size * 0.62))
    except OSError:
        font = ImageFont.load_default(int(size * 0.62))
    box = draw.textbbox((0, 0), 'W', font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), 'W', font=font, fill=WHITE)
    dot = size * 0.19
    draw.ellipse((size * 0.70, size * 0.12, size * 0.70 + dot, size * 0.12 + dot), fill=GOLD)
    return image


if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'installer/app.ico')
    badge(256).save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f'Icon written: {target}')
