#! /usr/bin/env python3
"""Draw the app icon (the review page's favicon: a report sheet with a folded corner) and write
icon.png, windows/clinreport.ico and macos/ClinReport.icns. Needs Pillow; run once after a design change
and commit the outputs:  python packaging/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ACCENT = (31, 95, 168, 255)
FOLD = (143, 179, 221, 255)
WHITE = (255, 255, 255, 255)


def draw(size: int) -> Image.Image:
    scale = 8  # supersample, then downscale for smooth edges
    s = size * scale / 32  # the favicon is drawn on a 32-unit grid
    image = Image.new('RGBA', (size * scale, size * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    # sheet: 5..27 x 2..30, folded corner 20..27 x 2..9
    d.rounded_rectangle([5 * s, 2 * s, 27 * s, 30 * s], radius=2 * s, fill=ACCENT)
    d.polygon([(20 * s, 2 * s), (27 * s, 9 * s), (27 * s, 2 * s)], fill=(0, 0, 0, 0))
    d.rectangle([20 * s, 1 * s, 28 * s, 2 * s], fill=(0, 0, 0, 0))
    d.polygon([(20 * s, 2 * s), (27 * s, 9 * s), (22 * s, 9 * s), (20 * s, 7 * s)], fill=FOLD)
    for y, width in ((14, 14), (19, 14), (24, 9)):
        d.rounded_rectangle([9 * s, y * s, (9 + width) * s, (y + 2.4) * s], radius=1.2 * s, fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


def main():
    big = draw(1024)
    big.resize((512, 512), Image.LANCZOS).save(HERE / 'icon.png')
    (HERE / 'windows').mkdir(exist_ok=True)
    draw(256).save(
        HERE / 'windows' / 'clinreport.ico',
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    (HERE / 'macos').mkdir(exist_ok=True)
    big.save(HERE / 'macos' / 'ClinReport.icns')
    print('written: icon.png, windows/clinreport.ico, macos/ClinReport.icns')


if __name__ == '__main__':
    main()
