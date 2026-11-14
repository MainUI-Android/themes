"""Crimson: punchy flat dark. Charcoal, a solid crimson header bar, flat tiles with a darker foot
band, bright glowing colour discs with white pictures and heavy italic type."""
import math
import struct
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, BADGES, GLYPHS, SS, Pen, S, Style, finish, hexa, hexc, lerp, rgba, system_ids

# ---- palette ------------------------------------------------------------------------------
CHAR_TOP = (36, 37, 43)
CHAR = (28, 29, 34)
TILE = (46, 48, 55)
TILE_FOOT = (37, 39, 45)
FOOTER = (40, 42, 48)
CRIMSON = (204, 28, 48)
CRIMSON_HI = (226, 50, 68)
CRIMSON_FOOT = (168, 18, 36)
CRIMSON_DEEP = (116, 10, 24)
PANEL = (220, 40, 60)       # toasts; 0.8 x this is the pop-up title band
SHEET = (44, 46, 53)        # pop-up menus and dialogs
WHITE = (255, 255, 255)
MUTED = (150, 153, 164)
INK = (16, 16, 20)
ROSE = (255, 96, 112)       # page counter on the dark footer
AMBER = (255, 188, 28)
GOLD = (246, 160, 0)
BLUE = (34, 122, 242)
YELLOW = (255, 176, 0)
GREEN = (24, 172, 84)
TEAL = (10, 164, 176)
PINK = (236, 50, 120)
PURPLE = (140, 80, 232)
ORANGE = (248, 112, 24)
INDIGO = (82, 94, 240)
SLATE = (98, 106, 128)

DISC = {"recent": BLUE, "favorite": YELLOW, "game": GREEN, "emulators": TEAL, "retroarch": PINK,
        "app": PURPLE, "setting": ORANGE}
SYS_DISC = [BLUE, ORANGE, GREEN, PURPLE, TEAL, PINK]
APP_DISC = {"themes": PINK, "pacman": ORANGE, "gameswitcher": PURPLE, "search": BLUE, "gallery": TEAL,
            "activity": GREEN, "retroarch": INDIGO, "tweaks": ORANGE, "download": BLUE, "folder": GOLD,
            "hidden": SLATE, "emulators": TEAL, "category": PINK, "updates": GREEN, "repos": PURPLE}
NO_BADGE = {"xbox", "wii", "segacd", "neogeo"}   # badges that would spell a brand name

LOGO_FONT = "Barlow-BlackItalic.ttf"


# ---- masks and layers (supersampled, coordinates in 1x pixels) ------------------------------

def blank(w, h):
    return Image.new("L", (w * SS, h * SS), 0)


