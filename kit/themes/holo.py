"""Holo: Y2K holographic. Pearl surfaces washed with shifting lilac, sky, mint and peach foil,
glossy jelly tiles and buttons, chrome swooshes, floating bubbles and sparkles; dark ink keeps
every label readable."""
import math
import random
import struct
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import (APPS, BADGES, GLYPHS, SS, TILES, Pen, S, Style, canvas, circle, finish, g_folder, hexc, line, poly,
                       rgba, rrect)

INK = (46, 36, 98)          # text and line art
INK_SOFT = (92, 80, 150)    # unfocused labels
WHITE = (255, 255, 255)
PEARL = (250, 248, 255)
LILAC = (186, 160, 255)
VIOLET = (120, 92, 220)
SHADOW = (110, 90, 180)

# foil colours, cycling: lilac, sky, mint, lemon, peach, pink
FOIL = [(206, 190, 255), (178, 218, 255), (172, 244, 222), (255, 242, 190), (255, 210, 190), (255, 196, 230)]
FOIL_STRONG = [(176, 146, 255), (128, 192, 255), (112, 228, 196), (255, 226, 136), (255, 172, 150), (255, 150, 210)]
FOIL_DEEP = [(132, 96, 236), (64, 140, 230), (30, 168, 140), (214, 150, 20), (232, 104, 92), (220, 76, 160)]
# each menu glyph gets its own jelly bubble
BUBBLE = {"recent": (88, 156, 240), "favorite": (248, 132, 104), "game": (48, 184, 152), "emulators": (146, 106, 232),
          "retroarch": (236, 98, 166), "app": (236, 170, 40), "setting": (124, 134, 196)}
APP_BUBBLES = [(146, 106, 232), (88, 156, 240), (48, 184, 152), (236, 170, 40), (248, 132, 104), (236, 98, 166),
               (124, 134, 196)]


# ---- image helpers -----------------------------------------------------------------------

def place(dst, src, x, y):
    layer = Image.new("RGBA", dst.size, (0, 0, 0, 0))
    layer.paste(src, (int(round(x)), int(round(y))))
    dst.alpha_composite(layer)


def place_center(dst, src, cx, cy):
    place(dst, src, cx - src.width / 2, cy - src.height / 2)


def over(*layers):
    out = layers[0]
    for lay in layers[1:]:
        out = Image.alpha_composite(out, lay)
    return out


def with_mask(fill, mask):
    out = fill.copy()
    out.putalpha(ImageChops.multiply(fill.getchannel("A"), mask))
    return out


def fade(im, k):
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * k)))
    return out


def solid(size, c, mask, k=1.0):
    out = Image.new("RGBA", size, rgba(c[:3]))
    a = c[3] / 255 if len(c) > 3 else 1.0
    out.putalpha(mask if a * k == 1.0 else mask.point(lambda v: int(v * a * k)))
    return out


