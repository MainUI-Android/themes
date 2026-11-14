"""Chalkboard: a school blackboard. Green slate with eraser smudges, a wooden frame and chalk
ledge, and everything drawn in dusty white and pastel chalk."""
import math
import random
import struct
import wave
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, GLYPHS, SS, TILES, Pen, Style, finish, hexc, rgba, system_ids

BOARD = (43, 67, 54)
BOARD_D = (30, 49, 39)
CHALK = (241, 239, 229)
DUST = (178, 194, 184)     # unfocused labels
INKD = (26, 42, 34)        # dark slate: lines and text on chalk fills
YELLOW = (250, 226, 128)
PINK = (246, 172, 192)
BLUE = (158, 206, 242)
MINT = (170, 226, 174)
ORANGE = (249, 190, 126)
LILAC = (204, 186, 238)
WOOD = (110, 70, 40)
WOOD_D = (70, 43, 24)
WOOD_L = (156, 108, 66)
TILE_COLOR = {"recent": BLUE, "favorite": YELLOW, "game": MINT, "emulators": PINK, "retroarch": ORANGE,
              "app": LILAC, "setting": CHALK}
ICON_COLORS = [BLUE, PINK, MINT, YELLOW, LILAC, ORANGE]
DETAIL = {BLUE: YELLOW, PINK: BLUE, MINT: PINK, YELLOW: PINK, LILAC: YELLOW, ORANGE: BLUE}
APP_COLOR = {"activity": MINT, "download": BLUE, "folder": YELLOW, "gallery": PINK, "gameswitcher": ORANGE,
             "pacman": YELLOW, "retroarch": ORANGE, "search": BLUE, "themes": PINK, "tweaks": LILAC}
INVADER = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX",
           "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."]


def S(v):
    return v * SS


def seed_of(*parts):
    return zlib.crc32("/".join(str(p) for p in parts).encode())