def clear(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def layer(im, color, mask, k=1.0):
    """[im] with [color] painted through [mask]; the colour's alpha and [k] scale it."""
    a = (color[3] / 255 if len(color) > 3 else 1.0) * k
    if a < 1.0:
        mask = mask.point(lambda v: int(round(v * a)))
    c = Image.new("RGBA", im.size, rgba(color))
    c.putalpha(mask)
    return Image.alpha_composite(im, c)


def through(im, src, mask):
    """[src] (RGBA, same size) painted onto [im] through [mask]."""
    s = src.copy()
    s.putalpha(ImageChops.multiply(src.getchannel("A"), mask))
    return Image.alpha_composite(im, s)


def vgrad(w, h, top, bottom, y0=0.0, y1=None):
    """SS-size vertical gradient from [top] at y0 to [bottom] at y1 (1x)."""
    y1 = h if y1 is None else y1
    col = Image.new("RGBA", (1, h * SS))
    for y in range(h * SS):
        t = min(1.0, max(0.0, (y / SS - y0) / max(1e-6, y1 - y0)))
        col.putpixel((0, y), lerp(rgba(top), rgba(bottom), t))
    return col.resize((w * SS, h * SS), Image.NEAREST)


def shift(mask, dx, dy):
    out = Image.new("L", mask.size, 0)
    out.paste(mask, (int(round(S(dx))), int(round(S(dy)))))
    return out


def blur(mask, r):
    return mask.filter(ImageFilter.GaussianBlur(S(r)))


def rr_mask(w, h, box, r):
    m = blank(w, h)
    ImageDraw.Draw(m).rounded_rectangle([S(v) for v in box], radius=S(max(0, r)), fill=255)
    return m


def rect_mask(w, h, box):
    m = blank(w, h)
    ImageDraw.Draw(m).rectangle([S(v) for v in box], fill=255)
    return m


def edge_fade(w, h, d=4.0):
    """1 inside, falling to 0 at the image edges: light and shadow must not end in a hard line."""
    m = rect_mask(w, h, (d, d, w - d, h - d))
    return m.filter(ImageFilter.GaussianBlur(S(d / 2)))


def tone(c, k):
    """Lighter (k > 0, towards white) or darker (k < 0, towards black)."""
    return lerp(c[:3], (255, 255, 255) if k > 0 else (0, 0, 0), abs(k))


class Shape:
    """Draws on an SS-size L mask in 1x coordinates around (cx, cy), scaled by [k]; v=0 cuts."""

    def __init__(self, mask, cx=0.0, cy=0.0, k=1.0):
        self.m, self.d, self.cx, self.cy, self.k = mask, ImageDraw.Draw(mask), cx, cy, k

    def P(self, x, y):
        return S(self.cx + x * self.k), S(self.cy + y * self.k)

    def ci(self, x, y, r, v=255):
        self.d.ellipse([*self.P(x - r, y - r), *self.P(x + r, y + r)], fill=v)

    def rr(self, x0, y0, x1, y1, r, v=255):
        self.d.rounded_rectangle([*self.P(x0, y0), *self.P(x1, y1)], radius=S(r * self.k), fill=v)

    def poly(self, pts, v=255):
        self.d.polygon([self.P(x, y) for x, y in pts], fill=v)

    def ln(self, pts, w, v=255):
        q = [self.P(x, y) for x, y in pts]
        self.d.line(q, fill=v, width=int(round(S(w * self.k))), joint="curve")
        r = S(w * self.k) / 2
        for x, y in q:
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=v)


def star_pts(r0, r1, n=5, rot=-90.0, cx=0.0, cy=0.0):
    pts = []
    for i in range(n * 2):
        r = r0 if i % 2 == 0 else r1
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def gear_pts(r0, r1, teeth=8):
    pts = []
    for i in range(teeth * 4):
        a = math.radians(i * 360 / (teeth * 4) - 90 + 360 / teeth / 8)
        r = r0 if (i % 4) in (1, 2) else r1
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


INVADER = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX",
           "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."]


# ---- the main menu pictures: white silhouettes, details cut through to the disc ----------------

def m_recent(g):
    g.ci(0, 0, 21.5)
    for k in range(12):
        a = math.radians(k * 30)
        r = 1.9 if k % 3 == 0 else 1.1
        g.ci(16.2 * math.cos(a), 16.2 * math.sin(a), r, 0)
    g.ln([(0, -12), (0, 0), (8.5, 5.5)], 3.8, 0)


def m_favorite(g):
    pts = star_pts(23, 11.2, cy=1.5)
    g.poly(pts)
    g.ln(pts + pts[:1], 4.2)


def m_game(g):
    g.rr(-27, -14, 27, 7, 10.5)
    g.ci(-17, 6.5, 10.5)
    g.ci(17, 6.5, 10.5)
    g.ln([(-20.5, -3.5), (-8.5, -3.5)], 4.2, 0)
    g.ln([(-14.5, -9.5), (-14.5, 2.5)], 4.2, 0)
    g.ci(12, -6, 3.3, 0)
    g.ci(19, 0, 3.3, 0)