def soft_shadow(shape, color=SHADOW, alpha=60, blur=4, dy=3):
    a = shape.getchannel("A").point(lambda v: v * alpha // 255)
    sh = solid(shape.size, color, a).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", shape.size, rgba(color, 0))
    place(out, sh, 0, dy)
    return out


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def lighter(c, k):
    return mix(c, WHITE, k)


def darker(c, k):
    return mix(c, (0, 0, 0), k)


def rr_mask(w, h, box, r):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([v * SS for v in box], radius=r * SS, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def rr_ring(w, h, box, r, width):
    e = width / 2
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([S(box[0] - e), S(box[1] - e), S(box[2] + e), S(box[3] + e)], radius=S(r + e),
                                        outline=255, width=max(1, int(S(width))))
    return m.resize((w, h), Image.LANCZOS)


def disc_mask(w, h, cx, cy, r):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=255)
    return m.resize((w, h), Image.LANCZOS)


def ring_mask(w, h, cx, cy, r, width):
    m = Image.new("L", (w * SS, h * SS), 0)
    e = width / 2
    ImageDraw.Draw(m).ellipse([S(cx - r - e), S(cy - r - e), S(cx + r + e), S(cy + r + e)], outline=255,
                              width=max(1, int(S(width))))
    return m.resize((w, h), Image.LANCZOS)


def vgrad(w, h, stops, y0=0, y1=None):
    """Vertical RGBA gradient through [(t, colour)] between rows y0 and y1."""
    y1 = h - 1 if y1 is None else y1
    t = np.clip((np.arange(h, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1)
    return _ramp_img(np.repeat(t[:, None], w, axis=1), stops)


def _ramp_img(t, stops):
    ts = np.array([s for s, _ in stops], dtype=np.float32)
    cs = np.array([rgba(c) if len(c) == 3 else c for _, c in stops], dtype=np.float32)
    out = np.stack([np.interp(t, ts, cs[:, k]) for k in range(4)], axis=-1)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def foil(w, h, pal, span=320.0, angle=30.0, warp=0.16, phase=0.0, seed=0.0, x0=0, y0=0):
    """Holographic foil: [pal] cycling along a warped diagonal, a full cycle every [span] px."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x += x0
    y += y0
    a = math.radians(angle)
    t = (x * math.cos(a) + y * math.sin(a)) / span + phase
    t += warp * np.sin(2 * math.pi * (x * 0.55 + y * 0.3) / span + seed)
    t += warp * 0.7 * np.sin(2 * math.pi * (-x * 0.35 + y * 0.8) / (span * 0.8) + seed * 1.7 + 1.1)
    n = len(pal)
    idx = (t % 1.0) * n
    i0 = np.floor(idx).astype(np.int32) % n
    f = idx - np.floor(idx)
    f = f * f * (3 - 2 * f)
    p = np.array(pal, dtype=np.float32)
    c = p[i0] * (1 - f[..., None]) + p[(i0 + 1) % n] * f[..., None]
    out = np.concatenate([c, np.full((h, w, 1), 255, np.float32)], axis=-1)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA")


def edge_fade(w, h, n=5):
    """L mask: 0 on the canvas border, 255 from [n] px in, so a glow fades out instead of being cut."""
    xs = np.clip(np.minimum(np.arange(w), w - 1 - np.arange(w)) / n, 0, 1)
    ys = np.clip(np.minimum(np.arange(h), h - 1 - np.arange(h)) / n, 0, 1)
    return Image.fromarray((np.outer(ys, xs) * 255).astype(np.uint8), "L")


def sparkle(d, cx, cy, r, col, waist=0.16):
    """A four-pointed twinkle on a supersampled ImageDraw."""
    pts = []
    for i in range(16):
        a = math.radians(i * 22.5 - 90)
        k = 1.0 if i % 4 == 0 else (waist if i % 2 == 0 else waist * 1.25)
        if i % 4 == 2:
            k = waist * 0.9
        pts.append((S(cx + r * k * math.cos(a)), S(cy + r * k * math.sin(a))))
    d.polygon(pts, fill=col)


def sparkle_img(n, r, col=WHITE, glow=LILAC):
    im = canvas(n, n)
    sparkle(ImageDraw.Draw(im), n / 2, n / 2, r, rgba(col))
    im = finish(im)
    halo = solid(im.size, glow, im.getchannel("A")).filter(ImageFilter.GaussianBlur(r * 0.22))
    return over(Image.new("RGBA", im.size, rgba(glow, 0)), halo, halo, im)


def silhouette(alpha, grow=2):
    m = alpha.point(lambda v: 255 if v > 70 else 0)
    if grow:
        m = m.filter(ImageFilter.GaussianBlur(grow * 0.75)).point(lambda v: 255 if v > 28 else 0)
    pad = Image.new("L", (m.width + 2, m.height + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    filled = pad.point(lambda v: 0 if v == 128 else 255).crop((1, 1, m.width + 1, m.height + 1))
    return filled.filter(ImageFilter.GaussianBlur(0.7))


def gloss(w, h, box, r, k=1.0):
    """The jelly highlight: a white sheet over the upper part of a rounded box, fading down."""
    x0, y0, x1, y1 = box
    hh = (y1 - y0)
    inset = max(2.0, min(5.0, r * 0.25))
    gb = (x0 + inset, y0 + inset * 0.7, x1 - inset, y0 + min(hh * 0.48, hh - inset))
    m = rr_mask(w, h, gb, max(1, r - inset))
    g = vgrad(w, h, [(0, (255, 255, 255, int(205 * k))), (1, (255, 255, 255, int(18 * k)))], gb[1], gb[3])
    return with_mask(g, m)


def bubble(n_w, n_h, cx, cy, r, col, sheen=1.0):
    """A glossy jelly sphere of colour [col]: bright caustic low, white highlight high, coloured shadow."""
    m = disc_mask(n_w, n_h, cx, cy, r)
    y, x = np.mgrid[0:n_h, 0:n_w].astype(np.float32)
    d = np.sqrt((x - cx) ** 2 + (y - (cy + r * 0.42)) ** 2) / (r * 1.45)
    t = np.clip(d, 0, 1)
    body = _ramp_img(t, [(0, lighter(col, 0.5)), (0.55, col), (1, darker(col, 0.14))])
    body = with_mask(body, m)
    out = Image.new("RGBA", (n_w, n_h), rgba(col, 0))
    out.alpha_composite(soft_shadow(body, darker(col, 0.15), 110, 4, 4))
    out.alpha_composite(body)
    out.alpha_composite(solid((n_w, n_h), darker(col, 0.22), ring_mask(n_w, n_h, cx, cy, r - 0.6, 1.2), 0.7))
    return out


def bubble_gloss(n_w, n_h, cx, cy, r, k=1.0):
    hl = Image.new("L", (n_w * SS, n_h * SS), 0)
    ImageDraw.Draw(hl).ellipse([S(cx - r * 0.66), S(cy - r * 0.9), S(cx + r * 0.66), S(cy - r * 0.04)], fill=255)
    hl = hl.resize((n_w, n_h), Image.LANCZOS)
    g = vgrad(n_w, n_h, [(0, (255, 255, 255, int(215 * k))), (1, (255, 255, 255, int(12 * k)))], cy - r * 0.9, cy - r * 0.04)
    out = with_mask(g, hl)
    dot = Image.new("RGBA", (n_w, n_h), (255, 255, 255, 0))
    ImageDraw.Draw(dot).ellipse([cx + r * 0.42, cy + r * 0.38, cx + r * 0.62, cy + r * 0.56],
                                fill=(255, 255, 255, int(150 * k)))
    return over(out, dot.filter(ImageFilter.GaussianBlur(1.2)))


def android_lines(col, cy, width=3.2):
    """GLYPHS['android'] fills its head and body solid; outline them instead, like every other icon."""
    solid_l, thin = canvas(120, 130), canvas(120, 130)

    class SplitPen(Pen):   # its antennas (pen lines) go on their own layer
        def ln(self, *pts, w=None):
            Pen(ImageDraw.Draw(thin), self.cx, self.cy, col, self.ss, self.w).ln(*pts, w=w)

    pen = SplitPen(ImageDraw.Draw(solid_l), 60, cy, col, SS, w=width)
    GLYPHS["android"](pen)
    b = solid_l.getchannel("A").filter(ImageFilter.GaussianBlur(width * SS / 2.38))
    ring = ImageChops.subtract(b.point(lambda v: 255 if v > 30 else 0), b.point(lambda v: 255 if v > 225 else 0))
    out = Image.new("RGBA", solid_l.size, rgba(col, 0))
    out.paste(Image.new("RGBA", solid_l.size, col), (0, 0), ring)
    d = ImageDraw.Draw(out)
    for ex in (-13, 13):
        d.ellipse([*pen.p(ex - 3.6, -11.6), *pen.p(ex + 3.6, -4.4)], fill=col)
    out.alpha_composite(thin)
    return finish(out)


# ---- the theme -----------------------------------------------------------------------------

class Theme(Style):
    name = "Holo"
    author = "MainUI"
    description = "Y2K holographic: iridescent pearl foil, glossy jelly bubbles and sparkles, with crisp dark ink."

    bg_top = (236, 228, 255)
    bg_bottom = (240, 236, 255)   # light: MainUI's own fallbacks pick dark ink
    accent = (112, 80, 206)       # MainUI writes white on it (fallback tiles, keys)
    accent2 = VIOLET
    highlight = (150, 60, 170)    # current page number
    text = INK
    muted = INK_SOFT
    glyph_n = INK
    glyph_f = INK
    panel = (238, 230, 255)       # toasts; MainUI darkens it by 20% for the pop-up title band
    panel_alpha = 255

    font_file = "Kodchasan-Bold.ttf"
    font_license = "OFL-Kodchasan.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 27, 25, 24, 22, 15, 17
    icon_quant = 64
    sel_icons = True

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc((34, 22, 80))
        return cfg

    # ---- background --------------------------------------------------------------------
    def background(self, w=640, h=480):
        f = foil(w, h, FOIL, span=520, angle=28, warp=0.2, seed=0.6)
        bg = Image.blend(Image.new("RGBA", (w, h), rgba(PEARL)), f, 0.78)
        # pearly light pooling
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        glowm = np.exp(-(((x - 230) / 300) ** 2 + ((y - 170) / 210) ** 2)) * 120
        bg.alpha_composite(solid((w, h), WHITE, Image.fromarray(glowm.astype(np.uint8), "L")))
        # chrome swooshes across the bottom and the top right
        bg.alpha_composite(self._swoosh(w, h, 400, 46, 0.0, 28))
        bg.alpha_composite(self._swoosh(w, h, 446, 30, 1.9, 22, k=0.8))
        bg.alpha_composite(self._swoosh(w, h, 92, 26, 3.4, 16, k=0.55, x_from=300))
        # bubbles
        for cx, cy, r, k in ((592, 150, 62, 1.0), (40, 300, 40, 0.9), (514, 330, 22, 0.9), (150, 100, 14, 0.8),
                             (612, 262, 12, 0.8), (310, 380, 10, 0.8), (88, 216, 9, 0.7), (440, 84, 8, 0.7)):
            bg.alpha_composite(self._soap(w, h, cx, cy, r, k))
        # sparkles, mostly near the edges
        rnd = random.Random(7)
        for cx, cy, r in ((560, 78, 11), (604, 218, 7), (46, 250, 8), (130, 380, 9), (360, 92, 6), (250, 300, 5),
                          (486, 260, 6), (24, 120, 6), (430, 400, 7), (600, 380, 10), (210, 150, 4.5), (520, 190, 4.5)):
            place_center(bg, fade(sparkle_img(int(r * 4) + 6, r), rnd.uniform(0.75, 1.0)), cx, cy)
        dots = canvas(w, h)
        dd = ImageDraw.Draw(dots)
        for _ in range(60):
            circle(dd, rnd.uniform(0, w), rnd.uniform(60, h), rnd.choice((0.7, 0.9, 1.1)),
                   fill=(255, 255, 255, rnd.randint(150, 240)))
        bg.alpha_composite(finish(dots))
        return bg.convert("RGB").convert("RGBA")

    def _swoosh(self, w, h, y0, thick, ph, amp, k=1.0, x_from=-10):
        """A glossy foil ribbon along a sine."""
        top, bot = [], []
        for i in range(0, 85):
            x = x_from + (w + 20 - x_from) * i / 84
            u = (x - x_from) / (w + 20 - x_from)
            yc = y0 + amp * math.sin(u * math.pi * 1.6 + ph)
            if x_from > 0:   # starts mid-screen: tapers in from a point
                th = thick * (0.25 + 0.75 * math.sin(min(1, u * 1.15) * math.pi) ** 0.7)
            else:
                th = thick * (0.55 + 0.45 * math.sin(u * math.pi * 1.2 + ph))
            top.append((x, yc - th / 2))
            bot.append((x, yc + th / 2))
        m = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(m).polygon([(S(x), S(y)) for x, y in top + bot[::-1]], fill=255)
        m = m.resize((w, h), Image.LANCZOS)
        body = with_mask(foil(w, h, FOIL_STRONG, span=360, angle=-20, warp=0.12, seed=ph), m)
        body = fade(body, 0.55 * k)
        edge = canvas(w, h)
        ImageDraw.Draw(edge).line([(S(x), S(y + 1.2)) for x, y in top], fill=(255, 255, 255, 255), width=int(S(1.6)))
        lo = canvas(w, h)
        ImageDraw.Draw(lo).line([(S(x), S(y - 1)) for x, y in bot], fill=(255, 255, 255, 255), width=int(S(1.0)))
        return over(body, solid((w, h), WHITE, finish(edge).getchannel("A"), 0.85 * k),
                    solid((w, h), (150, 120, 230), finish(lo).getchannel("A"), 0.35 * k))

    def _soap(self, w, h, cx, cy, r, k):
        """A floating soap bubble: clear middle, iridescent rim, a white highlight."""
        m = disc_mask(w, h, cx, cy, r)
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        d = np.clip(np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r, 0, 1)
        a = Image.fromarray((np.clip((d - 0.55) / 0.45, 0, 1) ** 2 * 170 * k + 18 * k).astype(np.uint8), "L")
        body = with_mask(foil(w, h, FOIL_STRONG, span=r * 2.2, angle=60, warp=0.1, seed=r), ImageChops.multiply(m, a))
        out = over(body, solid((w, h), WHITE, ring_mask(w, h, cx, cy, r - 0.5, max(0.8, r * 0.03)), 0.7 * k))
        hl = Image.new("L", (w * SS, h * SS), 0)
        hd = ImageDraw.Draw(hl)
        hd.ellipse([S(cx - r * 0.62), S(cy - r * 0.7), S(cx - r * 0.1), S(cy - r * 0.38)], fill=255)
        hl = hl.resize((w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(0.6, r * 0.05)))
        return over(out, solid((w, h), WHITE, hl, 0.85 * k))

    # ---- bars ----------------------------------------------------------------------------
    def _rainbow_line(self, w, h, y, width, alpha=1.0):
        ln = canvas(w, h)
        line(ImageDraw.Draw(ln), [(0, y), (w, y)], (255, 255, 255, 255), width)
        m = finish(ln).getchannel("A")
        col = foil(w, h, FOIL_DEEP, span=w * 0.9, angle=0, warp=0.0)
        return with_mask(col, m.point(lambda v: int(v * alpha)))

    def _bar(self, top):
        im = vgrad(640, 60, [(0, (255, 255, 255, 222)), (1, (250, 246, 255, 196))] if top else
                   [(0, (250, 246, 255, 196)), (1, (255, 255, 255, 224))])
        y = 58.4 if top else 1.6
        im.alpha_composite(self._rainbow_line(640, 60, y, 1.8, 0.85))
        hl = canvas(640, 60)
        y2 = y - 1.8 if top else y + 1.8
        line(ImageDraw.Draw(hl), [(0, y2), (640, y2)], (255, 255, 255, 230), 1.0)
        im.alpha_composite(finish(hl))
        return im

    def header_bar(self):
        return self._bar(True)

    def footer_bar(self):
        return self._bar(False)

    def logo(self):
        w, h = 160, 42
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        im.alpha_composite(bubble(w, h, 19, 21, 13, (150, 116, 236)))
        inner = disc_mask(w, h, 19, 21, 9.5).point(lambda v: v * 150 // 255)
        im.alpha_composite(with_mask(foil(w, h, FOIL_STRONG, span=30, angle=50), inner))
        im.alpha_composite(bubble_gloss(w, h, 19, 21, 13))
        tm = Image.new("L", (w * SS, h * SS), 0)
        td = ImageDraw.Draw(tm)
        f = self.font(26)
        x = 40
        for ch in "HOLO":
            td.text((S(x), S(22.5)), ch, font=f, fill=255, anchor="lm")
            x += td.textlength(ch, font=f) / SS + 1.5
        tm = tm.resize((w, h), Image.LANCZOS)
        chrome = foil(w, h, [(118, 78, 226), (58, 116, 226), (34, 146, 168), (196, 64, 168)], span=130, angle=0, warp=0.05)
        clear = (255, 255, 255, 0)
        shade = vgrad(w, h, [(0, clear), (0.5, clear), (0.52, (30, 20, 70, 60)), (1, (30, 20, 70, 0))], 9, 34)
        text = over(with_mask(chrome, tm), with_mask(shade, tm))
        im.alpha_composite(soft_shadow(text, (90, 70, 170), 90, 1.0, 1.0))
        im.alpha_composite(text)
        place_center(im, sparkle_img(18, 6.5), x - 1, 9)
        return im

    # ---- lists ---------------------------------------------------------------------------
    def _jelly_bar(self, w, h, box, r, strong=True):
        m = rr_mask(w, h, box, r)
        body = with_mask(foil(w, h, FOIL_STRONG if strong else FOIL, span=w * 0.95, angle=8, warp=0.06, phase=0.02), m)
        out = over(soft_shadow(body, SHADOW, 70, 3, 2), body)
        out.alpha_composite(gloss(w, h, box, r, 0.9))
        out.alpha_composite(solid((w, h), WHITE, rr_ring(w, h, box, r, 1.5), 0.9))
        outer = rr_ring(w, h, (box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1), r + 1, 0.9)
        out.alpha_composite(solid((w, h), (120, 90, 200), outer, 0.45))
        return out

    def selection(self, h):
        w = 640
        box = (8, 5, w - 8, h - 6)
        out = self._jelly_bar(w, h, box, min(24, (box[3] - box[1]) / 2))
        place_center(out, sparkle_img(20, 6, WHITE, (150, 110, 240)), w - 16, h / 2 - 1)   # inside the kept end cap
        return out

    def divider(self):
        im = canvas(640, 4)
        line(ImageDraw.Draw(im), [(22, 2), (618, 2)], (255, 255, 255, 255), 1.2)
        m = finish(im).getchannel("A")
        row = np.clip(np.minimum(np.arange(640) - 22, 618 - np.arange(640)) / 60, 0, 1).astype(np.float32)
        fm = Image.fromarray((np.repeat(row[None, :], 4, axis=0) * 255).astype(np.uint8), "L")
        return with_mask(foil(640, 4, FOIL_DEEP, span=600, angle=0, warp=0),
                         ImageChops.multiply(m, fm).point(lambda v: v * 120 // 255))

    # ---- tiles ---------------------------------------------------------------------------
    def _jelly(self, w, h, box, r, focused, shine=0.0):
        """A jelly card: pearl and calm, or washed in strong foil with a halo when focused."""
        m = rr_mask(w, h, box, r)
        if focused:
            f = foil(w, h, FOIL_STRONG, span=(box[3] - box[1]) * 1.25, angle=62, warp=0.14, phase=shine, seed=1.3)
            body = with_mask(f, m)
            spread = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(5))
            halo = with_mask(foil(w, h, FOIL_STRONG, span=(box[3] - box[1]) * 1.25, angle=62, warp=0.14, phase=shine + 0.15),
                             ImageChops.multiply(spread, edge_fade(w, h)))
            out = over(soft_shadow(body, SHADOW, 80, 6, 5), halo, halo, body)
            # a pearly wash where MainUI writes the label, so dark ink reads on any hue
            band = vgrad(w, h, [(0, (255, 255, 255, 0)), (0.55, (255, 255, 255, 0)), (0.72, (255, 255, 255, 96)),
                                (0.86, (255, 255, 255, 60)), (1, (255, 255, 255, 30))], box[1], box[3])
            out.alpha_composite(with_mask(band, m))
        else:
            body = with_mask(vgrad(w, h, [(0, (255, 255, 255, 150)), (0.6, (252, 250, 255, 196)), (1, (248, 244, 255, 214))],
                                   box[1], box[3]), m)
            out = over(soft_shadow(body, SHADOW, 50, 5, 4), body)
            tint = with_mask(foil(w, h, FOIL, span=(box[3] - box[1]) * 1.4, angle=62, warp=0.1, seed=2.0), m)
            out.alpha_composite(fade(tint, 0.35))
        out.alpha_composite(gloss(w, h, box, r, 1.0 if focused else 0.75))
        rim = rr_ring(w, h, box, r, 2.0 if focused else 1.4)
        out.alpha_composite(solid((w, h), WHITE, rim, 1.0 if focused else 0.9))
        edge = foil(w, h, FOIL_DEEP, span=(box[3] - box[1]) * 1.25, angle=62, warp=0.14, phase=shine)
        outer = rr_ring(w, h, (box[0] - 1.2, box[1] - 1.2, box[2] + 1.2, box[3] + 1.2), r + 1.2, 1.0)
        out.alpha_composite(with_mask(edge, outer.point(lambda v: v * (200 if focused else 90) // 255)))
        return out

    def card(self, w, h, focused):
        if w == 155:
            out = self._jelly(w, h, (6, 5, w - 6, h - 7), 22, focused)
        else:
            out = self._jelly(w, h, (6, 5, w - 6, h - 7), min(22, w / 5), focused)
        if focused:
            place_center(out, sparkle_img(24, 8), w - 16, 16)
        return out

    def tile_base(self, focused):
        box = (12, 9, 144, 268)
        im = self._jelly(156, 278, box, 30, focused)
        if focused:
            for cx, cy, r in ((128, 26, 9), (28, 168, 5.5), (122, 250, 6.5)):
                place_center(im, sparkle_img(int(r * 4) + 6, r), cx, cy)
        return im

    def tile_glyph(self, key, focused):
        col = BUBBLE[key]
        r = 47 if focused else 44
        n_w, n_h = 156, 278
        out = Image.new("RGBA", (n_w, n_h), (0, 0, 0, 0))
        if focused:   # an iridescent ring hovering round the bubble
            ring = ring_mask(n_w, n_h, 78, 112, r + 5, 3.0)
            col_r = foil(n_w, n_h, FOIL_DEEP, span=90, angle=40, warp=0.1)
            out.alpha_composite(with_mask(col_r, ring.filter(ImageFilter.GaussianBlur(3))))
            out.alpha_composite(with_mask(foil(n_w, n_h, FOIL_STRONG, span=90, angle=40, warp=0.1), ring))
        out.alpha_composite(bubble(n_w, n_h, 78, 112, r, col))
        g = canvas(n_w, n_h)
        TILES[key](ImageDraw.Draw(g), 78, 113, 25 if focused else 24, rgba(WHITE), 4.8)
        g = finish(g)
        out.alpha_composite(soft_shadow(g, darker(col, 0.4), 210, 1.0, 1.8))
        out.alpha_composite(g)
        out.alpha_composite(bubble_gloss(n_w, n_h, 78, 112, r, 0.85))
        return out

    def home_tile(self, key, focused):
        im = super().home_tile(key, focused)
        return Image.merge("RGBA", [c.point(lambda v: v - v % 4) for c in im.split()])   # smaller PNGs, unseen

    # ---- buttons -------------------------------------------------------------------------
    BUTTONS = {"A": (236, 98, 166), "B": (88, 156, 240), "X": (48, 184, 152), "Y": (236, 170, 40)}

    def button(self, label, primary):
        n = 54
        col = self.BUTTONS.get(label, VIOLET)
        out = bubble(n, n, n / 2, n / 2 - 1, 20, col)
        out.alpha_composite(bubble_gloss(n, n, n / 2, n / 2 - 1, 20, 0.7))
        t = canvas(n, n)
        ImageDraw.Draw(t).text((S(n / 2), S(n / 2 - 1)), label, font=self.font(25), fill=rgba(WHITE), anchor="mm")
        t = finish(t)
        out.alpha_composite(soft_shadow(t, darker(col, 0.5), 255, 0.7, 1.2))
        out.alpha_composite(t)
        return out

    def pill(self, label, w, h=48):
        box = (4, 9, w - 4, h - 9)
        r = (box[3] - box[1]) / 2
        m = rr_mask(w, h, box, r)
        body = with_mask(vgrad(w, h, [(0, (255, 255, 255, 250)), (1, (240, 234, 255, 250))], box[1], box[3]), m)
        out = over(soft_shadow(body, SHADOW, 70, 1.5, 1.5), body)
        out.alpha_composite(with_mask(foil(w, h, FOIL_DEEP, span=w * 1.2, angle=10), rr_ring(w, h, box, r, 1.4)))
        t = canvas(w, h)
        ImageDraw.Draw(t).text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(h * 0.32), fill=rgba(INK), anchor="mm")
        out.alpha_composite(finish(t))
        return out

    def dot(self, active):
        w, h = 26, 16
        if active:
            box = (2.5, 4, 23.5, 12)
            m = rr_mask(w, h, box, 4)
            body = with_mask(foil(w, h, FOIL_DEEP, span=26, angle=0), m)
            out = over(soft_shadow(body, SHADOW, 90, 1.2, 1), body, gloss(w, h, box, 4, 0.8))
            out.alpha_composite(solid((w, h), WHITE, rr_ring(w, h, box, 4, 1.0), 0.9))
            return out
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.alpha_composite(solid((w, h), WHITE, disc_mask(w, h, 13, 8, 4.2)))
        out.alpha_composite(solid((w, h), (120, 96, 210), ring_mask(w, h, 13, 8, 4.2, 1.1), 0.75))
        return out

    def toggle(self, on):
        w, h = 92, 44
        box = (8, 11, w - 8, h - 11)
        r = (box[3] - box[1]) / 2
        m = rr_mask(w, h, box, r)
        if on:
            body = with_mask(foil(w, h, FOIL_STRONG, span=80, angle=10), m)
        else:
            body = with_mask(vgrad(w, h, [(0, (222, 216, 240)), (1, (236, 232, 248))], box[1], box[3]), m)
        out = over(body, gloss(w, h, box, r, 0.6))
        out.alpha_composite(solid((w, h), (120, 96, 210) if on else (170, 160, 210), rr_ring(w, h, box, r, 1.2), 0.8))
        cx = box[2] - r if on else box[0] + r
        knob = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        km = disc_mask(w, h, cx, h / 2, r + 3)
        kb = with_mask(vgrad(w, h, [(0, WHITE), (1, (236, 232, 250))], h / 2 - r - 3, h / 2 + r + 3), km)
        knob.alpha_composite(soft_shadow(kb, SHADOW, 90, 1.6, 1.4))
        knob.alpha_composite(kb)
        knob.alpha_composite(solid((w, h), (150, 130, 220), ring_mask(w, h, cx, h / 2, r + 2.6, 0.9), 0.7))
        out.alpha_composite(knob)
        if on:
            place_center(out, sparkle_img(16, 5.5, (150, 110, 240), WHITE), cx, h / 2)
        return out

    def arrow(self, left, size=24):
        im = canvas(size, size)
        d = ImageDraw.Draw(im)
        xs = (0.62, 0.34) if left else (0.38, 0.66)
        line(d, [(size * xs[0], size * 0.22), (size * xs[1], size * 0.5), (size * xs[0], size * 0.78)], rgba(INK), size * 0.13)
        return finish(im)

    # ---- panels ----------------------------------------------------------------------------
    def panel_image(self, w, h):
        menu = w == 400   # pop-up menus: MainUI puts a square title band right on top
        r = 20
        box = (0, 0, w, h - 4) if menu else (3, 3, w - 3, h - 4)
        m_ss = Image.new("L", (w * SS, h * SS), 0)
        md = ImageDraw.Draw(m_ss)
        md.rounded_rectangle([S(v) for v in box], radius=S(r), fill=255)
        if menu:
            md.rectangle((0, 0, S(w), S(r)), fill=255)
        m = m_ss.resize((w, h), Image.LANCZOS)
        body = with_mask(vgrad(w, h, [(0, (255, 255, 255, 250)), (1, (246, 242, 255, 250))]), m)
        out = over(soft_shadow(body, SHADOW, 70, 4, 3), body)
        # a holographic sheen in the lower corner
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        a = np.clip(1 - np.sqrt(((x - w) / (w * 0.7)) ** 2 + ((y - h) / (h * 0.9)) ** 2), 0, 1) ** 1.5 * 150
        sheen = with_mask(foil(w, h, FOIL, span=w * 0.6, angle=35, warp=0.12), Image.fromarray(a.astype(np.uint8), "L"))
        out.alpha_composite(with_mask(sheen, m))
        rim = foil(w, h, FOIL_DEEP, span=w * 0.8, angle=20, warp=0.08)
        if menu:
            ring = Image.new("L", (w * SS, h * SS), 0)
            rd = ImageDraw.Draw(ring)
            rd.rounded_rectangle([S(v) for v in box], radius=S(r), outline=255, width=int(S(2)))
            rd.rectangle((0, 0, S(w), S(r)), fill=0)
            rd.rectangle((0, 0, S(2), S(r)), fill=255)
            rd.rectangle((S(w - 2), 0, S(w), S(r)), fill=255)
            rd.rectangle((0, 0, S(w), S(2)), fill=255)
            ring = ring.resize((w, h), Image.LANCZOS)
        else:
            ring = rr_ring(w, h, box, r, 2.0)
        out.alpha_composite(with_mask(rim, ring.point(lambda v: v * 210 // 255)))
        return out

    def preview_frame(self):
        w, h = 250, 360
        box = (1, 1, w - 1, h - 1)
        out = solid((w, h), WHITE, rr_mask(w, h, box, 12))
        out.alpha_composite(with_mask(foil(w, h, FOIL_DEEP, span=300, angle=50), rr_ring(w, h, (2, 2, w - 2, h - 2), 11, 2.4)))
        return out

    def key(self, focused):
        """Dark keys (MainUI writes key labels in white), at the letter keys' own size."""
        w, h = 52, 38
        box = (2, 2, w - 2, h - 3)
        m = rr_mask(w, h, box, 10)
        col = (176, 70, 160) if focused else (84, 68, 150)
        body = with_mask(vgrad(w, h, [(0, lighter(col, 0.12)), (1, darker(col, 0.08))], box[1], box[3]), m)
        out = over(soft_shadow(body, SHADOW, 80, 1.4, 1.2), body)
        mid = (box[1] + box[3]) / 2
        out.alpha_composite(with_mask(vgrad(w, h, [(0, (255, 255, 255, 70)), (1, (255, 255, 255, 0))], box[1], mid),
                                      rr_mask(w, h, (box[0] + 2, box[1] + 1.5, box[2] - 2, mid), 8)))
        if focused:   # a ring with thinner sides: wide keys (up to 3.5x) stretch it sideways only
            ring = Image.new("L", (w * SS, h * SS), 0)
            rd = ImageDraw.Draw(ring)
            rd.rounded_rectangle([S(box[0] + 1.0), S(box[1] + 1.0), S(box[2] - 1.0), S(box[3] - 1.0)], radius=S(9), fill=255)
            rd.rounded_rectangle([S(box[0] + 1.5), S(box[1] + 2.4), S(box[2] - 1.5), S(box[3] - 2.4)], radius=S(8), fill=0)
            out.alpha_composite(solid((w, h), WHITE, ring.resize((w, h), Image.LANCZOS)))
        return out

    def input_box(self):
        w, h = 560, 60
        box = (3, 4, w - 3, h - 5)
        m = rr_mask(w, h, box, 20)
        body = solid((w, h), WHITE, m)
        out = over(soft_shadow(body, SHADOW, 60, 2, 1.5), body)
        out.alpha_composite(with_mask(foil(w, h, FOIL_DEEP, span=w, angle=5), rr_ring(w, h, box, 20, 2.0)))
        return out

    # ---- small marks -----------------------------------------------------------------------
    def _holo_body(self, lines, pal=FOIL_STRONG, alpha=170, offset=(3, 3), span=90, angle=50):
        sil = silhouette(lines.getchannel("A"), 2)
        body = with_mask(foil(lines.width, lines.height, pal, span=span, angle=angle, warp=0.1),
                         sil.point(lambda v: v * alpha // 255))
        out = Image.new("RGBA", lines.size, (0, 0, 0, 0))
        place(out, body, *offset)
        out.alpha_composite(lines)
        return out

    def folder_icon(self):
        im = canvas(60, 60)
        g_folder(ImageDraw.Draw(im), 30, 31, 19, rgba(INK), 3.4)
        return self._holo_body(finish(im), alpha=200, offset=(2, 2), span=50)

    def favorite_mark(self):
        w, h = 34, 39
        pts = []
        for i in range(10):
            r = 14.5 if i % 2 == 0 else 6.6
            a = math.radians(-90 + i * 36)
            pts.append((17 + r * math.cos(a), 20.5 + r * math.sin(a)))
        m = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(m).polygon([(S(x), S(y)) for x, y in pts], fill=255)
        m = m.resize((w, h), Image.LANCZOS)
        body = with_mask(foil(w, h, [(255, 150, 210), (255, 196, 120), (255, 236, 140), (150, 200, 255)], span=40, angle=70), m)
        e = canvas(w, h)
        poly(ImageDraw.Draw(e), pts, rgba(INK), 1.5)
        out = over(soft_shadow(body, SHADOW, 90, 1.2, 1), body, finish(e))
        hl = canvas(w, h)
        circle(ImageDraw.Draw(hl), 14, 15, 3, fill=(255, 255, 255, 200))
        return over(out, finish(hl).filter(ImageFilter.GaussianBlur(0.8)))

    def battery(self, level, charging=False):
        im = canvas(48, 48)
        d = ImageDraw.Draw(im)
        rrect(d, (5, 15, 40, 33), 6, rgba(INK), 2.2)
        rrect(d, (40.5, 20.5, 44, 27.5), 1.6, fill=rgba(INK))
        out = finish(im)
        if level > 0:
            box = (8.5, 18.5, 8.5 + 28 * level, 29.5)
            m = rr_mask(48, 48, box, 3.5)
            if level <= 0.2:
                fill = solid((48, 48), (236, 70, 110), m)
            else:
                fill = with_mask(foil(48, 48, [(112, 228, 196), (128, 192, 255), (176, 146, 255)], span=60, angle=0), m)
            out.alpha_composite(fill)
            out.alpha_composite(with_mask(vgrad(48, 48, [(0, (255, 255, 255, 150)), (1, (255, 255, 255, 0))], 18.5, 24), m))
        if charging:
            b = canvas(48, 48)
            pts = [(25, 10), (16, 26), (23, 26), (20, 38), (31, 21), (24, 21)]
            poly(ImageDraw.Draw(b), pts, rgba(WHITE), 3.2)
            poly(ImageDraw.Draw(b), pts, fill=(236, 170, 40, 255))
            out.alpha_composite(finish(b))
        return out

    # ---- system and app icons ---------------------------------------------------------------
    def _lines(self, sid, col, soft, cy):
        if sid == "android":
            return android_lines(col, cy)
        im = canvas(120, 130)
        pen = Pen(ImageDraw.Draw(im), 60, cy, col, SS, w=3.2)
        pen.soft_c = soft
        (GLYPHS.get(sid) or GLYPHS["fallback"])(pen)
        return finish(im)

    def icon_picture(self, sid, selected, cy):
        if not selected:
            lines = self._lines(sid, rgba(INK), (150, 120, 240, 110), cy)
            return self._holo_body(lines, alpha=150, span=100)
        # on the foil of a focused cell: a white pearl sticker under the ink
        lines = self._lines(sid, rgba(INK), (110, 80, 220, 120), cy)
        sil = silhouette(lines.getchannel("A"), 3)
        body = solid(lines.size, WHITE, sil.point(lambda v: v * 235 // 255))
        out = Image.new("RGBA", lines.size, (255, 255, 255, 0))
        out.alpha_composite(soft_shadow(body, SHADOW, 90, 2, 2))
        out.alpha_composite(body)
        out.alpha_composite(lines)
        return out

    def system_icon(self, sid, selected):
        label = {"segacd": "SCD", "xbox": "XB"}.get(sid, BADGES.get(sid, sid[:7].upper()))
        out = self.icon_picture(sid, selected, 52 if label else 62)
        if label:
            out = Image.alpha_composite(out, self.badge(label, selected))
        return out

    def badge(self, label, selected):
        f = self.font(13)
        probe = ImageDraw.Draw(canvas(1, 1))
        tw = probe.textlength(label, font=f) / SS
        bw = min(116, tw + 18)
        x0 = (120 - bw) / 2
        box = (x0, 105, x0 + bw, 126)
        m = rr_mask(120, 130, box, 10.5)
        if selected:
            out = solid((120, 130), INK, m)
            tc = WHITE
        else:
            out = with_mask(foil(120, 130, FOIL_STRONG, span=100, angle=0), m)
            out.alpha_composite(solid((120, 130), WHITE, m, 0.45))
            out.alpha_composite(solid((120, 130), (120, 96, 210), rr_ring(120, 130, box, 10.5, 1.0), 0.8))
            tc = INK
        t = canvas(120, 130)
        ImageDraw.Draw(t).text((S(60), S(116)), label, font=f, fill=rgba(tc), anchor="mm")
        out.alpha_composite(finish(t))
        return out

    def app_icon(self, key):
        n = 96
        col = APP_BUBBLES[list(APPS).index(key) % len(APP_BUBBLES)]
        box = (8, 7, n - 8, n - 9)
        m = rr_mask(n, n, box, 24)
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        t = np.clip(np.sqrt((x - n / 2) ** 2 + (y - n * 0.78) ** 2) / (n * 0.75), 0, 1)
        body = with_mask(_ramp_img(t, [(0, lighter(col, 0.5)), (0.55, col), (1, darker(col, 0.12))]), m)
        out = over(soft_shadow(body, darker(col, 0.15), 110, 3, 3), body)
        out.alpha_composite(solid((n, n), darker(col, 0.22), rr_ring(n, n, box, 24, 1.2), 0.7))
        g = canvas(n, n)
        APPS[key](ImageDraw.Draw(g), n / 2, n / 2 + 1, n * 0.24, rgba(WHITE), n * 0.058)
        g = finish(g)
        out.alpha_composite(soft_shadow(g, darker(col, 0.4), 200, 1.0, 1.6))
        out.alpha_composite(g)
        out.alpha_composite(gloss(n, n, box, 24, 0.85))
        return out

    # ---- sound ------------------------------------------------------------------------------
    def sound(self, path):
        """A bubbly blip: a sine chirping upwards with a faint glassy partial."""
        rate = 22050
        frames = bytearray()
        ph = 0.0
        n = int(rate * 0.06)
        for i in range(n):
            t = i / rate
            f = 900 + 1100 * (t / 0.06) ** 0.6
            ph += 2 * math.pi * f / rate
            env = math.exp(-t * 60) * min(1.0, t / 0.002)
            s = 0.8 * math.sin(ph) + 0.2 * math.sin(2 * math.pi * 3150 * t) * math.exp(-t * 120)
            frames += struct.pack("<h", int(7600 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))