def clear(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def blank(w, h):
    return Image.new("L", (w * SS, h * SS), 0)


def noise_l(size, seed):
    return Image.frombytes("L", size, random.Random(seed).randbytes(size[0] * size[1]))


def paint(color, mask):
    """[color] through the L [mask] (the colour's alpha scales it)."""
    out = Image.new("RGBA", mask.size, rgba(color))
    if len(color) > 3 and color[3] != 255:
        mask = mask.point(lambda v, k=color[3]: v * k // 255)
    out.putalpha(mask)
    return out


def lean(im, n=64):
    """Fewer distinct colours: the noisy chalk layers then pack far smaller as PNG."""
    return im.quantize(n, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGBA")


def over(im, color, mask):
    return Image.alpha_composite(im, paint(color, mask))


def grain(size, seed, holes=0.3, patch=0.35):
    """Chalk on slate (L multiplier, 1x): pitted where the stick skipped the board's grain,
    a little thinner in patches where it was pressed lightly."""
    w, h = size
    lo, hi = int(256 * holes * 0.4), int(256 * holes)
    pit = noise_l(size, seed).point(lambda v: 40 if v < lo else 150 if v < hi else 255)
    p = noise_l((max(2, w // 6), max(2, h // 6)), seed + 1).resize(size, Image.BICUBIC)
    base = int(255 * (1 - patch))
    return ImageChops.multiply(pit, p.point(lambda v: base + v * (255 - base) // 255))


def chalky(im, seed, holes=0.3, patch=0.35):
    """[im] (1x RGBA) given a chalk texture through its alpha."""
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.getchannel("A"), grain(im.size, seed, holes, patch)))
    return out


def wobble(im, amp, wave_len, seed):
    """Hand-drawn jitter: [im] displaced smoothly by about [amp] px (in [im]'s pixels)."""
    rnd = random.Random(seed)

    def comps():
        out = []
        for _ in range(3):
            a = rnd.uniform(0, math.tau)
            k = math.tau / (wave_len * rnd.uniform(0.7, 1.4))
            out.append((math.cos(a) * k, math.sin(a) * k, rnd.uniform(0, math.tau)))
        return out

    cx, cy = comps(), comps()

    def f(x, y, cs):
        return amp * sum(math.sin(x * kx + y * ky + p) for kx, ky, p in cs) / 1.7

    st = max(4, int(wave_len / 6))
    xs = list(range(0, im.width, st)) + [im.width]
    ys = list(range(0, im.height, st)) + [im.height]
    pt = {(x, y): (x + f(x, y, cx), y + f(x, y, cy)) for x in xs for y in ys}
    data = []
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            data.append(((x0, y0, x1, y1), pt[x0, y0] + pt[x0, y1] + pt[x1, y1] + pt[x1, y0]))
    return im.transform(im.size, Image.Transform.MESH, data, Image.Resampling.BILINEAR)


def streaks(size, seed, lo=0.75, run=24, angle=0):
    """Rubbed chalk: streaks along the stroke (L, 1x), between [lo] and full."""
    w, h = size
    big = int(math.hypot(w, h)) + 4
    n = noise_l((max(2, big // run), max(2, big // 2)), seed).resize((big, big), Image.BICUBIC)
    if angle:
        n = n.rotate(angle, Image.BILINEAR)
    n = n.crop(((big - w) // 2, (big - h) // 2, (big - w) // 2 + w, (big - h) // 2 + h))
    b = int(255 * lo)
    return n.point(lambda v: b + v * (255 - b) // 255)


class Chalk:
    """Chalk strokes on a supersampled canvas, in 1x coordinates: wobbly, uneven pressure."""

    def __init__(self, im, seed):
        self.d = ImageDraw.Draw(im)
        self.rnd = random.Random(seed)

    def path(self, pts, c, w, wob=0.5, step=1.2, taper=False):
        dense = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            dense += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
        dense.append(pts[-1])
        p1, p2, p3 = (self.rnd.uniform(0, math.tau) for _ in range(3))
        n = len(dense)
        prev = None
        for i, (x, y) in enumerate(dense):
            a, b = dense[max(0, i - 2)], dense[min(n - 1, i + 2)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            tl = math.hypot(tx, ty) or 1
            s = i * step
            off = wob * (0.6 * math.sin(s / 11 + p1) + 0.4 * math.sin(s / 29 + p2))
            x, y = x - ty / tl * off, y + tx / tl * off
            t = i / max(1, n - 1)
            pr = min(1.0, 0.6 + t * 6, 0.6 + (1 - t) * 6) if taper else 1.0
            r = w * pr * (0.88 + 0.12 * math.sin(s / 7 + p3)) / 2
            if prev is not None:
                self.d.line((S(prev[0]), S(prev[1]), S(x), S(y)), fill=c, width=max(1, int(S(2 * r))))
            self.d.ellipse((S(x - r), S(y - r), S(x + r), S(y + r)), fill=c)
            prev = (x, y)

    def box(self, x0, y0, x1, y1, r, c, w, over=10, wob=0.6):
        """A rounded box in one stroke, its end running on past its start."""
        pts = []

        def corner(cx, cy, a0):
            for i in range(7):
                a = math.radians(a0 + i * 15)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

        pts.append((x0 + r + 3, y0 - 0.8))
        corner(x1 - r, y0 + r, -90)
        corner(x1 - r, y1 - r, 0)
        corner(x0 + r, y1 - r, 90)
        corner(x0 + r, y0 + r, 180)
        pts.append((x0 + r + 3 + over, y0 + 1.2))
        self.path(pts, c, w, wob=wob)

    def loop(self, cx, cy, rx, ry, c, w, over=0.5, wob=0.4):
        """A chalk circle: one loop overshooting its start, slightly spiralling."""
        a0 = self.rnd.uniform(-2.6, -1.9)
        ph = self.rnd.uniform(0, math.tau)
        pts = []
        n = max(40, int((rx + ry) * 2))
        for i in range(n + 1):
            t = i / n
            a = a0 + t * (math.tau + over)
            k = (1 + 0.03 * math.sin(2 * a + ph)) * (0.97 + 0.06 * t)
            pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
        self.path(pts, c, w, wob=wob)


def rough_rect(w, h, box, r, seed, jag=0.8):
    """Rounded-rect mask (SS L) with a slightly irregular, hand-rubbed edge."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    pts = []

    def corner(cx, cy, a0):
        for i in range(10):
            a = math.radians(a0 + i * 10)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    def edge(xa, ya, xb, yb):
        n = max(1, int(math.hypot(xb - xa, yb - ya) / 5))
        for i in range(1, n):
            t = i / n
            pts.append((xa + (xb - xa) * t + rnd.uniform(-jag, jag), ya + (yb - ya) * t + rnd.uniform(-jag, jag)))

    corner(x1 - r, y0 + r, -90)
    edge(x1, y0 + r, x1, y1 - r)
    corner(x1 - r, y1 - r, 0)
    edge(x1 - r, y1, x0 + r, y1)
    corner(x0 + r, y1 - r, 90)
    edge(x0, y1 - r, x0, y0 + r)
    corner(x0 + r, y0 + r, 180)
    edge(x0 + r, y0, x1 - r, y0)
    m = blank(w, h)
    ImageDraw.Draw(m).polygon([(S(x), S(y)) for x, y in pts], fill=255)
    return m


def rough_disc(w, h, cx, cy, r, seed, jag=0.05):
    rnd = random.Random(seed)
    ph = rnd.uniform(0, math.tau)
    pts = []
    for i in range(60):
        a = i / 60 * math.tau
        k = 1 + jag * math.sin(3 * a + ph) + rnd.uniform(-jag, jag) * 0.5
        pts.append((S(cx + r * k * math.cos(a)), S(cy + r * k * math.sin(a))))
    m = blank(w, h)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def rub(mask, color, seed, density=0.92, run=24, angle=-8, holes=0.07, lo=0.7):
    """Chalk rubbed in with the side of the stick, through [mask] (1x L): 1x RGBA. (Alpha in
    steps, so the large fills stay small as PNG.)"""
    size = mask.size
    a = ImageChops.multiply(mask, streaks(size, seed, lo, run, angle))
    a = ImageChops.multiply(a, grain(size, seed + 5, holes, 0.15))
    return paint(color, a.point(lambda v: min(255, int(v * density / 12 + 0.5) * 12)))


def wood(w, h, seed, base=WOOD, amp=16):
    """Planed wood (1x RGB), grain running along x."""
    rnd = random.Random(seed)
    long_ = noise_l((max(2, w // 70), h), seed).resize((w, h), Image.BICUBIC)
    fine = noise_l((max(2, w // 9), h), seed + 1).resize((w, h), Image.BICUBIC)
    g = ImageChops.add(long_.point(lambda v: v * 6 // 10), fine.point(lambda v: v * 4 // 10))
    # a few darker figure lines that drift across the board
    fig = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(fig)
    for _ in range(max(2, h // 9)):
        y0 = rnd.uniform(0, h)
        ph, k, a = rnd.uniform(0, math.tau), rnd.uniform(90, 220), rnd.uniform(0.6, 2.4)
        d.line([(x, y0 + a * math.sin(x / k + ph)) for x in range(0, w + 8, 8)], fill=rnd.randint(40, 90), width=1)
    g = ImageChops.subtract(g, fig.filter(ImageFilter.GaussianBlur(0.5)))
    off = g.point(lambda v: max(0, min(255, 128 + (v - 128) * amp // 64)))
    im = Image.new("RGB", (w, h), base)
    return ImageChops.add(im, Image.merge("RGB", (off,) * 3), 1, -128)


def invader(d, cx, cy, s, c):
    px = s * 2 / 11
    x0, y0 = cx - px * 5.5, cy - px * 4
    for j, row in enumerate(INVADER):
        for i, ch in enumerate(row):
            if ch == "X":
                d.rectangle([round(S(x0 + i * px)), round(S(y0 + j * px)),
                             round(S(x0 + (i + 1) * px)), round(S(y0 + (j + 1) * px))], fill=c)


def star_pts(cx, cy, r0, r1, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r0 if i % 2 == 0 else r1
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def tile_shape(d, key, cx, cy, s):
    """What gets coloured in on each menu drawing (same geometry as the kit's TILES)."""
    def pg(pts):
        d.polygon([(S(x), S(y)) for x, y in pts], fill=255)

    if key == "recent":
        d.ellipse([S(cx - s * 0.92), S(cy - s * 0.92), S(cx + s * 0.92), S(cy + s * 0.92)], fill=255)
    elif key == "favorite":
        pg(star_pts(cx, cy, s, s * 0.46))
    elif key == "game":
        pg([(cx + s * x, cy + s * y) for x, y in ((-1, -0.25), (-0.75, -0.55), (0.75, -0.55), (1, -0.25), (1.05, 0.45),
                                                  (0.75, 0.62), (0.45, 0.3), (-0.45, 0.3), (-0.75, 0.62), (-1.05, 0.45))])
    elif key == "emulators":
        d.rounded_rectangle([S(cx - s * 0.62), S(cy - s), S(cx + s * 0.62), S(cy + s)], radius=S(s * 0.18), fill=255)
    elif key == "app":
        h = s * 0.36
        for dx in (-1, 1):
            for dy in (-1, 1):
                x, y = cx + dx * s * 0.52, cy + dy * s * 0.52
                d.rounded_rectangle([S(x - h), S(y - h), S(x + h), S(y + h)],
                                    radius=S(h * (1 if (dx, dy) == (1, -1) else 0.35)), fill=255)
    elif key == "setting":
        pts = []
        for i in range(32):
            a = math.radians(i * 360 / 32 - 90 + 360 / 8 / 8)
            r = s if (i % 4) in (1, 2) else s * 0.76
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        pg(pts)
        d.ellipse([S(cx - s * 0.3), S(cy - s * 0.3), S(cx + s * 0.3), S(cy + s * 0.3)], fill=0)


def enclosed(walls, w, h):
    """Areas the line work (SS L) closes in completely, found at 2x: SS L mask."""
    w2, h2 = w * 2, h * 2
    wall = walls.resize((w2, h2), Image.BOX).point(lambda v: 255 if v > 50 else 0)
    pad = Image.new("L", (w2 + 2, h2 + 2), 0)
    pad.paste(wall, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    inside = pad.crop((1, 1, w2 + 1, h2 + 1)).point(lambda v: 255 if v == 0 else 0)
    return inside.filter(ImageFilter.MaxFilter(3)).resize((w * SS, h * SS), Image.BILINEAR)


class Theme(Style):
    name = "Chalkboard"
    author = "MainUI"
    description = "A school blackboard: green slate, eraser smudges, a wooden frame and ledge, all drawn in dusty pastel chalk."

    bg_top = BOARD
    bg_bottom = BOARD
    accent = YELLOW
    accent2 = PINK
    highlight = YELLOW
    text = CHALK
    muted = DUST
    glyph_n = CHALK
    glyph_f = INKD
    panel = (31, 50, 40)
    panel_alpha = 246
    bar = WOOD
    bar_alpha = 255

    font_file = "GochiHand-Regular.ttf"
    font_license = "OFL-GochiHand.txt"
    logo_font = "CabinSketch-Bold.ttf"   # drawn into the logo only
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 32, 26, 27, 26, 17, 20
    icon_quant = 32
    sel_icons = True    # on the yellow focused card: dark lines instead of white chalk

    # ---- board, frame and ledge -----------------------------------------------------------
    def background(self, w=640, h=480):
        rnd = random.Random(17)
        im = Image.new("RGB", (w, h), BOARD)
        blot = noise_l((w // 80 + 2, h // 80 + 2), 3).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(16))
        blot = blot.point(lambda v: int(128 + (v - 128) * 0.13))
        im = ImageChops.add(im, Image.merge("RGB", (blot,) * 3), 1, -128).convert("RGBA")
        # eraser swipes: broad arcs of chalk haze, streaked along the wipe
        haze = Image.new("L", (w * 2, h * 2), 0)
        d = ImageDraw.Draw(haze)
        for cx, cy, r, a0, a1, band in ((150, 300, 230, 196, 320, 90), (540, 130, 250, 30, 150, 80),
                                        (360, 470, 280, 214, 300, 70), (20, 40, 200, 340, 430, 60)):
            for k in range(40):
                rr = r - band / 2 + band * rnd.random()
                span = (a1 - a0) * rnd.uniform(0.35, 1.0)
                st = a0 + rnd.uniform(0, a1 - a0 - span)
                a = rnd.randint(5, 22) if rnd.random() < 0.85 else rnd.randint(22, 40)
                d.arc([(cx - rr) * 2, (cy - rr) * 2, (cx + rr) * 2, (cy + rr) * 2], st, st + span, fill=a,
                      width=rnd.randint(2, 7))
        haze = haze.filter(ImageFilter.GaussianBlur(4)).resize((w, h), Image.LANCZOS)
        im = over(im, CHALK, haze)
        # ghosts of erased lessons
        ghost = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(ghost)
        f = self.font1x(30)
        for (x, y, s, ang) in ((392, 96, "a² + b² = c²", -4), (46, 404, "3 × 4 = 12", 3),
                               (430, 326, "ABC", -2), (80, 150, "x = 7", 5)):
            t = Image.new("RGBA", (260, 70), (0, 0, 0, 0))
            ImageDraw.Draw(t).text((10, 35), s, font=f, fill=rgba(CHALK, 30), anchor="lm")
            t = t.rotate(ang, Image.BICUBIC, expand=True)
            ghost.alpha_composite(t, (int(x - 10), int(y - t.height / 2)))
        for cx, cy in ((560, 250), (250, 120)):
            gd.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=rgba(CHALK, 22), width=3)
        ghost = ghost.filter(ImageFilter.GaussianBlur(1.6))
        im = Image.alpha_composite(im, ghost)
        # dust
        specks = noise_l((w, h), 23).point(lambda v: 56 if v > 252 else 0)
        im = over(im, CHALK, specks)
        # chalk dust settled along the bottom, above the ledge
        settle = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(settle)
        for i in range(30):
            y = h - 60 - i * 0.7
            sd.line((0, y, w, y), fill=max(0, 26 - i))
        settle = ImageChops.multiply(settle, streaks((w, h), 41, 0.2, 40))
        return Image.alpha_composite(im, paint(CHALK, settle))

    def header_bar(self):
        """The top of the frame: a wooden rail, a groove, and its shadow on the slate."""
        w, h = 640, 60
        body = wood(w, 50, 31).convert("RGBA")
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        im.paste(body, (0, 0))
        d = ImageDraw.Draw(im)
        d.line((0, 0, w, 0), fill=rgba(WOOD_D))
        d.line((0, 1, w, 1), fill=rgba(WOOD_L, 120))
        d.line((0, 46, w, 46), fill=rgba(WOOD_L, 110))
        d.rectangle((0, 47, w, 49), fill=rgba(WOOD_D))
        for i in range(10):
            d.line((0, 50 + i, w, 50 + i), fill=(8, 16, 12, int(140 * (1 - i / 10) ** 1.6)))
        return lean(im, 96)

    def footer_bar(self):
        """The ledge: its top face dusted with chalk, then its front."""
        w, h = 640, 60
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        top = wood(w, 10, 32, WOOD_L, 12).convert("RGBA")
        front = wood(w, 46, 33, WOOD, 16).convert("RGBA")
        shade = Image.new("RGBA", (w, 46), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for i in range(46):
            sd.line((0, i, w, i), fill=(20, 10, 4, int(10 + 70 * i / 45)))
        front = Image.alpha_composite(front, shade)
        im.paste(top, (0, 2))
        im.paste(front, (0, 14))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, w, 1), fill=rgba(BOARD_D))
        d.line((0, 12, w, 12), fill=rgba((186, 136, 88)))
        d.line((0, 13, w, 13), fill=rgba(WOOD_D))
        # chalk dust on the top face
        dust = Image.new("L", (w, h), 0)
        ImageDraw.Draw(dust).rectangle((0, 3, w, 11), fill=110)
        dust = ImageChops.multiply(dust, streaks((w, h), 34, 0.0, 30))
        dust = ImageChops.multiply(dust, noise_l((w, h), 35).point(lambda v: 255 if v > 120 else 90))
        im = over(im, CHALK, dust)
        return lean(im, 96)

    def logo(self):
        w, h = 170, 46
        im = clear(w, h)
        d = ImageDraw.Draw(im)
        f = self.font(34, self.logo_font)
        d.text((S(5), S(21)), "MainUI", font=f, fill=rgba(CHALK), anchor="lm", stroke_width=int(S(0.5)), stroke_fill=rgba(CHALK))
        tw = d.textlength("MainUI", font=f) / SS
        Chalk(im, 4).path([(6, 39.5), (5 + tw * 0.5, 38), (8 + tw, 39)], rgba(YELLOW), 3.0, wob=0.6, taper=True)
        return chalky(finish(im), 5, 0.14, 0.15)

    # ---- lists --------------------------------------------------------------------------
    def selection(self, h):
        """Circled in yellow chalk, with a little colour rubbed in: list text stays white."""
        w = 640
        pad = 6 if h < 70 else 9
        m = finish(rough_rect(w, h, (8, pad, w - 8, h - pad), (h - 2 * pad) / 2.2, seed_of("selm", h)))
        im = rub(m, rgba(YELLOW, 255), seed_of("selr", h), 0.2, 40, 0)
        ring = clear(w, h)
        Chalk(ring, seed_of("sel", h)).box(7, pad - 1, w - 7, h - pad + 1, (h - 2 * pad) / 2.2, rgba(YELLOW), 3.0, over=14, wob=0.8)
        return lean(Image.alpha_composite(im, chalky(finish(ring), seed_of("selg", h), 0.26, 0.2)))

    def divider(self):
        im = clear(640, 4)
        Chalk(im, 8).path([(22, 2), (320, 2.3), (618, 1.8)], rgba(CHALK, 46), 1.3, wob=0.25, step=3)
        return chalky(finish(im), 9, 0.4, 0.4)

    # ---- tiles --------------------------------------------------------------------------
    def _frame(self, w, h, box, r, focused, color, seed):
        """A chalk outline (unfocused) or a box rubbed full of [color] chalk (focused)."""
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if focused:
            m = finish(rough_rect(w, h, box, r, seed))
            im = Image.alpha_composite(im, rub(m, rgba(color), seed + 1, 0.96, 26, -10, 0.015, 0.76))
        ring = clear(w, h)
        x0, y0, x1, y1 = box
        Chalk(ring, seed + 2).box(x0, y0, x1, y1, r, rgba(CHALK if not focused else color, 255 if focused else 120),
                                  3.2 if focused else 2.2, over=12)
        return lean(Image.alpha_composite(im, chalky(finish(ring), seed + 3, 0.3, 0.3)))

    def card(self, w, h, focused):
        return self._frame(w, h, (8, 10, w - 9, h - 9), 12, focused, YELLOW, seed_of("card", w, h, focused))

    def tile_base(self, focused):
        return self._frame(156, 278, (12, 14, 144, 262), 14, focused, YELLOW, seed_of("tile", focused))

    def tile_glyph(self, key, focused):
        w, h = 156, 278
        cx, cy, s = 78, 112, 40
        col = TILE_COLOR[key]
        seed = seed_of("glyph", key, focused)
        if key == "retroarch":
            g = clear(w, h)
            invader(ImageDraw.Draw(g), cx, cy, s, rgba(INKD if focused else col))
            g = finish(wobble(g, S(0.5), S(40), seed))
            return chalky(g, seed + 1, 0.2, 0.2) if not focused else g
        m = blank(w, h)
        tile_shape(ImageDraw.Draw(m), key, cx + 1.5, cy + 1.5, s)
        m = finish(wobble(m, S(1.0), S(40), seed + 2))
        fill = rub(m, rgba(CHALK if focused else col), seed + 3, 1.0, 16, -32, 0.04, 0.84)
        ln = clear(w, h)
        TILES[key](ImageDraw.Draw(ln), cx, cy, s, rgba(INKD if focused else CHALK), 5.4)
        ln = finish(wobble(ln, S(0.9), S(30), seed + 4))
        if not focused:
            gap = ln.getchannel("A").filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.5))
            fill.putalpha(ImageChops.subtract(fill.getchannel("A"), gap))
        ln = chalky(ln, seed + 5, 0.12 if focused else 0.22, 0.15 if focused else 0.25)
        return Image.alpha_composite(fill, ln)

    def home_tile(self, key, focused):
        if key is None:
            return self.tile_base(focused)
        base = self._frame(156, 278, (12, 14, 144, 262), 14, focused, TILE_COLOR[key], seed_of("tile", key, focused))
        return lean(Image.alpha_composite(base, self.tile_glyph(key, focused)))

    # ---- buttons and small parts ----------------------------------------------------------
    BUTTONS = {"A": YELLOW, "B": PINK, "X": BLUE, "Y": MINT}

    def button(self, label, primary):
        n = 54
        seed = seed_of("btn", label)
        m = finish(rough_disc(n, n, n / 2, n / 2, 21, seed))
        im = rub(m, rgba(self.BUTTONS[label]), seed + 1, 1.0, 14, -30, 0.03, 0.8)
        ring = clear(n, n)
        Chalk(ring, seed + 2).loop(n / 2, n / 2, 21.5, 21.5, rgba(self.BUTTONS[label]), 2.4, over=0.35)
        d = ImageDraw.Draw(ring)
        d.text((S(n / 2), S(n / 2 + 1)), label, font=self.font(30), fill=rgba(INKD), anchor="mm",
               stroke_width=int(S(0.7)), stroke_fill=rgba(INKD))
        return Image.alpha_composite(im, chalky(finish(ring), seed + 3, 0.1, 0.1))

    def pill(self, label, w, h=48):
        im = clear(w, h)
        seed = seed_of("pill", label)
        Chalk(im, seed).box(4, 10, w - 4, h - 10, 9, rgba(CHALK), 2.2, over=8)
        ImageDraw.Draw(im).text((S(w / 2), S(h / 2 + 1)), label, font=self.font(21), fill=rgba(CHALK), anchor="mm")
        return chalky(finish(im), seed + 1, 0.22, 0.2)

    def dot(self, active):
        im = clear(24, 14)
        c = Chalk(im, seed_of("dot", active))
        if active:
            im = over(im, rgba(YELLOW), rough_disc(24, 14, 12, 7, 5.4, 3, 0.06))
        else:
            c.loop(12, 7, 3.4, 3.4, rgba(CHALK, 190), 1.8, over=0.3, wob=0.15)
        return chalky(finish(im), seed_of("dotg", active), 0.18, 0.15)

    def toggle(self, on):
        w, h = 92, 44
        seed = seed_of("toggle", on)
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if on:
            m = finish(rough_rect(w, h, (10, 11, 82, 33), 11, seed))
            im = rub(m, rgba(MINT), seed + 1, 0.95, 16, -10)
        lay = clear(w, h)
        c = Chalk(lay, seed + 2)
        c.box(10, 11, 82, 33, 11, rgba(MINT if on else CHALK, 255 if on else 190), 2.3, over=9)
        if on:
            knob = rough_disc(w, h, 70, 22, 8, seed + 3)
            lay = over(lay, rgba(CHALK), knob)
            Chalk(lay, seed + 4).loop(70, 22, 8.5, 8.5, rgba(INKD, 200), 1.6, over=0.3)
        else:
            c.loop(22, 22, 7.5, 7.5, rgba(CHALK, 210), 2.0, over=0.4)
        return Image.alpha_composite(im, chalky(finish(lay), seed + 5, 0.2, 0.2))

    def arrow(self, left, size=24):
        im = clear(size, size)
        xs = (0.64, 0.34) if left else (0.36, 0.66)
        Chalk(im, seed_of("arrow", left, size)).path(
            [(size * xs[0], size * 0.2), (size * xs[1], size * 0.5), (size * xs[0], size * 0.8)], rgba(CHALK), size * 0.14, wob=0.2)
        return chalky(finish(im), seed_of("arrowg", left, size), 0.15, 0.15)

    def panel_image(self, w, h):
        if w >= 600:
            return self._slate(w, h)
        # pop-up menus: a darker slate flush under MainUI's title strip, chalk-ruled edges
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, w, h - 4), fill=rgba(self.panel, 250))
        d.rectangle((0, h - 4, w, h - 1), fill=rgba(WOOD))
        d.line((0, h - 4, w, h - 4), fill=rgba(WOOD_L))
        ring = clear(w, h)
        c = Chalk(ring, seed_of("pop", h))
        c.path([(6, 3), (6, h - 10)], rgba(CHALK, 150), 1.8, wob=0.4)
        c.path([(w - 6, 3), (w - 6, h - 10)], rgba(CHALK, 150), 1.8, wob=0.4)
        c.path([(4, h - 9), (w - 4, h - 10)], rgba(CHALK, 150), 1.8, wob=0.4)
        return lean(Image.alpha_composite(im, chalky(finish(ring), seed_of("popg", h), 0.3, 0.3)))

    def _slate(self, w, h):
        """A small framed slate (dialogs): four mitred rails, grain along each."""
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        fr = (14, 10, w - 14, h - 10)
        t = 14
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle(fr, radius=4, fill=255)
        im.alpha_composite(paint((0, 0, 0, 120), m.filter(ImageFilter.GaussianBlur(5))), (0, 4))
        x0, y0, x1, y1 = fr
        horiz = wood(w, h, 51, WOOD, 16)
        vert = wood(h, w, 53, WOOD, 16).rotate(90, expand=True)
        rails = (([(x0, y0), (x1, y0), (x1 - t, y0 + t), (x0 + t, y0 + t)], horiz, 0),
                 ([(x0, y1), (x1, y1), (x1 - t, y1 - t), (x0 + t, y1 - t)], horiz, -18),
                 ([(x0, y0), (x0 + t, y0 + t), (x0 + t, y1 - t), (x0, y1)], vert, -8),
                 ([(x1, y0), (x1 - t, y0 + t), (x1 - t, y1 - t), (x1, y1)], vert, -12))
        for pts, tex, shade in rails:
            rm = Image.new("L", (w, h), 0)
            ImageDraw.Draw(rm).polygon(pts, fill=255)
            rail = ImageChops.add(tex, Image.new("RGB", (w, h), (0, 0, 0)), 1, shade).convert("RGBA") if shade else tex.convert("RGBA")
            rail.putalpha(ImageChops.multiply(rm, m))
            im = Image.alpha_composite(im, rail)
        d = ImageDraw.Draw(im)
        d.line((x0 + 1, y0 + 1, x1 - 1, y0 + 1), fill=rgba(WOOD_L, 170))
        for (xa, ya), (xb, yb) in (((x0, y0), (x0 + t, y0 + t)), ((x1, y0), (x1 - t, y0 + t)),
                                   ((x0, y1), (x0 + t, y1 - t)), ((x1, y1), (x1 - t, y1 - t))):
            d.line((xa, ya, xb, yb), fill=rgba(WOOD_D, 200))
        inner = (x0 + t, y0 + t, x1 - t, y1 - t)
        mi = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mi).rectangle(inner, fill=255)
        slate = Image.new("RGBA", (w, h), rgba(self.panel))
        slate = Image.alpha_composite(slate, paint(CHALK, ImageChops.multiply(
            noise_l((w, h), 52).point(lambda v: 40 if v > 250 else 0), mi)))
        sh = Image.new("L", (w, h), 0)
        ImageDraw.Draw(sh).rectangle((inner[0], inner[1], inner[2], inner[1] + 5), fill=90)
        slate = Image.alpha_composite(slate, paint((0, 0, 0), sh.filter(ImageFilter.GaussianBlur(2))))
        slate.putalpha(mi)
        im = Image.alpha_composite(im, slate)
        ImageDraw.Draw(im).rectangle((inner[0] - 1, inner[1] - 1, inner[2] + 1, inner[3] + 1), outline=rgba(WOOD_D))
        return lean(im, 96)

    def folder_icon(self):
        n = 60
        seed = 61
        m = blank(n, n)
        s, cx, cy = 19, 30, 31
        body = [(cx - s, cy + s * 0.7), (cx - s, cy - s * 0.65), (cx - s * 0.3, cy - s * 0.65),
                (cx - s * 0.1, cy - s * 0.4), (cx + s, cy - s * 0.4), (cx + s, cy + s * 0.7)]
        ImageDraw.Draw(m).polygon([(S(x + 1), S(y + 1)) for x, y in body], fill=255)
        im = rub(finish(m), rgba(YELLOW), seed, 1.0, 10, -30, 0.03, 0.84)
        ln = clear(n, n)
        Chalk(ln, seed + 1).path(body + [body[0]], rgba(CHALK), 3.0, wob=0.3)
        ln = finish(ln)
        im.putalpha(ImageChops.subtract(im.getchannel("A"), ln.getchannel("A").filter(ImageFilter.MaxFilter(3))))
        return Image.alpha_composite(im, chalky(ln, seed + 2, 0.15, 0.15))

    def favorite_mark(self):
        w, h = 34, 39
        m = blank(w, h)
        pts = star_pts(17, 20, 14, 6.4)
        ImageDraw.Draw(m).polygon([(S(x), S(y)) for x, y in pts], fill=255)
        im = rub(finish(m), rgba(YELLOW), 71, 1.0, 10, -30, 0.08)
        ln = clear(w, h)
        Chalk(ln, 72).path(pts + [pts[0], pts[1]], rgba(YELLOW), 1.6, wob=0.15)
        return Image.alpha_composite(im, chalky(finish(ln), 73, 0.1, 0.1))

    def battery(self, level, charging=False):
        n = 48
        seed = seed_of("bat", level, charging)
        im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        if level > 0:
            m = finish(rough_rect(n, n, (9.5, 18.5, 9.5 + 27 * level, 29.5), 1.5, seed, 0.3))
            im = rub(m, rgba(PINK if level <= 0.2 else MINT), seed + 1, 1.0, 10, 0, 0.1)
        ln = clear(n, n)
        c = Chalk(ln, seed + 2)
        c.box(6, 15, 40, 33, 3, rgba(CHALK), 2.3, over=5, wob=0.3)
        c.path([(43, 20.5), (43, 27.5)], rgba(CHALK), 2.8, wob=0.1)
        if charging:
            bolt = [(26, 9), (16, 26), (23, 26), (19, 39), (32, 20), (25, 20), (29, 9)]
            d = ImageDraw.Draw(ln)
            pts = [(S(x), S(y)) for x, y in bolt]
            d.line(pts + pts[:2], fill=rgba(WOOD_D), width=int(S(3.5)), joint="curve")
            d.polygon(pts, fill=rgba(YELLOW))
        return Image.alpha_composite(im, chalky(finish(ln), seed + 3, 0.18, 0.15))

    def preview_frame(self):
        w, h = 250, 360
        im = clear(w, h)
        Chalk(im, 81).box(3, 3, w - 4, h - 4, 6, rgba(CHALK, 200), 2.6, over=16)
        return lean(chalky(finish(im), 82, 0.25, 0.25))

    def key(self, focused):
        """MainUI writes key labels in white: dark slate keys, the focused one ringed in yellow."""
        w, h = 52, 40
        seed = seed_of("key", focused)
        m = finish(rough_rect(w, h, (3, 3, w - 3, h - 4), 6, seed, 0.3))
        im = paint(rgba(BOARD_D if not focused else (66, 98, 80)), m)
        ring = clear(w, h)
        Chalk(ring, seed + 1).box(3, 3, w - 3, h - 4, 6, rgba(YELLOW if focused else CHALK, 255 if focused else 110),
                                  3.0 if focused else 1.6, over=6, wob=0.3)
        return Image.alpha_composite(im, chalky(finish(ring), seed + 2, 0.2, 0.2))

    def input_box(self):
        w, h = 560, 60
        m = finish(rough_rect(w, h, (4, 5, w - 4, h - 6), 8, 91))
        return lean(rub(m, rgba(CHALK), 92, 1.0, 40, 0, 0.01, 0.88))

    # ---- system and app icons -------------------------------------------------------------
    _order = None

    def icon_color(self, sid):
        if Theme._order is None:
            Theme._order = {s: i for i, s in enumerate(system_ids())}
        return ICON_COLORS[Theme._order.get(sid, len(sid)) % len(ICON_COLORS)]

    def _layers(self, draw, cx, cy, k):
        """(lines, soft) SS layers of a GLYPHS drawing [k] times its size around (cx, cy)."""
        out = []
        for c, soft in (((255, 255, 255, 255), (0, 0, 0, 0)), ((0, 0, 0, 0), (255, 255, 255, 255))):
            im = clear(120, 130)
            p = Pen(ImageDraw.Draw(im), cx / k, cy / k, c, SS * k, w=3.9)
            p.soft_c = soft
            draw(p)
            out.append(im.getchannel("A"))
        return out

    def icon_picture(self, sid, selected, cy):
        draw = GLYPHS.get(sid) or GLYPHS["fallback"]
        x0, y0, x1, y1 = (v / SS for v in self._layers(draw, 60, cy, 1.0)[0].getbbox())
        k = min(1.1, 54 / max(60 - x0, x1 - 60), (cy - 6) / (cy - y0), (124 - cy) / (y1 - cy))
        la, soft = self._layers(draw, 60, cy, k)
        seed = seed_of("icon", sid)
        la = wobble(la, S(0.6), S(26), seed)
        soft = wobble(soft, S(0.6), S(26), seed)
        body = enclosed(la, 120, 130)
        soft = soft.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
        col = self.icon_color(sid)
        if selected and col == YELLOW:
            col = CHALK
        if sid == "android":   # the one solid silhouette: coloured in, outline and eyes kept
            core = la.filter(ImageFilter.MinFilter(2 * round(3.5 * SS) + 1))
            la = ImageChops.subtract(la, core)
            soft = ImageChops.lighter(soft, core)
        body = finish(ImageChops.subtract(body, soft))
        out = rub(body, rgba(col), seed + 1, 1.0, 12, -32, 0.04, 0.84)
        if soft.getbbox():
            out = Image.alpha_composite(out, rub(finish(soft), rgba(CHALK if selected else DETAIL[self.icon_color(sid)]),
                                                 seed + 2, 1.0, 12, -32, 0.04, 0.88))
        la1 = finish(la)
        if not selected:  # the board shows in a hairline round the white lines, so details read on the colour
            gap = la1.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.4))
            out.putalpha(ImageChops.subtract(out.getchannel("A"), gap))
        ln = paint(rgba(INKD if selected else CHALK), la1)
        ln = chalky(ln, seed + 3, 0.1 if selected else 0.2, 0.15 if selected else 0.2)
        return Image.alpha_composite(out, ln)

    def system_icon(self, sid, selected):
        # (no name badge: MainUI writes the name under every icon)
        return self.icon_picture(sid, selected, 64)

    def app_icon(self, key):
        n = 96
        col = APP_COLOR.get(key, BLUE)
        seed = seed_of("app", key)
        m = finish(rough_disc(n, n, n / 2, n / 2, 40, seed, 0.03))
        im = rub(m, rgba(col), seed + 1, 1.0, 14, -30, 0.03, 0.8)
        ln = clear(n, n)
        if key == "retroarch":
            invader(ImageDraw.Draw(ln), n / 2, n / 2, n * 0.25, rgba(INKD))
        else:
            APPS[key](ImageDraw.Draw(ln), n / 2, n / 2, n * 0.25, rgba(INKD), n * 0.06)
        ln = wobble(ln, S(0.6), S(24), seed + 2)
        ring = clear(n, n)
        Chalk(ring, seed + 3).loop(n / 2, n / 2, 40.5, 40.5, rgba(CHALK, 230), 2.4, over=0.35)
        return Image.alpha_composite(im, chalky(finish(Image.alpha_composite(ring, ln)), seed + 4, 0.12, 0.12))

    # ---- sound and config -----------------------------------------------------------------
    def sound(self, path):
        """A chalk tap: a short dry knock with a little grit."""
        rate = 22050
        rnd = random.Random(9)
        frames = bytearray()
        lp = 0.0
        for i in range(int(rate * 0.032)):
            t = i / rate
            lp += 0.5 * (rnd.uniform(-1, 1) - lp)
            s = 0.55 * math.sin(2 * math.pi * 520 * t) * math.exp(-t * 120) + 0.45 * lp * math.exp(-t * 220)
            frames += struct.pack("<h", int(15000 * min(1.0, t / 0.0015) * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc(INKD)  # on the rubbed-in chalk of focused tiles
        cfg["currentpage"] = {"color": hexc(YELLOW)}
        return cfg
