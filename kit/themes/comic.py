"""Comic: a pop-art comic page. Cyan Ben-Day dots, bold black ink, flat CMYK colour, tilted
panels, caption boxes and speech balloons; the focused panel bursts out in yellow."""
import math
import random
import struct
import wave
import zlib

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, GLYPHS, SS, Pen, Style, finish, hexc, lerp, rgba, system_ids

INK = (22, 20, 28)
PAPER = (255, 252, 240)
CYAN = (0, 170, 234)
CYAN_D = (0, 142, 206)
CYAN_L = (170, 228, 250)
YELLOW = (255, 220, 0)
RED = (234, 34, 46)
MAGENTA = (230, 0, 126)
BLUE = (40, 96, 214)
GREEN = (0, 170, 92)
ORANGE = (255, 138, 0)
GREY = (70, 70, 82)
WHITE = (255, 255, 255)
TILT = {"recent": -1.6, "favorite": 1.3, "game": -1.1, "emulators": 1.6, "retroarch": -1.3, "app": 1.1, "setting": -1.5}
ICON_BODY = [CYAN, RED, YELLOW, MAGENTA, GREEN, ORANGE, BLUE]
DETAIL = {CYAN: YELLOW, RED: CYAN_L, YELLOW: CYAN_L, MAGENTA: YELLOW, GREEN: YELLOW, ORANGE: CYAN_L, BLUE: YELLOW}
APP_COLOR = {"activity": GREEN, "download": CYAN, "folder": ORANGE, "gallery": MAGENTA, "gameswitcher": RED,
             "pacman": YELLOW, "retroarch": GREEN, "search": CYAN, "themes": MAGENTA, "tweaks": BLUE,
             "hidden": BLUE, "emulators": RED, "category": ORANGE, "updates": GREEN, "repos": MAGENTA}
INVADER = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX",
           "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."]


def S(v):
    return v * SS


def seed_of(*parts):
    return zlib.crc32("/".join(str(p) for p in parts).encode())


def blank(w, h):
    return Image.new("L", (w * SS, h * SS), 0)


