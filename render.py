"""麺処 松もり: Generate clear, dated 1080x1350 JPEG announcements.
No image-generation API and no bundled font files are needed.
"""
from __future__ import annotations

import math
import random
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1350
JP_DAYS = "月火水木金土日"
REG_FONT = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
)
BOLD_FONT = (
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc",
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (BOLD_FONT if bold else REG_FONT):
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=0)
    raise RuntimeError("Noto Serif CJK JP not found. Install fonts-noto-cjk.")


def paper_base(closed: bool) -> Image.Image:
    # Both versions share the same motifs and layout. Closed is slightly darker.
    base = (250, 247, 239) if not closed else (238, 230, 219)
    im = Image.new("RGB", (W, H), base)
    rng = random.Random(8421)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(overlay, "RGBA")

    circles = [(-80, -125, 550, 410), (740, -110, 1240, 350),
               (-235, 745, 395, 1440), (730, 805, 1425, 1580)]
    for i, bb in enumerate(circles):
        c = (231, 207, 166, 44 if i % 2 == 0 else 24)
        if closed:
            c = (182, 164, 144, 42 if i % 2 == 0 else 25)
        g.ellipse(bb, fill=c)

    # Fine gold elliptical arcs only at the edges.
    gold = (181, 150, 94, 102 if not closed else 75)
    for bbox in [(-440, -620, 760, 440), (730, -350, 1730, 630),
                 (-560, 850, 450, 1760), (770, 680, 1570, 1500)]:
        g.arc(bbox, start=8, end=320, fill=gold, width=2)

    # Abstract, faint botanical sprigs at corners; nothing resembling a storefront.
    leaf_color = (126, 133, 109, 83) if not closed else (108, 114, 104, 75)
    stem_color = (143, 135, 107, 100) if not closed else (118, 113, 100, 95)
    sprigs = [((78, 260), (280, -60), -1), ((945, 1160), (1155, 840), 1)]
    for (x1, y1), (x2, y2), direction in sprigs:
        g.line([(x1, y1), (x2, y2)], fill=stem_color, width=3)
        for j in range(7):
            t = (j + 0.7) / 9
            x = x1 + (x2-x1)*t
            y = y1 + (y2-y1)*t
            sgn = 1 if j % 2 == 0 else -1
            lx = x + sgn*direction*44
            ly = y - 17 - j*2
            g.line([(x, y), (lx, ly)], fill=stem_color, width=2)
            # each leaf is a rotated ellipse in its small own overlay
            l = Image.new("RGBA", (78, 32), (0,0,0,0))
            ld = ImageDraw.Draw(l)
            ld.ellipse((0, 4, 72, 27), fill=leaf_color)
            l = l.rotate(-32 if sgn*direction > 0 else 30, expand=True)
            overlay.alpha_composite(l, (int(lx-l.width/2), int(ly-l.height/2)))

    for _ in range(220):
        x = rng.randrange(W)
        y = rng.randrange(H)
        if 80 < x < 1000 and 320 < y < 940:
            continue
        r = rng.choice([1, 1, 2])
        g.ellipse((x-r,y-r,x+r,y+r), fill=(190, 161, 113, rng.randint(15, 35)))

    im = Image.alpha_composite(im.convert("RGBA"), overlay)
    # very faint grain creates visual interest without harming legibility
    noise = Image.effect_noise((W,H), 18).convert('L')
    noise_color = Image.merge('RGB', (noise,noise,noise))
    im = Image.blend(im.convert('RGB'), noise_color, 0.026)
    return im


def centered(draw: ImageDraw.ImageDraw, y: int, txt: str, f: ImageFont.FreeTypeFont,
             fill: str, max_width: int = 980) -> None:
    bbox = draw.textbbox((0, 0), txt, font=f)
    tw = bbox[2] - bbox[0]
    if tw > max_width:
        raise ValueError(f"Text too wide ({tw}px): {txt}")
    draw.text((W//2, y), txt, anchor="mt", font=f, fill=fill)


def rule(d: ImageDraw.ImageDraw, y: int, closed: bool) -> None:
    gold = '#b5a082' if not closed else '#a8957d'
    d.line([(309,y),(495,y)], fill=gold, width=2)
    d.line([(585,y),(771,y)], fill=gold, width=2)
    c = W//2
    d.polygon([(c,y-7),(c+7,y),(c,y+7),(c-7,y)], outline=gold, width=2)


def render(day: date, status: str, path: str | Path) -> Path:
    closed = status == 'closed'
    image = paper_base(closed)
    d = ImageDraw.Draw(image)
    ink = '#4d3b2c' if not closed else '#514438'
    date_line = f"{day.month}月{day.day}日（{JP_DAYS[day.weekday()]}曜日）"
    centered(d, 325, date_line, font(65), ink)
    rule(d, 448, closed)
    message = '本日定休日です' if closed else '本日営業します'
    centered(d, 520, message, font(112), ink)
    rule(d, 725, closed)
    if closed:
        centered(d, 815, 'またのご来店をお待ちしております', font(38), ink)
    else:
        centered(d, 795, '営業時間  11:00〜15:00', font(52), ink)
        centered(d, 875, 'L.O.14:30', font(42), ink)
    d.line([(446,1110),(634,1110)], fill='#c4ae8d' if not closed else '#b7a48e', width=2)
    centered(d, 1140, '麺処 松もり', font(58), ink)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, 'JPEG', quality=93, subsampling=0, optimize=True)
    return target


if __name__ == '__main__':
    from datetime import date as d
    render(d(2026,10,14), 'open', Path('preview')/'営業日_見本.jpg')
    render(d(2026,10,15), 'closed', Path('preview')/'定休日_見本.jpg')