def m_emulators(g):
    g.rr(-17, -24, 17, 24, 5)
    g.rr(-11.5, -18.5, 11.5, 0.5, 2.5, 0)
    g.ln([(-12.5, 12), (-3, 12)], 3.6, 0)
    g.ln([(-7.75, 7.25), (-7.75, 16.75)], 3.6, 0)
    g.ci(6, 14.5, 2.9, 0)
    g.ci(11.5, 9, 2.9, 0)


def m_expert(g):
    c = 4.5
    x0, y0 = -c * 5.5, -c * 4 + 0.5
    for j, row in enumerate(INVADER):
        for i, ch in enumerate(row):
            if ch == "X":
                g.rr(x0 + i * c - 0.2, y0 + j * c - 0.2, x0 + (i + 1) * c + 0.2, y0 + (j + 1) * c + 0.2, 0.6)


def m_apps(g):
    h, k = 9, 11.5
    g.rr(-k - h, -k - h, -k + h, -k + h, 4.5)
    g.ci(k, -k, h + 0.6)
    g.rr(-k - h, k - h, -k + h, k + h, 4.5)
    g.rr(k - h, k - h, k + h, k + h, 4.5)


def m_setting(g):
    pts = gear_pts(23, 17)
    g.poly(pts)
    g.ln(pts + pts[:1], 2.4)
    g.ci(0, 0, 7.5, 0)


MENU = {"recent": m_recent, "favorite": m_favorite, "game": m_game, "emulators": m_emulators,
        "retroarch": m_expert, "app": m_apps, "setting": m_setting}


def disc_picture(w, h, cx, cy, r, color, glyph, glow=0.55, glow_r=9.0, lift=None, ring=0.0):
    """A [color] disc at (cx, cy) with a soft glow, and the white [glyph] (an SS-size RGBA layer,
    or a function drawing on a Shape) on it with a faint shadow of the disc's own colour."""
    disc = blank(w, h)
    Shape(disc).ci(cx, cy, r)
    out = clear(w, h)
    if lift:
        out = layer(out, (0, 0, 0), blur(shift(disc, 0, lift[0]), lift[1]), lift[2])
    if ring:
        rim = blank(w, h)
        Shape(rim).ci(cx, cy, r + ring)
        out = layer(out, WHITE, rim)
    if glow:
        out = layer(out, color, ImageChops.multiply(blur(disc, glow_r), edge_fade(w, h, 3)), glow)
    out = through(out, vgrad(w, h, tone(color, 0.16), tone(color, -0.1), cy - r, cy + r), disc)
    if callable(glyph):
        gm = blank(w, h)
        glyph(Shape(gm, cx, cy, r / 38))
        g = layer(clear(w, h), WHITE, gm)
    else:
        g = glyph
    ga = g.getchannel("A")
    out = layer(out, tone(color, -0.45), ImageChops.multiply(blur(shift(ga, 0, 1.6), 1.0), disc), 0.55)
    return Image.alpha_composite(out, g)


# ---- system pictures: the shared line drawings, white and zoomed to fit a disc -----------------

class _Pen(Pen):
    """A white Pen drawn [zoom] times its size, its lines kept about 3 px wide on screen."""

    def __init__(self, draw, cx, cy, zoom):
        super().__init__(draw, cx, cy, (255, 255, 255, 255), SS * zoom)
        self.zoom = zoom

    def _w(self, w):
        w = self.w if w is None else w
        px = min(max(w * self.zoom * 1.3, 1.7), w * 1.15)
        return max(1, int(round(px * SS)))


def _render(sid, x, y, zoom):
    """SS-size white RGBA of system [sid]'s drawing, its own (0, 0) at (x, y)."""
    im = clear(120, 130)
    (GLYPHS.get(sid) or GLYPHS["fallback"])(_Pen(ImageDraw.Draw(im), x / zoom, y / zoom, zoom))
    # (pixels a drawing paints dark, like android's eyes, are holes)
    r, _, _, a = im.split()
    im.putalpha(ImageChops.multiply(a, r))
    return im


