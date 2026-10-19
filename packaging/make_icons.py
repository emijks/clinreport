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


def draw(size: int, sheet=ACCENT, lines=WHITE) -> Image.Image:
    scale = 8  # supersample, then downscale for smooth edges
    s = size * scale / 32  # the favicon is drawn on a 32-unit grid
    image = Image.new('RGBA', (size * scale, size * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    # sheet: 5..27 x 2..30, folded corner 20..27 x 2..9
    d.rounded_rectangle([5 * s, 2 * s, 27 * s, 30 * s], radius=2 * s, fill=sheet)
    d.polygon([(20 * s, 2 * s), (27 * s, 9 * s), (27 * s, 2 * s)], fill=(0, 0, 0, 0))
    d.rectangle([20 * s, 1 * s, 28 * s, 2 * s], fill=(0, 0, 0, 0))
    d.polygon([(20 * s, 2 * s), (27 * s, 9 * s), (22 * s, 9 * s), (20 * s, 7 * s)], fill=FOLD)
    for y, width in ((14, 14), (19, 14), (24, 9)):
        d.rounded_rectangle([9 * s, y * s, (9 + width) * s, (y + 2.4) * s], radius=1.2 * s, fill=lines)
    return image.resize((size, size), Image.LANCZOS)


PANEL_TOP = (31, 95, 168)
PANEL_BOTTOM = (18, 58, 108)
# Inno Setup wizard images at 100 / 150 / 200 % display scaling (24-bit BMP, no transparency).
WIZARD_LARGE = ((164, 314), (246, 471), (328, 628))
WIZARD_SMALL = (55, 83, 110)


def wizard_large(width: int, height: int) -> Image.Image:
    """Welcome/finish page panel: vertical accent gradient with the white report sheet in the upper third."""
    panel = Image.new('RGB', (width, height))
    d = ImageDraw.Draw(panel)
    for y in range(height):
        t = y / (height - 1)
        d.line([(0, y), (width, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(PANEL_TOP, PANEL_BOTTOM, strict=True)))
    size = width * 3 // 5
    sheet = draw(size, sheet=WHITE, lines=ACCENT)  # inverted colours read better on the dark panel
    panel.paste(sheet, ((width - size) // 2, height // 4), sheet)
    return panel


def wizard_small(size: int) -> Image.Image:
    """Top-right image of the inner pages: the icon on white."""
    image = Image.new('RGB', (size, size), (255, 255, 255))
    icon = draw(size)
    image.paste(icon, (0, 0), icon)
    return image


def main():
    big = draw(1024)
    big.resize((512, 512), Image.LANCZOS).save(HERE / 'icon.png')
    (HERE / 'windows').mkdir(exist_ok=True)
    draw(256).save(
        HERE / 'windows' / 'clinreport.ico',
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for width, height in WIZARD_LARGE:
        wizard_large(width, height).save(HERE / 'windows' / f'wizard-large-{width}.bmp')
    for size in WIZARD_SMALL:
        wizard_small(size).save(HERE / 'windows' / f'wizard-small-{size}.bmp')
    (HERE / 'macos').mkdir(exist_ok=True)
    big.save(HERE / 'macos' / 'ClinReport.icns')
    print('written: icon.png, windows/clinreport.ico, windows/wizard-*.bmp, macos/ClinReport.icns')


if __name__ == '__main__':
    main()