def clear(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def layer(im, color, mask):
    """[im] with [color] painted through [mask] (same size; the colour's alpha scales it)."""
    c = Image.new("RGBA", im.size, rgba(color))
    if len(color) > 3 and color[3] != 255:
        mask = mask.point(lambda v, k=color[3]: v * k // 255)
    c.putalpha(mask)
    return Image.alpha_composite(im, c)


def lean(im, n=64):
    """Flat art in fewer colours: packs far smaller as PNG and looks the same."""
    return im.quantize(n, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).convert("RGBA")


def shift(mask, dx, dy):
    out = Image.new(mask.mode, mask.size, 0)
    out.paste(mask, (int(round(S(dx))), int(round(S(dy)))))
    return out


def dark(c, t=0.28):
    return lerp(c, INK, t)


def rotated(box, deg, cx=None, cy=None):
    """Corners of [box] turned [deg] degrees about its centre (or (cx, cy))."""
    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2 if cx is None else cx
    cy = (y0 + y1) / 2 if cy is None else cy
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca)
            for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def poly_mask(w, h, pts, g=0.0):
    """[pts] filled (SS L), grown by [g] 1x px with rounded corners."""
    m = blank(w, h)
    d = ImageDraw.Draw(m)
    p = [(S(x), S(y)) for x, y in pts]
    d.polygon(p, fill=255)
    if g > 0:
        d.line(p + [p[0]], fill=255, width=int(S(2 * g)), joint="curve")
        for x, y in p:
            d.ellipse([x - S(g), y - S(g), x + S(g), y + S(g)], fill=255)
    return m


def burst_pts(cx, cy, r0, r1, n, seed, jit=0.14, rot=-90):
    """An explosion balloon: [n] spikes between radii r1 (inner) and r0 (outer), a little uneven."""
    rnd = random.Random(seed)
    pts = []
    for i in range(n * 2):
        r = (r0 if i % 2 == 0 else r1) * (1 + rnd.uniform(-jit, jit))
        a = math.radians(rot + i * 180 / n + rnd.uniform(-5, 5))
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def star_pts(cx, cy, r0, r1, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r0 if i % 2 == 0 else r1
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def halftone(w, h, spacing, radius, angle=45, box=None):
    """Ben-Day dots (SS L): a grid turned [angle], each dot radius(x, y) 1x px (<= 0: none)."""
    m = blank(w, h)
    d = ImageDraw.Draw(m)
    x0, y0, x1, y1 = box or (0, 0, w, h)
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    n = int(math.hypot(x1 - x0, y1 - y0) / spacing / 2) + 2
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            u, v = i * spacing, j * spacing
            x, y = cx + u * ca - v * sa, cy + u * sa + v * ca
            if x0 - 3 < x < x1 + 3 and y0 - 3 < y < y1 + 3:
                r = radius(x, y)
                if r > 0.2:
                    d.ellipse([S(x - r), S(y - r), S(x + r), S(y + r)], fill=255)
    return m


class Ink:
    """Flat colour shapes with bold ink outlines, around (cx, cy) in 1x px. shape() inks the
    union of its parts [line] thick outside them, fills them, and can shade them with dots."""

    def __init__(self, im, cx, cy, line=4.5):
        self.im, self.cx, self.cy, self.line = im, cx, cy, line
        self.w, self.h = im.width // SS, im.height // SS

    def P(self, x, y):
        return S(self.cx + x), S(self.cy + y)

    def mask(self, parts, g=0.0):
        m = blank(self.w, self.h)
        d = ImageDraw.Draw(m)
        for p in parts:
            kind = p[0]
            if kind == "rr":
                (x0, y0, x1, y1), r = p[1], p[2]
                d.rounded_rectangle([*self.P(x0 - g, y0 - g), *self.P(x1 + g, y1 + g)], radius=S(r + g), fill=255)
            elif kind == "ci":
                x, y, r = p[1:4]
                d.ellipse([*self.P(x - r - g, y - r - g), *self.P(x + r + g, y + r + g)], fill=255)
            elif kind == "el":
                x0, y0, x1, y1 = p[1]
                d.ellipse([*self.P(x0 - g, y0 - g), *self.P(x1 + g, y1 + g)], fill=255)
            elif kind == "poly":
                pts = [self.P(x, y) for x, y in p[1]]
                d.polygon(pts, fill=255)
                if g:
                    d.line(pts + [pts[0]], fill=255, width=int(S(2 * g)), joint="curve")
                    for x, y in pts:
                        d.ellipse([x - S(g), y - S(g), x + S(g), y + S(g)], fill=255)
            elif kind == "ln":
                pts = [self.P(x, y) for x, y in p[1]]
                rad = S(p[2] / 2 + g)
                d.line(pts, fill=255, width=int(2 * rad), joint="curve")
                for x, y in pts:
                    d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=255)
            elif kind == "cut":  # a hole through what was drawn so far
                x, y, r = p[1:4]
                d.ellipse([*self.P(x - r + g, y - r + g), *self.P(x + r - g, y + r - g)], fill=0)
        return m

    def shade(self, m, color, k=1.0):
        """Dots darkening towards the lower right of the shape's own box."""
        bb = m.getbbox()
        if not bb:
            return
        x0, y0, x1, y1 = (v / SS for v in bb)
        span = max(1.0, (x1 - x0) + (y1 - y0))

        def rad(x, y):
            t = ((x - x0) + (y - y0)) / span
            return (t - 0.45) * 3.4 * k

        dots = halftone(self.w, self.h, 3.6, rad, 45, (x0, y0, x1, y1))
        self.im = layer(self.im, color, ImageChops.multiply(dots, m))

    def shape(self, parts, fill, line=None, shade=True, shine=None):
        lw = self.line if line is None else line
        if lw:
            self.im = layer(self.im, INK, self.mask(parts, lw))
        if fill is not None:
            m = self.mask(parts)
            self.im = layer(self.im, fill, m)
            if shade:
                self.shade(m, dark(fill, 0.22))
            if shine:
                self.im = layer(self.im, WHITE, self.mask([("ln", shine, 2.6)]))

    def ink(self, parts):
        self.im = layer(self.im, INK, self.mask(parts))


# ---- the main menu objects ---------------------------------------------------------------

def m_recent(st):
    st.shape([("ci", 0, 0, 37)], CYAN)
    st.shape([("ci", 0, 0, 26)], PAPER, 3.5, shade=False)
    for a in range(0, 360, 30):
        r0 = 21 if a % 90 else 18
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        st.ink([("ln", [(r0 * ca, r0 * sa), (24 * ca, 24 * sa)], 3 if a % 90 == 0 else 2)])
    st.ink([("ln", [(0, -17), (0, 0), (12, 8)], 5)])
    st.shape([("ci", 0, 0, 4)], RED, 2.5, shade=False)
    st.im = layer(st.im, WHITE, st.mask([("ln", [(-27, -14), (-20, -25)], 3.2)]))


def m_favorite(st):
    st.shape([("poly", star_pts(0, 4, 44, 20))], YELLOW, shine=[(-14, -4), (-8, -12)])


def m_game(st):
    st.shape([("rr", (-46, -24, 46, 14), 17), ("ci", -28, 12, 18), ("ci", 28, 12, 18)], RED,
             shine=[(-34, -12), (-20, -17)])
    st.ink([("rr", (-37, -7, -15, 0), 1.5), ("rr", (-29.5, -14.5, -22.5, 7.5), 1.5)])
    st.shape([("ci", 21, 0, 6)], YELLOW, 3, shade=False)
    st.shape([("ci", 33, -10, 6)], CYAN, 3, shade=False)


def m_emulators(st):
    st.shape([("rr", (-30, -44, 30, 44), 10)], MAGENTA, shine=[(-22, 30), (-22, -30)])
    st.shape([("rr", (-20, -34, 20, 2), 4)], CYAN_L, 3.5, shade=False)
    st.ink([("rr", (-22, 16, -4, 22), 1.5), ("rr", (-16, 10, -10, 28), 1.5)])
    st.shape([("ci", 11, 24, 5)], YELLOW, 3, shade=False)
    st.shape([("ci", 21, 14, 5)], YELLOW, 3, shade=False)


def m_expert(st):
    c = 8.0
    x0, y0 = -c * 5.5, -c * 4 + 2
    parts = [("rr", (x0 + i * c - 0.3, y0 + j * c - 0.3, x0 + (i + 1) * c + 0.3, y0 + (j + 1) * c + 0.3), 0.6)
             for j, row in enumerate(INVADER) for i, ch in enumerate(row) if ch == "X"]
    st.shape(parts, GREEN, 4.5)


def m_apps(st):
    st.shape([("rr", (-40, -40, -6, -6), 5)], CYAN)
    st.shape([("ci", 23, -23, 17)], RED)
    st.shape([("poly", [(-23, 4), (-5, 38), (-41, 38)])], YELLOW)
    st.shape([("rr", (6, 6, 40, 40), 5)], MAGENTA)


def m_setting(st):
    pts = []
    for i in range(32):
        a = math.radians(i * 360 / 32 - 90 + 360 / 8 / 8)
        r = 42 if (i % 4) in (1, 2) else 31
        pts.append((r * math.cos(a), r * math.sin(a)))
    st.shape([("poly", pts)], BLUE)
    st.shape([("ci", 0, 0, 13)], PAPER, 4, shade=False)


MENU = {"recent": m_recent, "favorite": m_favorite, "game": m_game, "emulators": m_emulators,
        "retroarch": m_expert, "app": m_apps, "setting": m_setting}


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
    name = "Comic"
    author = "MainUI"
    description = "A pop-art comic page: cyan Ben-Day dots, bold ink, flat CMYK colour, caption boxes and a bursting yellow focus."

    bg_top = CYAN
    bg_bottom = CYAN
    accent = RED
    accent2 = INK
    highlight = RED
    text = INK
    muted = GREY
    glyph_n = INK
    glyph_f = INK
    panel = YELLOW            # toasts become caption boxes; MainUI's pop-up title strip a darker yellow
    panel_alpha = 252
    bar = YELLOW
    bar_alpha = 255

    font_file = "Bangers-Regular.ttf"
    font_license = "OFL-Bangers.txt"
    # Lists (and dialog text) in dialogue lettering: MainUI draws list text bold, which clogs Bangers.
    list_font, list_license = "PatrickHandSC-Regular.ttf", "OFL-PatrickHandSC.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 32, 26, 28, 25, 18, 20
    icon_quant = 64

    # ---- page ---------------------------------------------------------------------------
    def background(self, w=640, h=480):
        """Ben-Day dots on cyan: bigger towards the corners, almost gone where text sits."""
        im = Image.new("RGBA", (w * SS, h * SS), rgba(CYAN))

        def rad(x, y):
            t = math.hypot((x - w / 2) / (w / 2), (y - h / 2) / (h / 2)) / 1.414
            return 0.6 + 2.6 * max(0.0, t - 0.25) / 0.75

        im = layer(im, CYAN_D, halftone(w, h, 8.5, rad, 30))
        return lean(finish(im), 24)

    def header_bar(self):
        """A yellow caption strip, inked along its lower edge."""
        w, h = 640, 60
        im = clear(w, h)
        im = layer(im, INK, poly_mask(w, h, [(0, 0), (w, 0), (w, 56), (0, 56)]))
        im = layer(im, YELLOW, poly_mask(w, h, [(0, 0), (w, 0), (w, 51.5), (0, 51.5)]))
        dots = halftone(w, h, 5, lambda x, y: (x - 470) / 170 * 1.9 - (y / 60) * 0.4, 45, (430, 0, w, 51.5))
        im = layer(im, ORANGE, dots)
        return lean(finish(im), 32)

    def footer_bar(self):
        w, h = 640, 60
        im = clear(w, h)
        im = layer(im, INK, poly_mask(w, h, [(0, 0), (w, 0), (w, h), (0, h)]))
        im = layer(im, PAPER, poly_mask(w, h, [(0, 4), (w, 4), (w, h), (0, h)]))
        return finish(im)

    def logo(self):
        """The masthead: white letters, inked and extruded in red, tilted up a little."""
        w, h = 172, 54
        im = clear(w, h)
        d = ImageDraw.Draw(im)
        f = self.font(42)
        x, y = 8, 27
        for k in range(6, 0, -1):
            d.text((S(x + k * 0.6), S(y + k * 0.6)), "MainUI", font=f, fill=rgba(INK), anchor="lm",
                   stroke_width=int(S(2.8)), stroke_fill=rgba(INK))
        d.text((S(x + 2.4), S(y + 2.4)), "MainUI", font=f, fill=rgba(RED), anchor="lm")
        d.text((S(x), S(y)), "MainUI", font=f, fill=rgba(WHITE), anchor="lm", stroke_width=int(S(2.8)), stroke_fill=rgba(INK))
        d.text((S(x), S(y)), "MainUI", font=f, fill=rgba(WHITE), anchor="lm")
        im = im.rotate(4, Image.BICUBIC, center=(S(w / 2), S(h / 2)))
        return finish(im)

    # ---- lists --------------------------------------------------------------------------
    def selection(self, h):
        """A yellow caption box, slanted, inked, over a hard shadow."""
        w = 640
        p = 6 if h < 70 else 10
        sl = 6
        pts = [(8 + sl, p), (w - 10, p), (w - 10 - sl, h - p - 5), (8, h - p - 5)]
        im = clear(w, h)
        outer = poly_mask(w, h, pts, 3)
        im = layer(im, INK, shift(outer, 4, 4))
        im = layer(im, INK, outer)
        im = layer(im, YELLOW, poly_mask(w, h, pts))
        return finish(im)

    def divider(self):
        im = clear(640, 4)
        d = ImageDraw.Draw(im)
        for x in range(24, 618, 7):
            d.ellipse([S(x - 1.1), S(0.9), S(x + 1.1), S(3.1)], fill=rgba(INK, 70))
        return finish(im)

    # ---- panels -------------------------------------------------------------------------
    def panel_shape(self, w, h, box, tilt, focused, seed):
        """A comic panel: newsprint and ink (unfocused), or yellow with dots and a burst behind
        the picture at (bx, by), over a hard shadow (focused)."""
        pts = rotated(box, tilt)
        im = clear(w, h)
        lw = 4.5 if focused else 3.2
        outer = poly_mask(w, h, pts, lw)
        if focused:
            im = layer(im, INK, shift(outer, 6, 6))
        im = layer(im, INK, outer)
        inner = poly_mask(w, h, pts)
        im = layer(im, YELLOW if focused else PAPER, inner)
        return im, inner, pts

    def pop(self, im, inner, w, h, bx, by, r0, r1, seed, label_y=None, band=22):
        """The focused panel's dots (thinning towards the label) and its burst."""
        x0, y0, x1, y1 = (v / SS for v in inner.getbbox())

        def rad(x, y):
            dd = math.hypot(x - bx, y - by)
            r = (dd - r1 * 0.9) / 40 * 1.6
            if label_y is not None:
                r -= max(0.0, 1 - abs(y - label_y) / band) * 3
            return min(1.45, r)

        dots = halftone(w, h, 5.2, rad, 45, (x0, y0, x1, y1))
        im = layer(im, ORANGE, ImageChops.multiply(dots, inner))
        pts = burst_pts(bx, by, r0, r1, 13, seed)
        im = layer(im, INK, ImageChops.multiply(poly_mask(w, h, pts, 3.2), inner))
        return layer(im, WHITE, ImageChops.multiply(poly_mask(w, h, pts), inner))

    def card(self, w, h, focused):
        box = (8, 9, w - 10, h - 9)
        im, inner, _ = self.panel_shape(w, h, box, -0.8 if focused else 0.6, focused, seed_of("card", w, h))
        if focused:
            im = self.pop(im, inner, w, h, w / 2 - 1, 68, 66, 46, seed_of("cardburst", w, h), 148)
        return lean(finish(im))

    def _tile(self, key, focused):
        w, h = 156, 278
        tilt = TILT.get(key, -1.0) * (1.5 if focused else 1)
        box = (12, 14, 143, 262) if not focused else (10, 10, 145, 262)
        im, inner, _ = self.panel_shape(w, h, box, tilt, focused, seed_of("tile", key))
        if focused:   # (the row view's tile: MainUI writes system names at 170-204, counts at 222)
            im = self.pop(im, inner, w, h, 78, 108, 70, 50, seed_of("burst", key),
                          195 if key else 200, 22 if key else 42)
        else:
            im = self.tint(im, inner, w, h, 222)
        return im

    @staticmethod
    def tint(im, inner, w, h, y0):
        """Pale printed dots growing towards the panel's foot, clear of the label above [y0]."""
        x0, _, x1, y1 = (v / SS for v in inner.getbbox())
        dots = halftone(w, h, 5.2, lambda x, y: (y - y0) / (y1 - y0) * 1.9, 45, (x0, y0, x1, y1))
        return layer(im, CYAN_L, ImageChops.multiply(dots, inner))

    def tile_base(self, focused):
        return lean(finish(self._tile(None, focused)))

    def tile_glyph(self, key, focused):
        st = Ink(clear(156, 278), 78, 108 if focused else 112)
        MENU[key](st)
        return st.im

    def home_tile(self, key, focused):
        if key is None:
            return self.tile_base(focused)
        return lean(finish(Image.alpha_composite(self._tile(key, focused), self.tile_glyph(key, focused))), 96)

    # ---- buttons and small parts ----------------------------------------------------------
    def button(self, label, primary):
        """A: a red burst. B, X, Y: tilted caption squares in cyan, yellow, magenta."""
        n = 54
        im = clear(n, n)
        if label == "A":
            pts = burst_pts(26, 26, 25, 17.5, 10, 7, 0.06)
            fill, tc = RED, WHITE
        else:
            pts = rotated((10, 10, 42, 42), {"B": -7, "X": 6, "Y": -5}[label])
            fill, tc = {"B": CYAN, "X": YELLOW, "Y": MAGENTA}[label], (WHITE if label == "Y" else INK)
        outer = poly_mask(n, n, pts, 2.6)
        im = layer(im, INK, shift(outer, 2.5, 2.5))
        im = layer(im, INK, outer)
        im = layer(im, fill, poly_mask(n, n, pts))
        d = ImageDraw.Draw(im)
        f = self.font(27)
        if tc == WHITE:
            d.text((S(26), S(27)), label, font=f, fill=rgba(INK), anchor="mm", stroke_width=int(S(2.2)), stroke_fill=rgba(INK))
        d.text((S(26), S(27)), label, font=f, fill=rgba(tc), anchor="mm")
        return finish(im)

    def pill(self, label, w, h=48):
        im = clear(w, h)
        pts = [(6, 11), (w - 4, 10), (w - 6, h - 13), (4, h - 12)]
        outer = poly_mask(w, h, pts, 2.2)
        im = layer(im, INK, shift(outer, 2.5, 2.5))
        im = layer(im, INK, outer)
        im = layer(im, PAPER, poly_mask(w, h, pts))
        ImageDraw.Draw(im).text((S(w / 2), S(h / 2 - 0.5)), label, font=self.font(19), fill=rgba(INK), anchor="mm")
        return finish(im)

    def dot(self, active):
        im = clear(24, 14)
        st = Ink(im, 12, 7, 2.0)
        if active:
            st.shape([("ci", 0, 0, 4.6)], RED, 2.0, shade=False)
        else:
            st.shape([("ci", 0, 0, 2.6)], PAPER, 1.8, shade=False)
        return finish(st.im)

    def toggle(self, on):
        w, h = 92, 44
        im = clear(w, h)
        st = Ink(im, 0, 0, 3.0)
        track = [("rr", (8, 11, 82, 33), 11)]
        st.im = layer(st.im, INK, shift(st.mask(track, 3), 3, 3))
        st.shape(track, RED if on else PAPER, shade=False)
        st.shape([("ci", 70 if on else 20, 22, 8)], WHITE if on else (220, 218, 210), 3, shade=False)
        return finish(st.im)

    def arrow(self, left, size=24):
        s = size
        im = clear(s, s)
        pts = [(0.22, 0.5), (0.72, 0.2), (0.72, 0.8)] if left else [(0.78, 0.5), (0.28, 0.2), (0.28, 0.8)]
        tri = [(x * s - s * 0.02, y * s - s * 0.03) for x, y in pts]
        st = Ink(im, 0, 0, s / 12)
        st.im = layer(st.im, INK, shift(st.mask([("poly", tri)], s / 12), s / 16, s / 16))
        st.shape([("poly", tri)], YELLOW, shade=False)
        return finish(st.im)

    def panel_image(self, w, h):
        if w >= 600:
            return self.balloon(w, h)
        # pop-up menus: a newsprint box flush under MainUI's title strip, inked sides and foot
        im = clear(w, h)
        outer = poly_mask(w, h, [(0, -10), (w, -10), (w, h - 6), (0, h - 6)])
        im = layer(im, INK, shift(outer, 0, 5))
        im = layer(im, INK, outer)
        im = layer(im, PAPER, poly_mask(w, h, [(3.5, -10), (w - 3.5, -10), (w - 3.5, h - 9.5), (3.5, h - 9.5)]))
        im = layer(im, INK, poly_mask(w, h, [(0, 0), (w, 0), (w, 3), (0, 3)]))
        return finish(im)

    def balloon(self, w, h):
        """Dialogs: a speech balloon with its tail at the lower left."""
        im = clear(w, h)
        body = (24, 12, w - 30, h - 46)
        m = blank(w, h)
        d = ImageDraw.Draw(m)
        d.rounded_rectangle([S(v) for v in body], radius=S(34), fill=255)
        d.polygon([(S(x), S(y)) for x, y in ((84, h - 60), (136, h - 60), (70, h - 8))], fill=255)
        grown = m.filter(ImageFilter.MaxFilter(2 * round(4 * SS / 2) + 1))
        grown = grown.filter(ImageFilter.MaxFilter(2 * round(4 * SS / 2) + 1))
        im = layer(im, INK, shift(grown, 7, 7))
        im = layer(im, INK, grown)
        return lean(finish(layer(im, PAPER, m)), 32)

    def folder_icon(self):
        st = Ink(clear(60, 60), 30, 31, 3.0)
        st.im = layer(st.im, INK, shift(st.mask([("rr", (-19, -15, 19, 15), 3)], 3), 2.5, 2.5))
        st.shape([("rr", (-19, -15, -3, -5), 2), ("rr", (-19, -10, 19, 15), 3)], ORANGE, shade=False)
        st.shape([("rr", (-19, -3, 19, 15), 3)], YELLOW, shade=False)
        return finish(st.im)

    def favorite_mark(self):
        st = Ink(clear(34, 39), 16, 19, 2.4)
        pts = star_pts(0, 0, 14, 6.4)
        st.im = layer(st.im, RED, shift(st.mask([("poly", pts)], 2.4), 2.5, 2.5))
        st.shape([("poly", pts)], YELLOW, shade=False)
        return finish(st.im)

    def battery(self, level, charging=False):
        st = Ink(clear(48, 48), 0, 0, 2.6)
        st.im = layer(st.im, INK, shift(st.mask([("rr", (6, 15, 39, 33), 3)], 2.6), 2, 2))
        st.shape([("rr", (6, 15, 39, 33), 3), ("rr", (39, 20, 43, 28), 1)], WHITE, shade=False)
        if level > 0:
            st.im = layer(st.im, RED if level <= 0.2 else GREEN, st.mask([("rr", (9, 18, 9 + 27 * level, 30), 1.5)]))
        if charging:
            st.shape([("poly", [(26, 6), (14, 26), (22, 26), (19, 42), (33, 20), (25, 20)])], YELLOW, 2.2, shade=False)
        return finish(st.im)

    def preview_frame(self):
        w, h = 250, 360
        im = clear(w, h)
        pts = [(4, 4), (w - 9, 4), (w - 9, h - 9), (4, h - 9)]
        outer = poly_mask(w, h, pts, 3)
        im = layer(im, INK, shift(outer, 5, 5))
        im = layer(im, INK, outer)
        return finish(layer(im, PAPER, poly_mask(w, h, pts)))

    def key(self, focused):
        """MainUI writes key labels in white: inked keys, the focused one red."""
        w, h = 52, 40
        im = clear(w, h)
        st = Ink(im, 0, 0, 2.5)
        k = [("rr", (3, 3, w - 3, h - 6), 5)]
        st.im = layer(st.im, INK, shift(st.mask(k, 1.5), 0, 3))
        st.shape(k, RED if focused else (52, 52, 64), 1.5 if not focused else 2.5, shade=False)
        if focused:
            st.im = layer(st.im, YELLOW, ImageChops.subtract(st.mask(k, 2.5), st.mask(k, 0.6)))
        return finish(st.im)

    def input_box(self):
        w, h = 560, 60
        im = clear(w, h)
        pts = [(4, 4), (w - 9, 4), (w - 9, h - 9), (4, h - 9)]
        outer = poly_mask(w, h, pts, 3)
        im = layer(im, INK, shift(outer, 4, 4))
        im = layer(im, INK, outer)
        return finish(layer(im, WHITE, poly_mask(w, h, pts)))

    # ---- system and app icons -------------------------------------------------------------
    _order = None
    _scales = {}

    def icon_colors(self, sid):
        if Theme._order is None:
            Theme._order = {s: i for i, s in enumerate(system_ids())}
        body = ICON_BODY[Theme._order.get(sid, len(sid)) % len(ICON_BODY)]
        return body, DETAIL[body]

    def _layers(self, draw, cx, cy, k, lw=4.4):
        """(lines, soft) SS masks of a GLYPHS drawing [k] times its size around (cx, cy)."""
        out = []
        for c, soft in (((255, 255, 255, 255), (0, 0, 0, 0)), ((0, 0, 0, 0), (255, 255, 255, 255))):
            im = clear(120, 130)
            p = Pen(ImageDraw.Draw(im), cx / k, cy / k, c, SS * k, w=lw / k)
            p.soft_c = soft
            draw(p)
            out.append(im.getchannel("A"))
        return out

    def icon_picture(self, sid, selected, cy):
        draw = GLYPHS.get(sid) or GLYPHS["fallback"]
        x0, y0, x1, y1 = (v / SS for v in self._layers(draw, 60, cy, 1.0)[0].getbbox())
        k = min(1.12, 55 / max(60 - x0, x1 - 60), (cy - 5) / (cy - y0), (125 - cy) / (y1 - cy))
        la, soft = self._layers(draw, 60, cy, k, 4.4 if k > 0.95 else 4.4 * (0.6 + 0.4 * k / 0.95))
        body = enclosed(la, 120, 130)
        soft = soft.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
        fill, detail = self.icon_colors(sid)
        n = 2 * round(3.2 * SS) + 1
        core = la.filter(ImageFilter.MinFilter(n))
        if core.getbbox():   # solid silhouettes (android): coloured in, an ink rim kept
            la = ImageChops.subtract(la, core)
            body = ImageChops.lighter(body, core)
        body = ImageChops.subtract(body, soft)
        st = Ink(clear(120, 130), 0, 0)
        st.im = layer(st.im, fill, body)
        st.shade(body, dark(fill, 0.25), 0.9)
        st.im = layer(st.im, detail, soft)
        st.im = layer(st.im, INK, la)
        return finish(st.im)

    def system_icon(self, sid, selected):
        # (no name badge: MainUI writes the name under every icon)
        return self.icon_picture(sid, selected, 63)

    def app_icon(self, key):
        """A tilted panel in the app's colour, with its picture inked in white."""
        n = 96
        col = APP_COLOR.get(key, CYAN)
        im = clear(n, n)
        pts = rotated((10, 10, 84, 84), -4 + seed_of("tilt", key) % 9)
        outer = poly_mask(n, n, pts, 3.5)
        im = layer(im, INK, shift(outer, 4, 4))
        im = layer(im, INK, outer)
        inner = poly_mask(n, n, pts)
        im = layer(im, col, inner)
        dots = halftone(n, n, 5, lambda x, y: (x + y - 100) / 70 * 1.9, 45)
        im = layer(im, dark(col, 0.22), ImageChops.multiply(dots, inner))
        g = clear(n, n)
        gd = ImageDraw.Draw(g)
        if key == "retroarch":
            st = Ink(g, 47, 47, 3.2)
            c = 5.6
            x0, y0 = -c * 5.5, -c * 4
            st.shape([("rr", (x0 + i * c - 0.25, y0 + j * c - 0.25, x0 + (i + 1) * c + 0.25, y0 + (j + 1) * c + 0.25), 0.4)
                      for j, row in enumerate(INVADER) for i, ch in enumerate(row) if ch == "X"], WHITE, shade=False)
            return finish(Image.alpha_composite(im, st.im))
        APPS[key](gd, 47, 47, n * 0.24, (255, 255, 255, 255), n * 0.07)
        im = finish(im)
        ga = finish(g).getchannel("A")
        # inked round its outside only, so the details inside stay white on the panel colour
        pad = Image.new("L", (n + 2, n + 2), 0)
        pad.paste(ga.point(lambda v: 255 if v > 60 else 0), (1, 1))
        ImageDraw.floodfill(pad, (0, 0), 128)
        sil = pad.crop((1, 1, n + 1, n + 1)).point(lambda v: 0 if v == 128 else 255)
        rim = sil.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.5))
        rim = ImageChops.subtract(rim, ImageChops.subtract(sil, ga))
        im = Image.alpha_composite(im, Image.merge("RGBA", (*Image.new("RGB", (n, n), INK).split(), rim)))
        return Image.alpha_composite(im, Image.merge("RGBA", (*Image.new("RGB", (n, n), WHITE).split(), ga)))

    # ---- sound and config -----------------------------------------------------------------
    def sound(self, path):
        """A quick cartoon 'boing': a pitch drop with a little wobble."""
        rate, length = 22050, 0.06
        frames = bytearray()
        ph = 0.0
        for i in range(int(rate * length)):
            t = i / rate
            f = 900 - 420 * (t / length) + 60 * math.sin(t * 2 * math.pi * 45)
            ph += 2 * math.pi * f / rate
            env = min(1.0, t / 0.002, (length - t) / 0.006) * math.exp(-t * 38)
            s = math.sin(ph) + 0.25 * math.sin(2 * ph)
            frames += struct.pack("<h", int(8500 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["list"]["font"] = self.list_font
        cfg["currentpage"] = {"color": hexc(RED)}
        return cfg

    def fonts(self):
        return super().fonts() + [self.list_license]