_FIT = {}


def _fit(sid):
    """(gx, gy, reach): the drawing's centre and the farthest it reaches from it, at zoom 1."""
    if sid not in _FIT:
        a = finish(_render(sid, 60, 65, 1.0)).getchannel("A").point(lambda v: 255 if v > 90 else 0)
        x0, y0, x1, y1 = a.getbbox()
        gx, gy = (x0 + x1) / 2, (y0 + y1) / 2
        px = a.load()
        reach = 1.0
        for y in range(y0, y1):
            for x in range(x0, x1):
                if px[x, y]:
                    reach = max(reach, math.hypot(x + 0.5 - gx, y + 0.5 - gy))
        _FIT[sid] = (gx - 60, gy - 65, reach)
    return _FIT[sid]


class Theme(Style):
    name = "Crimson"
    author = "MainUI"
    description = "Punchy flat dark: charcoal, a solid crimson header, bright glowing colour discs and heavy italic type."

    bg_top, bg_bottom = CHAR_TOP, CHAR
    accent = CRIMSON
    accent2 = CRIMSON_FOOT
    highlight = ROSE
    text = WHITE
    muted = MUTED
    glyph_n = WHITE
    glyph_f = WHITE
    panel = PANEL
    panel_alpha = 250
    bar = FOOTER

    font_file = "Barlow-ExtraBoldItalic.ttf"
    font_license = "OFL-Barlow.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 28, 27, 24, 24, 17, 18

    icon_quant = 64
    sel_icons = True    # focused: the disc in a white ring, as on the main menu

    # ---- big pictures ---------------------------------------------------------------------
    def background(self, w=640, h=480):
        bayer = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(h):
            t = y / (h - 1)
            base = [CHAR_TOP[i] + (CHAR[i] - CHAR_TOP[i]) * t for i in range(3)]
            for x in range(w):
                dith = (bayer[(y & 3) * 4 + (x & 3)] + 0.5) / 16
                px[x, y] = tuple(int(base[i] + dith) for i in range(3))
        return im.convert("RGBA")

    def header_bar(self):
        w, h = 640, 60
        im = vgrad(w, h, CRIMSON_HI, CRIMSON, 0, 56)
        im = layer(im, WHITE, rect_mask(w, h, (0, 0, w, 1)), 0.18)
        im = layer(im, CRIMSON_DEEP, rect_mask(w, h, (0, 57, w, 60)))
        return finish(im)

    def footer_bar(self):
        w, h = 640, 60
        im = Image.new("RGBA", (w * SS, h * SS), rgba(FOOTER))
        im = layer(im, INK, rect_mask(w, h, (0, 0, w, 2.5)))
        im = layer(im, WHITE, rect_mask(w, h, (0, 2.5, w, 3.5)), 0.05)
        return finish(im)

    def logo(self):
        w, h = 190, 46
        im = clear(w, h)
        f = self.font(35, LOGO_FONT)
        m = blank(w, h)
        g = Shape(m)
        for i, (y0, ln) in enumerate(((12, 14), (20, 11), (28, 8))):
            x1 = 21 - i * 1.8
            g.poly([(x1 - ln + 2.2, y0), (x1 + 2.2, y0), (x1 - 0.2, y0 + 5.2), (x1 - ln - 0.2, y0 + 5.2)])
        ImageDraw.Draw(m).text((S(28), S(23)), "CRIMSON", font=f, fill=255, anchor="lm")
        im = layer(im, CRIMSON_DEEP, shift(m, 2, 1.8), 0.8)
        return finish(layer(im, WHITE, m))

    # ---- lists --------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        box = (6, 3, w - 6, h - 3)
        m = rr_mask(w, h, box, 8)
        im = through(clear(w, h), vgrad(w, h, CRIMSON_HI, CRIMSON, 3, h - 3), m)
        im = layer(im, CRIMSON_FOOT, ImageChops.multiply(m, rect_mask(w, h, (0, h - 6, w, h))))
        return finish(im)

    def divider(self):
        w, h = 640, 4
        im = clear(w, h)
        im = layer(im, INK, rect_mask(w, h, (14, 1, w - 14, 2)), 0.7)
        im = layer(im, WHITE, rect_mask(w, h, (14, 2, w - 14, 3)), 0.05)
        return finish(im)

    # ---- tiles --------------------------------------------------------------------------
    def slab(self, w, h, box, r, focused, foot):
        """A flat rounded tile with a darker band from y [foot] down."""
        m = rr_mask(w, h, box, r)
        fill, band = (CRIMSON, CRIMSON_FOOT) if focused else (TILE, TILE_FOOT)
        im = layer(clear(w, h), fill, m)
        if foot < h:
            im = layer(im, band, ImageChops.multiply(m, rect_mask(w, h, (0, foot, w, h))))
        top = ImageChops.subtract(m, shift(m, 0, 1.2))
        im = layer(im, WHITE, top, 0.22 if focused else 0.06)
        return im

    def card(self, w, h, focused):
        return finish(self.slab(w, h, (5, 5, w - 5, h - 5), 10, focused, h - 38))

    def tile_base(self, focused):
        return finish(self.slab(156, 278, (8, 6, 148, 272), 12, focused, 238))

    def tile_glyph(self, key, focused):
        col = DISC[key]
        if focused:
            return finish(disc_picture(156, 278, 78, 110, 41, col, MENU[key], 0, 0, (3, 5, 0.4), 2.5))
        return finish(disc_picture(156, 278, 78, 110, 41, col, MENU[key], 0.7, 11))

    def home_tile(self, key, focused):
        base = self.tile_base(focused)
        return Image.alpha_composite(base, self.tile_glyph(key, focused)) if key else base

    def preview_frame(self):
        return finish(self.slab(250, 360, (2, 2, 248, 358), 12, False, 400))

    def key(self, focused):
        w, h = 52, 40
        m = rr_mask(w, h, (1, 1, w - 1, h - 1), 7)
        im = layer(clear(w, h), CRIMSON if focused else TILE, m)
        im = layer(im, CRIMSON_FOOT if focused else TILE_FOOT, ImageChops.multiply(m, rect_mask(w, h, (0, h - 6, w, h))))
        return finish(im)

    def input_box(self):
        w, h = 560, 60
        return finish(layer(clear(w, h), WHITE, rr_mask(w, h, (2, 3, w - 2, h - 3), 9)))

    # ---- buttons and small parts ----------------------------------------------------------
    def button(self, label, primary):
        # A / B at their own size, X / Y scaled to 44 high: the same 38 px key in both
        n = 38
        w, h = n + 4, (n + 4 if label in "AB" else 44)
        im = clear(w, h)
        x0, y0 = 2, (h - n) / 2
        m = rr_mask(w, h, (x0, y0, x0 + n, y0 + n), 6.5)
        im = through(im, vgrad(w, h, CRIMSON_HI, CRIMSON, y0, y0 + n), m)
        im = layer(im, CRIMSON_FOOT, ImageChops.multiply(m, rect_mask(w, h, (0, y0 + n - 4, w, h))))
        d = ImageDraw.Draw(im)
        d.text((S(x0 + n / 2 + 0.5), S(h / 2)), label, font=self.font(30, LOGO_FONT), fill=rgba(WHITE), anchor="mm")
        return finish(im)

    def pill(self, label, w, h=44):
        f = self.font(15)
        d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
        tw = d0.textlength(label, font=f) / SS
        w = int(math.ceil(tw + 26))
        im = clear(w, h)
        m = rr_mask(w, h, (2, h / 2 - 14, w - 2, h / 2 + 14), 6)
        im = layer(im, CRIMSON, m)
        im = layer(im, CRIMSON_FOOT, ImageChops.multiply(m, rect_mask(w, h, (0, h / 2 + 10, w, h))))
        ImageDraw.Draw(im).text((S(w / 2 + 0.5), S(h / 2)), label, font=f, fill=rgba(WHITE), anchor="mm")
        return finish(im)

    def dot(self, active):
        w, h = 22, 12
        im = clear(w, h)
        if active:
            g = Shape(blank(w, h))
            g.poly([(5, 2.5), (19.5, 2.5), (17, 9.5), (2.5, 9.5)])
            im = layer(im, WHITE, g.m)
        else:
            m = blank(w, h)
            Shape(m).ci(11, 6, 3.4)
            im = layer(im, (92, 95, 106), m)
        return finish(im)

    def toggle(self, on):
        w, h = 92, 44
        im = clear(w, h)
        x0, x1, y0, y1 = 30, 84, 8, 36
        r = (y1 - y0) / 2
        track = rr_mask(w, h, (x0, y0, x1, y1), r)
        knob = blank(w, h)
        cx = x1 - r if on else x0 + r
        Shape(knob).ci(cx, h / 2, r - 4)
        im = layer(im, CRIMSON if on else (72, 75, 85), track)
        im = layer(im, (0, 0, 0), blur(shift(knob, 0, 1.2), 1.2), 0.35)
        return finish(layer(im, WHITE if on else (170, 173, 182), knob))

    def arrow(self, left, size=24):
        im = clear(size, size)
        m = blank(size, size)
        k = size * 0.22
        c = size / 2
        sx = -1 if left else 1
        Shape(m).ln([(c - sx * k * 0.55, c - k), (c + sx * k * 0.6, c), (c - sx * k * 0.55, c + k)], size * 0.15)
        return finish(layer(im, WHITE, m))

    def panel_image(self, w, h):
        if w >= 600:  # dialog: a dark sheet with a crimson top rule
            box = (24, 6, w - 24, h - 6)
            m = rr_mask(w, h, box, 14)
            im = layer(clear(w, h), (0, 0, 0), ImageChops.multiply(blur(shift(m, 0, 4), 6), edge_fade(w, h, 3)), 0.5)
            im = layer(im, SHEET, m)
            return finish(layer(im, CRIMSON, ImageChops.multiply(m, rect_mask(w, h, (0, 0, w, box[1] + 6)))))
        # pop-up menus hang under MainUI's square crimson title band: square top, rounded bottom
        im = clear(w, h)
        m = rr_mask(w, h, (0, -20, w, h), 12)
        im = layer(im, SHEET, m)
        return finish(layer(im, CRIMSON_FOOT, rect_mask(w, h, (0, 0, w, 3))))

    def folder_icon(self):
        w = h = 60
        back, front = blank(w, h), blank(w, h)
        Shape(back).rr(9, 14, 30, 26, 3.5)
        Shape(back).rr(9, 19, 51, 46, 4)
        Shape(front).rr(9, 24, 51, 46, 4)
        im = layer(clear(w, h), GOLD, back)
        return finish(layer(im, AMBER, front))

    def favorite_mark(self):
        w, h = 34, 39
        m = blank(w, h)
        g = Shape(m, 17, 20)
        pts = star_pts(12.5, 6, cy=0.5)
        g.poly(pts)
        g.ln(pts + pts[:1], 2.4)
        return finish(layer(clear(w, h), AMBER, m))

    def battery(self, level, charging=False):
        w = h = 48
        im = clear(w, h)
        body = rr_mask(w, h, (6, 15, 40, 33), 4.5)
        hole = rr_mask(w, h, (8.6, 17.6, 37.4, 30.4), 2.4)
        im = layer(im, WHITE, ImageChops.subtract(body, hole))
        im = layer(im, WHITE, rr_mask(w, h, (40.5, 20.5, 44, 27.5), 1.5))
        if level > 0:
            col = AMBER if level <= 0.2 else WHITE
            im = layer(im, col, rr_mask(w, h, (10.5, 19.5, 10.5 + 25 * level, 28.5), 1.5))
        if charging:
            bolt = blank(w, h)
            pts = [(26, 9), (16, 26), (23, 26), (20.5, 39), (31, 21.5), (24, 21.5)]
            g = Shape(bolt)
            g.poly(pts)
            edge = blank(w, h)
            Shape(edge).poly(pts)
            Shape(edge).ln(pts + pts[:1], 3.2)
            im = layer(im, CRIMSON_DEEP, edge)
            im = layer(im, AMBER, bolt)
        return finish(im)

    # ---- system and app icons -----------------------------------------------------------
    _order = None

    def disc_color(self, sid):
        if Theme._order is None:
            Theme._order = {s: i for i, s in enumerate(system_ids())}
        return SYS_DISC[Theme._order.get(sid, len(sid)) % len(SYS_DISC)]

    def icon_picture(self, sid, selected, cy):
        r = 48
        gx, gy, reach = _fit(sid)
        zoom = min(0.9, (r - 7) / reach)
        g = _render(sid, 60 - gx * zoom, cy - gy * zoom, zoom)
        if selected:
            return disc_picture(120, 130, 60, cy, r, self.disc_color(sid), g, 0, 0, (2, 3, 0.4), 2.5)
        return disc_picture(120, 130, 60, cy, r, self.disc_color(sid), g, 0.45, 6)

    def badge(self, label, selected):
        w, h = 120, 130
        im = clear(w, h)
        f = self.font(13.5)
        d = ImageDraw.Draw(im)
        tw = d.textlength(label, font=f) / SS
        bw = min(112, tw + 18)
        x0, x1, y0, y1, k = 60 - bw / 2, 60 + bw / 2, 101, 121, 3.5
        m = blank(w, h)
        g = Shape(m)
        pts = [(x0 + k, y0), (x1 + k, y0), (x1 - k, y1), (x0 - k, y1)]
        g.poly(pts)
        g.ln(pts + pts[:1], 1.6)
        im = layer(im, (0, 0, 0), blur(shift(m, 0, 1.5), 1.5), 0.4)
        im = layer(im, INK, m)
        ImageDraw.Draw(im).text((S(60.5), S(111.5)), label, font=f, fill=rgba(WHITE), anchor="mm")
        return im

    def system_icon(self, sid, selected):
        label = None if sid in NO_BADGE else BADGES.get(sid, sid[:7].upper())
        out = self.icon_picture(sid, selected, 55 if label else 63)
        if label:
            out = Image.alpha_composite(out, self.badge(label, selected))
        return finish(out)

    def app_icon(self, key):
        n = 96
        g = clear(n, n)
        APPS[key](ImageDraw.Draw(g), n / 2, n / 2, n * 0.235, rgba(WHITE), 5.2)
        return finish(disc_picture(n, n, n / 2, n / 2, 37, APP_DISC.get(key, BLUE), g, 0.5, 5))

    # ---- sound and config -----------------------------------------------------------------
    def sound(self, path):
        """A short, bright tick with a fast fade (no click at the end)."""
        rate, length = 22050, 0.032
        frames = bytearray()
        for i in range(int(rate * length)):
            t = i / rate
            env = min(1.0, t / 0.0015, (length - t) / 0.003) * math.exp(-t * 170)
            s = 0.75 * math.sin(2 * math.pi * 1480 * t) + 0.25 * math.sin(2 * math.pi * 2960 * t)
            frames += struct.pack("<h", int(8600 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["mainui"] = {"accent": hexc(CRIMSON), "panel": hexa(PANEL, self.panel_alpha), "background": hexc(CHAR)}
        return cfg
