"""Dune: a warm light theme, the desert at golden hour. Layered dunes with sunlit and shaded faces
under a large low sun, wind-ripple dividers, arch-shaped tiles like adobe doorways, a sun-baked
clay disc of its own colour for every menu glyph, and deep indigo ink."""
import math
import random
import struct
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import (APPS, BADGES, GLYPHS, SS, TILES, Pen, S, Style, canvas, circle, finish, g_folder, hexc,
                       line, poly, rgba, rrect)

INK = (44, 38, 86)           # text and line art: deep indigo
INDIGO = (64, 58, 124)
TEAL = (34, 122, 128)
MUTED = (124, 84, 72)        # unfocused labels, on cream
CREAM = (255, 247, 234)
SAND = (240, 214, 174)
CLAY = (206, 146, 108)       # outlines of the quiet tiles
TERRA = (204, 96, 60)
TERRA_DEEP = (168, 64, 42)
GOLD = (234, 168, 58)
SHADE = (128, 66, 46)        # shadows
SUNLIT = (255, 216, 150)     # the glow around focused things

# each main menu glyph gets its own sun-baked disc
DISC = {"recent": (36, 136, 140), "favorite": (222, 154, 40), "game": (176, 62, 50), "emulators": (70, 66, 142),
        "retroarch": (170, 82, 112), "app": (108, 138, 76), "setting": (132, 104, 88)}
# the focused tile: sunlit at the top, deep terracotta where MainUI writes the cream label
TERRA_FILL = [(0.0, (246, 168, 94)), (0.42, (224, 116, 68)), (0.7, (194, 82, 54)), (1.0, (172, 68, 46))]
APP_DISCS = [(36, 136, 140), (204, 96, 60), (70, 66, 142), (222, 154, 40), (170, 82, 112), (108, 138, 76),
             (132, 104, 88)]


# ---- image helpers -----------------------------------------------------------------------

def place(dst, src, x, y):
    """alpha_composite [src] at (x, y), which may be partly outside [dst]."""
    layer = Image.new("RGBA", dst.size, (0, 0, 0, 0))
    layer.paste(src, (int(round(x)), int(round(y))))
    dst.alpha_composite(layer)


def place_center(dst, src, cx, cy):
    place(dst, src, cx - src.width / 2, cy - src.height / 2)


def _luts(stops):
    ts = [t for t, _ in stops]
    cs = [rgba(c) if len(c) == 3 else tuple(c) for _, c in stops]
    luts = [[], [], [], []]
    for v in range(256):
        t = v / 255
        k = next((i for i in range(1, len(ts)) if t <= ts[i]), len(ts) - 1)
        u = 0.0 if ts[k] == ts[k - 1] else min(1.0, max(0.0, (t - ts[k - 1]) / (ts[k] - ts[k - 1])))
        for ch in range(4):
            luts[ch].append(int(cs[k - 1][ch] + (cs[k][ch] - cs[k - 1][ch]) * u + 0.5))
    return luts


def colorize(mask, stops):
    return Image.merge("RGBA", [mask.point(lut) for lut in _luts(stops)])


def vgrad(w, h, stops, y0=0, y1=None):
    """Vertical RGBA gradient through [stops] between rows y0 and y1."""
    y1 = h - 1 if y1 is None else y1
    col = Image.new("L", (1, h))
    col.putdata([int(255 * min(1, max(0, (y - y0) / max(1, y1 - y0)))) for y in range(h)])
    return colorize(col.resize((w, h), Image.NEAREST), stops)


def hgrad(w, h, stops):
    row = Image.new("L", (w, 1))
    row.putdata([int(255 * x / max(1, w - 1)) for x in range(w)])
    return colorize(row.resize((w, h), Image.NEAREST), stops)


_RADIAL = Image.radial_gradient("L")   # 1.414 x the distance from (128, 128)


def rgrad(w, h, cx, cy, r, stops):
    """Radial RGBA gradient; stops = [(t, colour)] with t in 0..1 of [r]."""
    d = max(2, int(round(2 * r)))
    m = Image.new("L", (w, h), 255)
    m.paste(_RADIAL.resize((d, d), Image.BILINEAR), (int(round(cx - d / 2)), int(round(cy - d / 2))))
    m = m.point(lambda v: min(255, int(v * 255 / 181.02 + 0.5)))
    return colorize(m, stops)


def with_mask(fill, mask):
    out = fill.copy()
    out.putalpha(ImageChops.multiply(fill.getchannel("A"), mask))
    return out


def fade(im, k):
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * k)))
    return out


def solid(size, c, mask):
    out = Image.new("RGBA", size, rgba(c[:3]))
    out.putalpha(mask if len(c) == 3 else mask.point(lambda v: v * c[3] // 255))
    return out


def soft_shadow(shape, color=SHADE, alpha=60, blur=4, dy=3):
    a = shape.getchannel("A").point(lambda v: v * alpha // 255)
    sh = solid(shape.size, color, a).filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", shape.size, (0, 0, 0, 0))
    place(out, sh, 0, dy)
    return out


def over(*layers):
    out = layers[0]
    for lay in layers[1:]:
        out = Image.alpha_composite(out, lay)
    return out


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def lighter(c, k):
    return mix(c, (255, 255, 255), k)


def darker(c, k):
    return mix(c, (0, 0, 0), k)


def _arch_ss(w, h, box, rt, rb):
    """Supersampled L mask of an arch: top corners of radius rt, bottom corners rb."""
    x0, y0, x1, y1 = [v * SS for v in box]
    rt = min(rt, (box[2] - box[0]) / 2) * SS
    rb = min(rb, (box[2] - box[0]) / 2) * SS
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([x0, y0, x1, y1], radius=rb, fill=255)
    top = Image.new("L", m.size, 0)
    ImageDraw.Draw(top).rounded_rectangle([x0, y0, x1, y1], radius=rt, fill=255)
    mid = int((y0 + y1) / 2)
    m.paste(top.crop((0, 0, m.width, mid)), (0, 0))
    return m


def arch_mask(w, h, box, rt, rb):
    return _arch_ss(w, h, box, rt, rb).resize((w, h), Image.LANCZOS)


def arch_ring(w, h, box, rt, rb, width):
    """An outline [width] wide centred on the arch's edge (L, 1x)."""
    e = width / 2
    outer = _arch_ss(w, h, (box[0] - e, box[1] - e, box[2] + e, box[3] + e), rt + e, rb + e)
    inner = _arch_ss(w, h, (box[0] + e, box[1] + e, box[2] - e, box[3] - e), max(0, rt - e), max(0, rb - e))
    return ImageChops.subtract(outer, inner).resize((w, h), Image.LANCZOS)


def edge_fade(w, h, n=5):
    """L mask: 0 on the canvas border, 255 from [n] px in, so a glow fades out instead of being cut."""
    xs = np.clip(np.minimum(np.arange(w), w - 1 - np.arange(w)) / n, 0, 1)
    ys = np.clip(np.minimum(np.arange(h), h - 1 - np.arange(h)) / n, 0, 1)
    return Image.fromarray((np.outer(ys, xs) * 255).astype(np.uint8), "L")


def silhouette(alpha, grow=2):
    """[alpha]'s shape with its holes filled, as L (a body behind line art)."""
    m = alpha.point(lambda v: 255 if v > 70 else 0)
    if grow:
        m = m.filter(ImageFilter.GaussianBlur(grow * 0.75)).point(lambda v: 255 if v > 28 else 0)
    pad = Image.new("L", (m.width + 2, m.height + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    filled = pad.point(lambda v: 0 if v == 128 else 255).crop((1, 1, m.width + 1, m.height + 1))
    return filled.filter(ImageFilter.GaussianBlur(0.7))


def grain(w, h, amount, seed):
    rnd = random.Random(seed)
    m = Image.new("L", (w, h))
    m.putdata([rnd.randint(0, 255) for _ in range(w * h)])
    return m.point(lambda v: v * amount // 255)


def sun_mark(n, cx, cy, r, sun=(255, 206, 110), dune=TERRA, edge=None):
    """The emblem: a sun half sunk behind a dune (n x n layer)."""
    im = canvas(n, n)
    d = ImageDraw.Draw(im)
    circle(d, cx, cy, r, fill=rgba(sun))
    pts = [(cx - r * 1.3, cy + r * 1.2), (cx - r * 1.3, cy + r * 0.42)]
    for i in range(21):
        t = i / 20
        x = cx - r * 1.3 + t * r * 2.6
        y = cy + r * 0.42 - math.sin(t * math.pi) ** 1.6 * r * 0.34 + t * r * 0.1
        pts.append((x, y))
    pts.append((cx + r * 1.3, cy + r * 1.2))
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=255)
    dm = Image.new("L", im.size, 0)
    ImageDraw.Draw(dm).polygon([(S(x), S(y)) for x, y in pts], fill=255)
    im.paste(Image.new("RGBA", im.size, rgba(dune)), (0, 0), ImageChops.multiply(m, dm))
    if edge:
        circle(d, cx, cy, r, edge, 1.2)
    return finish(im)


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


# ---- dunes ---------------------------------------------------------------------------------

def ridge_fn(base, bumps):
    """y(x) of a dune line: base minus the tallest of its asymmetric bumps (c, height, wl, wr)."""
    def f(x):
        best = 0.0
        for c, a, wl, wr in bumps:
            k = (x - c) / (wl if x < c else wr)
            best = max(best, a * math.exp(-k * k))
        return base - best
    return f


def dune_layer(w, h, base, bumps, lit, shade, ripples=0, seed=0, crest=0.9):
    """One row of dunes: lit windward slopes, shaded slip faces cut by curving brinks, a light
    rim along the crest and wind ripples."""
    y = ridge_fn(base, bumps)
    xs = [x * 2 for x in range(w // 2 + 2)]
    outline = [(x, y(x)) for x in xs]
    m_ss = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m_ss).polygon([(S(x), S(yy)) for x, yy in outline + [(w + 2, h + 2), (-2, h + 2)]], fill=255)
    mask = m_ss.resize((w, h), Image.LANCZOS)
    body = with_mask(vgrad(w, h, [(0, lighter(lit, 0.18)), (0.35, lit), (1, mix(lit, shade, 0.35))],
                           int(base - max(b[1] for b in bumps)), min(h, int(base + 90))), mask)
    # slip faces
    sh_ss = Image.new("L", m_ss.size, 0)
    sd = ImageDraw.Draw(sh_ss)
    for c, a, wl, wr in bumps:
        top = base - a
        xl = c
        while xl > c - 3.2 * wl:
            mine = a * math.exp(-((xl - c) / wl) ** 2)
            if mine < 1.0 or base - mine > y(xl) + 0.5:
                break
            xl -= 2
        pts = [(x, y(x)) for x in range(int(xl), int(c) + 1, 2)]
        # a crescent: the brink sweeps down across the windward slope, the slip face's foot curves back
        dep, span = a * 2.0, a * 1.6 * crest
        brink = [(c + span * t ** 1.35, top + dep * t) for t in (i / 24 for i in range(25))]
        bx, by = brink[-1]
        y0 = y(xl)
        foot = [(bx + (xl - bx) * t, by + (y0 - by) * t ** 1.6 + a * 0.25 * math.sin(math.pi * t))
                for t in (i / 24 for i in range(1, 24))]
        sd.polygon([(S(px), S(py)) for px, py in pts + brink + foot], fill=255)
    shadow = ImageChops.multiply(sh_ss.resize((w, h), Image.LANCZOS), mask)
    sh_fill = vgrad(w, h, [(0, shade), (1, mix(shade, lit, 0.25))], int(base - 60), h)
    out = Image.alpha_composite(body, with_mask(sh_fill, shadow))
    # wind ripples, fainter in the shade
    if ripples:
        rnd = random.Random(seed)
        rd_dark, rd_lite = canvas(w, h), canvas(w, h)
        dd, dl = ImageDraw.Draw(rd_dark), ImageDraw.Draw(rd_lite)
        bottom = base + 70
        for k in range(1, ripples + 1):
            u = (k / (ripples + 1)) ** 0.85
            ph, ph2 = rnd.uniform(0, 6.3), rnd.uniform(0, 6.3)
            pts = []
            for x in range(-4, w + 6, 3):
                yy = y(x) + (bottom - y(x)) * u + 1.8 * math.sin(x / 19 + ph) + 0.9 * math.sin(x / 7.1 + ph2)
                pts.append((x, yy))
            dd.line([(S(px), S(py)) for px, py in pts], fill=(255, 255, 255, 255), width=int(S(1.0)))
            dl.line([(S(px), S(py + 1.3)) for px, py in pts], fill=(255, 255, 255, 255), width=int(S(0.9)))
        inner = mask.filter(ImageFilter.MinFilter(5))
        calm = ImageChops.invert(shadow.point(lambda v: v // 2))
        for lay, col, a in ((rd_dark, darker(shade, 0.08), 70), (rd_lite, lighter(lit, 0.6), 86)):
            m = ImageChops.multiply(ImageChops.multiply(finish(lay).getchannel("A"), inner), calm)
            out = Image.alpha_composite(out, solid((w, h), col, m.point(lambda v: v * a // 255)))
    # a lit rim along the crest
    rim = canvas(w, h)
    ImageDraw.Draw(rim).line([(S(x), S(yy + 0.6)) for x, yy in outline], fill=(255, 255, 255, 255), width=int(S(1.3)))
    rim_m = ImageChops.multiply(finish(rim).getchannel("A"), ImageChops.invert(shadow))
    out = Image.alpha_composite(out, solid((w, h), (255, 240, 214), rim_m.point(lambda v: v * 170 // 255)))
    return out


# ---- the theme -----------------------------------------------------------------------------

class Theme(Style):
    name = "Dune"
    author = "MainUI"
    description = "The desert at golden hour: layered dunes under a low sun, adobe-arch tiles and clay discs in indigo ink."

    bg_top = (238, 196, 180)
    bg_bottom = (250, 230, 200)   # light: MainUI's own fallbacks pick dark ink
    accent = TERRA_DEEP           # MainUI writes white on it (fallback tiles, keys)
    accent2 = INDIGO
    highlight = TERRA_DEEP        # current page number
    text = INK
    muted = MUTED
    glyph_n = INK
    glyph_f = CREAM
    panel = (252, 218, 174)       # toasts; MainUI darkens it by 20% for the pop-up title band
    panel_alpha = 255

    font_file = "Philosopher-Bold.ttf"
    font_license = "OFL-Philosopher.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 28, 26, 24, 22, 16, 18
    icon_quant = 64
    sel_icons = True

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc(CREAM)   # on the terracotta of focused tiles and cells
        return cfg

    # ---- background --------------------------------------------------------------------
    def background(self, w=640, h=480):
        bg = vgrad(w, h, [(0.0, (214, 156, 166)), (0.2, (228, 172, 168)), (0.42, (242, 196, 166)),
                          (0.6, (250, 214, 170)), (1.0, (250, 224, 186))])
        sx, sy, sr = 430, 238, 104
        bg.alpha_composite(rgrad(w, h, sx, sy, 320, [(0, (255, 214, 150, 200)), (0.34, (255, 200, 136, 110)),
                                                     (1, (255, 190, 128, 0))]))
        # the sun: a pale core, a warm rim and a thin bright edge
        sun = rgrad(w, h, sx, sy, sr, [(0, (255, 251, 236, 255)), (0.6, (255, 242, 204, 255)), (1, (255, 224, 150, 255))])
        sm = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(sm).ellipse([S(sx - sr), S(sy - sr), S(sx + sr), S(sy + sr)], fill=255)
        sm = sm.resize((w, h), Image.LANCZOS)
        rim = sm.filter(ImageFilter.GaussianBlur(9)).point(lambda v: v * 220 // 255)
        bg.alpha_composite(solid((w, h), (255, 222, 160), rim))
        bg.alpha_composite(with_mask(sun, sm))
        # soft golden-hour streaks, lighter than the sky
        cl = Image.new("RGBA", (w, h), (255, 238, 220, 0))
        cd = ImageDraw.Draw(cl)
        for box, col in (((20, 132, 280, 140), (255, 236, 220, 120)), ((96, 152, 236, 157), (255, 232, 214, 90)),
                         ((360, 112, 650, 119), (255, 238, 222, 110)), ((300, 262, 560, 268), (255, 238, 208, 90))):
            cd.ellipse(box, fill=col)
        bg.alpha_composite(cl.filter(ImageFilter.GaussianBlur(3)))
        # a few birds far off
        bd = canvas(w, h)
        dd = ImageDraw.Draw(bd)
        for x, y, s in ((536, 78, 4.6), (551, 70, 3.8), (563, 82, 3.2), (226, 74, 3.4), (238, 80, 2.8)):
            line(dd, [(x - s, y - s * 0.4), (x - s * 0.45, y - s * 0.55), (x, y)], (120, 72, 90, 170), 1.0)
            line(dd, [(x, y), (x + s * 0.45, y - s * 0.55), (x + s, y - s * 0.4)], (120, 72, 90, 170), 1.0)
        bg.alpha_composite(finish(bd))

        layers = [
            (300, [(22, 26, 56, 120), (176, 17, 46, 110), (338, 30, 56, 130), (508, 21, 48, 110), (640, 27, 56, 100)],
             (226, 166, 156), (204, 140, 138), 0),
            (356, [(84, 42, 58, 170), (292, 26, 50, 150), (476, 40, 56, 160), (700, 34, 50, 120)],
             (236, 172, 118), (212, 134, 98), 4),
            (424, [(-40, 70, 60, 230), (318, 40, 60, 210), (598, 62, 56, 190)],
             (244, 204, 152), (226, 170, 126), 6),
            (492, [(186, 52, 70, 250), (520, 34, 60, 210)],
             (249, 222, 180), (236, 194, 152), 3),
        ]
        for i, (base, bumps, lit, shade, rip) in enumerate(layers):
            if i:   # haze over what lies behind: farther rows paler
                bg.alpha_composite(vgrad(w, h, [(0, (255, 236, 214, 0)), (1, (255, 236, 214, 70))], base - 90, base))
            bg.alpha_composite(dune_layer(w, h, base, bumps, lit, shade, ripples=rip, seed=i * 7 + 3))
        return bg.convert("RGB").convert("RGBA")

    # ---- bars ----------------------------------------------------------------------------
    def _bar(self, top):
        im = vgrad(640, 60, [(0, (253, 244, 228, 236)), (1, (252, 238, 218, 214))] if top else
                   [(0, (252, 238, 218, 214)), (1, (253, 244, 228, 238))])
        d = canvas(640, 60)
        dd = ImageDraw.Draw(d)
        y = 57.8 if top else 2.2
        y2 = 54.6 if top else 5.4
        line(dd, [(0, y), (640, y)], rgba(TERRA, 235), 1.6)
        line(dd, [(0, y2), (640, y2)], rgba(GOLD, 130), 0.8)
        im.alpha_composite(finish(d))
        return im

    def header_bar(self):
        return self._bar(True)

    def footer_bar(self):
        return self._bar(False)

    def logo(self):
        w, h = 160, 42
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        mark = sun_mark(40, 20, 20, 14.5, sun=(250, 190, 96), dune=TERRA)
        place(im, soft_shadow(mark, alpha=50, blur=1.5, dy=1), -2, 1)
        place(im, mark, -2, 1)
        t = canvas(w, h)
        td = ImageDraw.Draw(t)
        f = self.font(24)
        x = 42
        for ch in "DUNE":
            td.text((S(x), S(22.5)), ch, font=f, fill=rgba(INK), anchor="lm")
            x += td.textlength(ch, font=f) / SS + 3.2
        im.alpha_composite(finish(t))
        return im

    # ---- lists ---------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        r = min(22, (h - 10) / 2)
        box = (7, 4, w - 7, h - 6)
        m = Image.new("L", (w * SS, h * SS), 0)
        ImageDraw.Draw(m).rounded_rectangle([S(v) for v in box], radius=S(r), fill=255)
        m = m.resize((w, h), Image.LANCZOS)
        body = with_mask(hgrad(w, h, [(0, (250, 206, 142)), (0.55, (246, 186, 128)), (1, (240, 164, 112))]), m)
        out = soft_shadow(body, alpha=70, blur=2.5, dy=2)
        out.alpha_composite(body)
        sheen = vgrad(w, h, [(0, (255, 244, 220, 120)), (0.5, (255, 244, 220, 0)), (1, (255, 244, 220, 0))], box[1], box[3])
        out.alpha_composite(with_mask(sheen, m))
        e = canvas(w, h)
        ed = ImageDraw.Draw(e)
        rrect(ed, box, r, rgba(TERRA, 235), 1.6)
        out.alpha_composite(finish(e))
        # a small sun at the far end, clear of MainUI's arrows and marks
        place_center(out, sun_mark(20, 10, 10, 5.5, sun=(255, 246, 226), dune=TERRA), w - 17, h / 2 - 1)
        return out

    def divider(self):
        """A wind ripple."""
        im = canvas(640, 4)
        d = ImageDraw.Draw(im)
        pts = [(x, 2 + 0.8 * math.sin(x / 9.0)) for x in range(20, 621, 2)]
        d.line([(S(x), S(y)) for x, y in pts], fill=(255, 255, 255, 255), width=int(S(1.1)))
        m = finish(im).getchannel("A")
        ramp = hgrad(640, 4, [(0, (0, 0, 0, 0)), (0.08, (0, 0, 0, 255)), (0.92, (0, 0, 0, 255)), (1, (0, 0, 0, 0))])
        m = ImageChops.multiply(m, ramp.getchannel("A"))
        return solid((640, 4), CLAY, m.point(lambda v: v * 170 // 255))

    # ---- arches --------------------------------------------------------------------------
    def _arch(self, w, h, box, rt, rb, focused, inset=True, clear=130):
        m = arch_mask(w, h, box, rt, rb)
        if focused:
            body = with_mask(vgrad(w, h, TERRA_FILL, box[1], box[3]), m)
            halo = solid((w, h), (244, 150, 76), ImageChops.multiply(
                m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(5)), edge_fade(w, h)))
            out = over(soft_shadow(body, alpha=90, blur=5, dy=4), fade(halo, 0.9), body)
            # sunlight pooling in the top of the arch
            sun = rgrad(w, h, (box[0] + box[2]) / 2, box[1] + 18, (box[2] - box[0]) * 0.75,
                        [(0, (255, 226, 160, 150)), (1, (255, 226, 160, 0))])
            out.alpha_composite(with_mask(sun, m))
        else:
            body = with_mask(vgrad(w, h, [(0, (255, 246, 232, clear)), (0.55, (255, 246, 232, max(clear, 196))),
                                          (1, (253, 240, 222, 222))],
                                   box[1], box[3]), m)
            out = over(soft_shadow(body, alpha=40, blur=4, dy=3), body)
        rim = arch_ring(w, h, box, rt, rb, 1.6)
        out.alpha_composite(solid((w, h), (150, 56, 36) if focused else CLAY, rim.point(lambda v: v * 230 // 255)))
        if inset:   # the doorway's reveal
            k = 5.5
            ib = (box[0] + k, box[1] + k, box[2] - k, box[3] - k)
            ring = arch_ring(w, h, ib, max(0, rt - k), max(0, rb - k), 1.0)
            out.alpha_composite(solid((w, h), (255, 226, 180) if focused else (226, 184, 146),
                                      ring.point(lambda v: v * (150 if focused else 120) // 255)))
        return out

    def card(self, w, h, focused):
        if w == 155:   # games grid cell: a lower arch, so the system pictures fit under it
            return self._arch(w, h, (6, 4, w - 6, h - 6), 40, 10, focused, inset=False, clear=214)
        return self._arch(w, h, (6, 5, w - 6, h - 7), min(40, w / 2 - 6), 10, focused, inset=False, clear=214)

    def tile_base(self, focused):
        box = (12, 9, 144, 268)
        im = self._arch(156, 278, box, 66, 12, focused)
        # a little sun on the horizon under the label
        o = canvas(156, 278)
        d = ImageDraw.Draw(o)
        col = (255, 236, 206, 230) if focused else rgba(CLAY, 160)
        line(d, [(60, 242), (96, 242)], col, 1.4)
        d.pieslice([S(78 - 7), S(242 - 7), S(78 + 7), S(242 + 7)], 180, 360, fill=col)
        for a in (-150, -120, -90, -60, -30):
            r = math.radians(a)
            line(d, [(78 + math.cos(r) * 9.5, 242 + math.sin(r) * 9.5), (78 + math.cos(r) * 12.5, 242 + math.sin(r) * 12.5)],
                 col, 1.2)
        im.alpha_composite(finish(o))
        return im

    def _disc(self, n_w, n_h, cx, cy, r, col, focused, seed=1):
        """A sun-baked clay disc: lit from the upper left, a darker fired rim and fine grain."""
        out = Image.new("RGBA", (n_w, n_h), (0, 0, 0, 0))
        m_ss = Image.new("L", (n_w * SS, n_h * SS), 0)
        ImageDraw.Draw(m_ss).ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=255)
        m = m_ss.resize((n_w, n_h), Image.LANCZOS)
        if focused:   # sunlight behind it
            out.alpha_composite(rgrad(n_w, n_h, cx, cy, r * 1.75, [(0, (255, 234, 170, 255)), (0.55, (255, 214, 140, 150)),
                                                                   (1, (255, 200, 120, 0))]))
        body = with_mask(rgrad(n_w, n_h, cx - r * 0.35, cy - r * 0.42, r * 1.55,
                               [(0, lighter(col, 0.22)), (0.55, col), (1, darker(col, 0.2))]), m)
        out.alpha_composite(soft_shadow(body, alpha=110 if not focused else 80, blur=3, dy=3))
        out.alpha_composite(body)
        out.alpha_composite(solid((n_w, n_h), darker(col, 0.3), ImageChops.multiply(grain(n_w, n_h, 34, seed), m)))
        e = canvas(n_w, n_h)
        ed = ImageDraw.Draw(e)
        circle(ed, cx, cy, r - 0.7, rgba(darker(col, 0.3), 200), 1.4)
        ed.arc([S(cx - r + 3.4), S(cy - r + 3.4), S(cx + r - 3.4), S(cy + r - 3.4)], 190, 300,
               fill=(255, 255, 255, 110), width=int(S(1.4)))
        if focused:
            circle(ed, cx, cy, r + 1.8, rgba(CREAM, 255), 2.4)
        out.alpha_composite(finish(e))
        return out

    def _glyph_on(self, out, draw, col):
        """Cream line art pressed into a disc of colour [col]."""
        g = canvas(out.width, out.height)
        draw(ImageDraw.Draw(g), rgba(CREAM))
        g = finish(g)
        out.alpha_composite(soft_shadow(g, darker(col, 0.45), 200, 0.8, 1.6))
        out.alpha_composite(g)
        return out

    def home_tile(self, key, focused):
        im = super().home_tile(key, focused)
        return Image.merge("RGBA", [c.point(lambda v: v - v % 4) for c in im.split()])   # smaller PNGs, unseen

    def tile_glyph(self, key, focused):
        col = DISC[key]
        r = 46 if focused else 44
        out = self._disc(156, 278, 78, 112, r, col, focused, seed=sum(map(ord, key)))
        return self._glyph_on(out, lambda d, c: TILES[key](d, 78, 112, 25 if focused else 24, c, 4.6), col)

    # ---- buttons -------------------------------------------------------------------------
    BUTTONS = {"A": TERRA_DEEP, "B": INDIGO, "X": TEAL, "Y": (196, 128, 28)}

    def button(self, label, primary):
        n = 54
        col = self.BUTTONS.get(label, INDIGO)
        box = (8, 7, 46, 48)
        m = arch_mask(n, n, box, 19, 5)
        body = with_mask(vgrad(n, n, [(0, lighter(col, 0.2)), (1, darker(col, 0.08))], box[1], box[3]), m)
        out = over(soft_shadow(body, alpha=90, blur=1.6, dy=1.5), body)
        out.alpha_composite(solid((n, n), darker(col, 0.3), arch_ring(n, n, box, 19, 5, 1.2).point(lambda v: v * 200 // 255)))
        k = 3
        out.alpha_composite(solid((n, n), (255, 236, 210), arch_ring(n, n, (box[0] + k, box[1] + k, box[2] - k, box[3] - k),
                                                                     16, 3, 0.9).point(lambda v: v * 110 // 255)))
        t = canvas(n, n)
        ImageDraw.Draw(t).text((S(n / 2), S(30)), label, font=self.font(24), fill=rgba(CREAM), anchor="mm")
        t = finish(t)
        out.alpha_composite(soft_shadow(t, darker(col, 0.5), 180, 0.6, 1.0))
        out.alpha_composite(t)
        return out

    def pill(self, label, w, h=48):
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        box = (3, 8, w - 3, h - 8)
        r = (box[3] - box[1]) / 2
        rrect(d, (box[0], box[1] + 1.5, box[2], box[3] + 1.5), r, fill=rgba(SHADE, 50))
        rrect(d, box, r, fill=rgba(CREAM))
        rrect(d, box, r, rgba(INDIGO), 1.6)
        d.text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(h * 0.33), fill=rgba(INK), anchor="mm")
        return finish(im)

    def dot(self, active):
        im = canvas(20, 20)
        d = ImageDraw.Draw(im)
        if active:
            circle(d, 10, 10, 6.6, fill=rgba(CREAM))
            circle(d, 10, 10, 5.2, fill=rgba(TERRA))
            circle(d, 10, 10, 6.6, rgba(TERRA_DEEP), 1.0)
        else:
            circle(d, 10, 10, 3.2, fill=rgba(INDIGO, 150))
        return finish(im)

    def toggle(self, on):
        w, h = 92, 44
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        box = (8, 11, w - 8, h - 11)
        r = (box[3] - box[1]) / 2
        if on:
            rrect(d, box, r, fill=rgba(TERRA))
            rrect(d, box, r, rgba(TERRA_DEEP), 1.4)
        else:
            rrect(d, box, r, fill=(234, 214, 186, 255))
            rrect(d, box, r, rgba(CLAY), 1.4)
        cx = box[2] - r if on else box[0] + r
        circle(d, cx, h / 2 + 1.2, r + 3, fill=rgba(SHADE, 60))
        circle(d, cx, h / 2, r + 3, fill=rgba(CREAM))
        circle(d, cx, h / 2, r + 3, rgba(TERRA_DEEP if on else CLAY), 1.3)
        if on:
            circle(d, cx, h / 2, 4.4, fill=rgba(GOLD))
        return finish(im)

    def arrow(self, left, size=24):
        im = canvas(size, size)
        d = ImageDraw.Draw(im)
        xs = (0.62, 0.34) if left else (0.38, 0.66)
        line(d, [(size * xs[0], size * 0.22), (size * xs[1], size * 0.5), (size * xs[0], size * 0.78)], rgba(INK), size * 0.13)
        return finish(im)

    # ---- panels ----------------------------------------------------------------------------
    def panel_image(self, w, h):
        menu = w == 400   # pop-up menus: MainUI puts a square title band right on top
        r = 18
        box = (0, 0, w, h - 4) if menu else (3, 3, w - 3, h - 4)
        m_ss = Image.new("L", (w * SS, h * SS), 0)
        md = ImageDraw.Draw(m_ss)
        md.rounded_rectangle([S(v) for v in box], radius=S(r), fill=255)
        if menu:
            md.rectangle((0, 0, S(w), S(r)), fill=255)
        m = m_ss.resize((w, h), Image.LANCZOS)
        body = with_mask(vgrad(w, h, [(0, (255, 249, 238, 252)), (1, (252, 240, 222, 252))]), m)
        out = over(soft_shadow(body, alpha=70, blur=3, dy=2), body)
        # faint dunes along the bottom edge
        dn = dune_layer(w, h, h - 4, [(w * 0.18, 26, 30, 90), (w * 0.72, 18, 26, 80)], (246, 222, 190), (238, 206, 172))
        out.alpha_composite(with_mask(fade(dn, 0.8), m))
        e = canvas(w, h)
        ed = ImageDraw.Draw(e)
        col = rgba(TERRA, 230)
        if menu:
            ed.rounded_rectangle([S(v) for v in box], radius=S(r), outline=col, width=int(S(1.8)))
            ed.rectangle((0, 0, S(w), S(r)), fill=(0, 0, 0, 0))
            ed.rectangle((0, 0, S(1.8), S(r)), fill=col)
            ed.rectangle((S(w - 1.8), 0, S(w), S(r)), fill=col)
            ed.rectangle((0, 0, S(w), S(1.8)), fill=col)
        else:
            rrect(ed, box, r, col, 1.8)
        out.alpha_composite(finish(e))
        return out

    def preview_frame(self):
        im = canvas(250, 360)
        d = ImageDraw.Draw(im)
        rrect(d, (0.5, 0.5, 249.5, 359.5), 10, fill=rgba(CREAM))
        rrect(d, (0.5, 0.5, 249.5, 359.5), 10, rgba(TERRA), 2.2)
        return finish(im)

    def key(self, focused):
        """Dark keys (MainUI writes key labels in white), drawn at the letter keys' own size."""
        w, h = 52, 38
        box = (2, 2, w - 2, h - 3)
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        rrect(d, (box[0], box[1] + 1.2, box[2], box[3] + 1.2), 8, fill=rgba(SHADE, 70))
        rrect(d, box, 8, fill=rgba(TERRA_DEEP if focused else INDIGO))
        if not focused:
            line(d, [(box[0] + 8, box[1] + 1.6), (box[2] - 8, box[1] + 1.6)], (255, 255, 255, 60), 1.0)
            return finish(im)
        # a ring with thinner sides: wide keys (up to 3.5x) stretch it sideways only
        ring = Image.new("L", im.size, 0)
        rd = ImageDraw.Draw(ring)
        rd.rounded_rectangle([S(box[0] + 1.0), S(box[1] + 1.0), S(box[2] - 1.0), S(box[3] - 1.0)], radius=S(7), fill=255)
        rd.rounded_rectangle([S(box[0] + 1.5), S(box[1] + 2.4), S(box[2] - 1.5), S(box[3] - 2.4)], radius=S(6), fill=0)
        im.paste(rgba(SUNLIT), (0, 0), ring)
        return finish(im)

    def input_box(self):
        w, h = 560, 60
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        box = (2, 3, w - 2, h - 4)
        rrect(d, (box[0], box[1] + 1.5, box[2], box[3] + 1.5), 18, fill=rgba(SHADE, 45))
        rrect(d, box, 18, fill=rgba(CREAM))
        rrect(d, box, 18, rgba(TERRA), 1.8)
        return finish(im)

    # ---- small marks -----------------------------------------------------------------------
    def folder_icon(self):
        im = canvas(60, 60)
        g_folder(ImageDraw.Draw(im), 30, 31, 19, rgba(INK), 3.4)
        out = self._duotone(finish(im), (236, 190, 130, 190), (2, 2))
        return out

    def favorite_mark(self):
        im = canvas(34, 39)
        d = ImageDraw.Draw(im)
        pts = []
        for i in range(10):
            r = 14 if i % 2 == 0 else 6.4
            a = math.radians(-90 + i * 36)
            pts.append((17 + r * math.cos(a), 20.5 + r * math.sin(a)))
        poly(d, pts, rgba(CREAM), 3.4)
        poly(d, pts, fill=rgba(GOLD))
        poly(d, pts, rgba(TERRA_DEEP), 1.4)
        out = finish(im)
        return over(soft_shadow(out, alpha=70, blur=1.2, dy=1), out)

    def battery(self, level, charging=False):
        im = canvas(48, 48)
        d = ImageDraw.Draw(im)
        rrect(d, (5, 15, 40, 33), 5, rgba(INK), 2.2)
        rrect(d, (40.5, 20.5, 44, 27.5), 1.5, fill=rgba(INK))
        if level > 0:
            col = (204, 60, 48, 255) if level <= 0.2 else rgba(TEAL)
            rrect(d, (8.5, 18.5, 8.5 + 28 * level, 29.5), 2.6, fill=col)
        if charging:
            pts = [(25, 10), (16, 26), (23, 26), (20, 38), (31, 21), (24, 21)]
            poly(d, pts, rgba(CREAM), 3.2)
            poly(d, pts, fill=rgba(GOLD))
        return finish(im)

    # ---- system and app icons ---------------------------------------------------------------
    def _duotone(self, lines, fill, offset=(3, 3), grow=2):
        sil = silhouette(lines.getchannel("A"), grow)
        body = solid(lines.size, fill[:3], sil.point(lambda v: v * fill[3] // 255))
        out = Image.new("RGBA", lines.size, (0, 0, 0, 0))
        place(out, body, *offset)
        out.alpha_composite(lines)
        return out

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
            lines = self._lines(sid, rgba(INK), (52, 150, 152, 120), cy)
            return self._duotone(lines, (234, 186, 128, 150), (3, 3))
        lines = self._lines(sid, rgba(CREAM), (255, 214, 150, 120), cy)
        out = Image.new("RGBA", lines.size, (0, 0, 0, 0))
        place(out, solid(lines.size, (140, 50, 32), silhouette(lines.getchannel("A")).point(lambda v: v * 200 // 255)), 3, 3)
        out.alpha_composite(soft_shadow(lines, (110, 36, 22), 110, 1.0, 1.0))
        out.alpha_composite(lines)
        return out

    def system_icon(self, sid, selected):
        label = {"segacd": "SCD", "xbox": "XB"}.get(sid, BADGES.get(sid, sid[:7].upper()))
        out = self.icon_picture(sid, selected, 52 if label else 62)
        if label:
            out = Image.alpha_composite(out, self.badge(label, selected))
        return out

    def badge(self, label, selected):
        f = self.font(14)
        probe = ImageDraw.Draw(canvas(1, 1))
        tw = probe.textlength(label, font=f) / SS
        bw = min(116, tw + 18)
        x0 = (120 - bw) / 2
        box = (x0, 105, x0 + bw, 126)
        m = arch_mask(120, 130, box, 10, 3.5)
        out = solid((120, 130), CREAM if selected else INDIGO, m)
        if selected:
            out.alpha_composite(solid((120, 130), TERRA_DEEP, arch_ring(120, 130, box, 10, 3.5, 1.2)))
        t = canvas(120, 130)
        ImageDraw.Draw(t).text((S(60), S(116.2)), label, font=f, fill=rgba(TERRA_DEEP if selected else CREAM), anchor="mm")
        out.alpha_composite(finish(t))
        return out

    def app_icon(self, key):
        n = 96
        col = APP_DISCS[list(APPS).index(key) % len(APP_DISCS)]
        box = (8, 6, n - 8, n - 7)
        m = arch_mask(n, n, box, 40, 10)
        body = solid((n, n), col, m)
        out = over(soft_shadow(body, alpha=80, blur=2.5, dy=2), body)
        lit = rgrad(n, n, n * 0.38, n * 0.3, n * 0.6, [(0, (255, 255, 255, 60)), (1, (255, 255, 255, 0))])
        out.alpha_composite(with_mask(lit, m))
        out.alpha_composite(solid((n, n), darker(col, 0.3), arch_ring(n, n, box, 40, 10, 1.4)))
        k = 4.5
        inner = arch_ring(n, n, (box[0] + k, box[1] + k, box[2] - k, box[3] - k), 35.5, 5.5, 1.0)
        out.alpha_composite(solid((n, n), lighter(col, 0.45), inner.point(lambda v: v * 150 // 255)))
        return self._glyph_on(out, lambda d, c: APPS[key](d, n / 2, n / 2 + 3, n * 0.24, c, n * 0.055), col)

    # ---- sound ------------------------------------------------------------------------------
    def sound(self, path):
        """A soft clay-pot tock: a low hollow partial with a short wooden click on top."""
        rate = 22050
        frames = bytearray()
        for i in range(int(rate * 0.07)):
            t = i / rate
            env = math.exp(-t * 70) * min(1.0, t / 0.0015)
            s = 0.75 * math.sin(2 * math.pi * 620 * t) + 0.25 * math.sin(2 * math.pi * 1490 * t) * math.exp(-t * 160)
            frames += struct.pack("<h", int(8200 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))
