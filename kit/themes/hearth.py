"""Hearth: calm, cosy dark. Warm charcoal, thin outlined cards, a lighter raised card for focus
and softly shaded full-colour objects."""
import math
import struct
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, BADGES, GLYPHS, SS, Pen, S, Style, finish, hexa, hexc, lerp, rgba, system_ids

# ---- palette ------------------------------------------------------------------------------
BG_TOP = (56, 53, 50)
BG_BOT = (43, 41, 39)
BAR = (37, 35, 33)
LINE_DARK = (24, 23, 22)
CARD = (122, 117, 111)        # the focused card (white text on it: 4.7:1)
CARD_LOW = (104, 100, 95)
OUTLINE = (255, 250, 240)
SHEET = (64, 61, 58)          # pop-ups; MainUI's title band is 0.8 x the panel colour
SEL = (106, 101, 96)          # list selection
TEXT = (244, 239, 231)
SUBTLE = (212, 206, 198)      # hints, unfocused menu labels
MUTED = (182, 176, 168)       # unfocused grid labels
KEYCAP = (200, 194, 186)      # hint discs and pills
KEYINK = (44, 41, 39)
COPPER = (178, 102, 50)       # MainUI's accent (white text on it)
HONEY = (244, 196, 70)        # the active page dot, toggles
WHITE = (255, 255, 255)
CHARCOAL = (56, 52, 50)

MUSTARD = (232, 172, 60)
CREAMY = (248, 243, 234)
BRICK = (212, 72, 64)
GOLD = (236, 188, 86)
SNOW = (250, 248, 244)
TEALC = (72, 166, 164)
CORAL = (226, 98, 96)
PLUM = (150, 108, 212)
BLUEC = (82, 140, 208)
GREENC = (92, 172, 102)
REDC = (216, 86, 78)
YELLOWC = (234, 182, 58)
STEEL = (190, 186, 180)

# system pictures: pastel bodies, in systems.json order
BODY = [(166, 194, 222), (236, 206, 140), (176, 200, 166), (230, 178, 166), (198, 184, 228), (238, 230, 214),
        (156, 206, 196), (204, 198, 190)]
GLASS_TOP, GLASS_BOT = (74, 88, 96), (38, 46, 52)
NO_BADGE = {"xbox", "wii", "segacd", "neogeo"}   # badges that would spell a brand name
APP_TILE = {"themes": CORAL, "pacman": (214, 150, 52), "gameswitcher": TEALC, "search": BLUEC, "gallery": GREENC,
            "activity": (206, 102, 132), "retroarch": PLUM, "tweaks": (132, 126, 120), "download": BLUEC,
            "folder": (214, 150, 52), "hidden": (124, 118, 112), "emulators": TEALC, "category": CORAL,
            "updates": GREENC, "repos": PLUM}

LIST_FONT = "BeVietnamPro-Regular.ttf"


# ---- masks and layers (supersampled, coordinates in 1x pixels) ------------------------------

def blank(w, h):
    return Image.new("L", (w * SS, h * SS), 0)


def clear(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def layer(im, color, mask, k=1.0):
    a = (color[3] / 255 if len(color) > 3 else 1.0) * k
    if a < 1.0:
        mask = mask.point(lambda v: int(round(v * a)))
    c = Image.new("RGBA", im.size, rgba(color))
    c.putalpha(mask)
    return Image.alpha_composite(im, c)


def through(im, src, mask):
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


def ring_mask(w, h, box, r, width):
    return ImageChops.subtract(rr_mask(w, h, box, r), rr_mask(w, h, (box[0] + width, box[1] + width, box[2] - width,
                                                                     box[3] - width), max(0, r - width)))


def edge_fade(w, h, d=4.0):
    """1 inside, falling to 0 at the image edges: light and shadow must not end in a hard line."""
    m = rect_mask(w, h, (d, d, w - d, h - d))
    return m.filter(ImageFilter.GaussianBlur(S(d / 2)))


def tone(c, k):
    return lerp(c[:3], (255, 255, 255) if k > 0 else (0, 0, 0), abs(k))


def bbox_y(mask):
    b = mask.getbbox()
    return (b[1] / SS, b[3] / SS) if b else (0, 1)


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
        self.d.line(q, fill=v, width=max(1, int(round(S(w * self.k)))), joint="curve")
        r = S(w * self.k) / 2
        for x, y in q:
            self.d.ellipse([x - r, y - r, x + r, y + r], fill=v)

    def rpoly(self, pts, round_=3.0, v=255):
        """A polygon with its corners rounded (grown by [round_] / 2)."""
        self.poly(pts, v)
        self.ln(pts + pts[:1], round_, v)


class Obj:
    """A softly shaded object on a w x h SS canvas; parts are added back to front."""

    def __init__(self, w, h, cx, cy, k=1.0):
        self.w, self.h, self.cx, self.cy, self.k = w, h, cx, cy, k
        self.im = clear(w, h)
        self.all = blank(w, h)

    def mask(self, fn):
        m = blank(self.w, self.h)
        fn(Shape(m, self.cx, self.cy, self.k))
        return m

    def shaded(self, m, base, light=0.2, dark=0.16, hi=0.4, lo=0.22, y=None):
        y0, y1 = y or bbox_y(m)
        self.im = through(self.im, vgrad(self.w, self.h, tone(base, light), tone(base, -dark), y0, y1), m)
        rim = ImageChops.subtract(m, shift(m, 0, 1.7 * self.k))
        self.im = layer(self.im, WHITE, ImageChops.multiply(blur(rim, 0.7), m), hi)
        foot = ImageChops.subtract(m, shift(m, 0, -2.6 * self.k))
        self.im = layer(self.im, (0, 0, 0), ImageChops.multiply(blur(foot, 1.6), m), lo)
        self.all = ImageChops.lighter(self.all, m)

    def flat(self, m, color, k=1.0):
        self.im = layer(self.im, color, m, k)

    def inset(self, m, k=0.35, dy=1.6):
        """A soft shadow inside [m] along its top edge (something set into the surface)."""
        e = ImageChops.subtract(m, shift(m, 0, dy * self.k))
        self.im = layer(self.im, (0, 0, 0), ImageChops.multiply(blur(e, 1.2), m), k)

    def done(self, drop=(3.5, 3.5, 0.5)):
        dy, r, a = drop
        sh = blur(shift(self.all, 0, dy * self.k), r)
        out = layer(clear(self.w, self.h), (0, 0, 0), sh, a)
        return Image.alpha_composite(out, self.im)


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


# ---- the main menu objects ------------------------------------------------------------------

def o_recent(o):
    rim = o.mask(lambda g: g.ci(0, 0, 34))
    o.shaded(rim, MUSTARD, 0.22, 0.2)
    face = o.mask(lambda g: g.ci(0, 0, 27))
    o.shaded(face, CREAMY, 0.0, 0.1, 0.0, 0.0)
    o.inset(face, 0.32, 3.2)
    ticks = o.mask(lambda g: [g.ci(21.5 * math.cos(math.radians(a)), 21.5 * math.sin(math.radians(a)), 2.0 if a % 90 == 0 else 1.2)
                              for a in range(0, 360, 30)])
    o.flat(ticks, (120, 112, 106))

    def hands(g):
        a, b = math.radians(-150), math.radians(-30)
        g.ln([(0, 0), (12 * math.cos(a), 12 * math.sin(a))], 4.4)
        g.ln([(0, 0), (18.5 * math.cos(b), 18.5 * math.sin(b))], 3.2)
    hm = o.mask(hands)
    o.flat(blur(shift(hm, 0.8, 1.6), 0.9), (0, 0, 0), 0.25)
    o.flat(hm, CHARCOAL)
    sec = o.mask(lambda g: g.ln([(-4 * 0.5, -4 * 0.87), (10, 17.3)], 1.5))
    o.flat(sec, CORAL)
    cap = o.mask(lambda g: g.ci(0, 0, 3.2))
    o.shaded(cap, CORAL, 0.2, 0.1, 0.3, 0.1)


def o_favorite(o):
    banner_pts = [(-24, -30), (24, -30), (24, 37), (0, 23), (-24, 37)]
    banner = o.mask(lambda g: g.rpoly(banner_pts, 2.5))
    o.shaded(banner, BRICK, 0.12, 0.18, 0.0, 0.25)
    left = o.mask(lambda g: g.rr(-27, -40, 0, 40, 0))
    o.flat(ImageChops.multiply(banner, left), WHITE, 0.07)
    under = o.mask(lambda g: g.rr(-30, -32, 30, -27, 0))
    o.flat(ImageChops.multiply(blur(under, 2.0), banner), (60, 10, 10), 0.6)
    star = o.mask(lambda g: g.rpoly(star_pts(15.5, 7.2, cy=1), 2.4))
    o.flat(blur(shift(star, 0, 1.6), 1.2), (90, 16, 16), 0.55)
    o.shaded(star, CREAMY, 0.0, 0.12, 0.25, 0.12)
    rod = o.mask(lambda g: (g.rr(-31, -38, 31, -30, 4), g.ci(-32, -34, 5.5), g.ci(32, -34, 5.5)))
    o.shaded(rod, GOLD, 0.25, 0.2, 0.55, 0.2)


def o_game(o):
    body = o.mask(lambda g: (g.rr(-38, -20, 38, 9, 15), g.ci(-25, 9, 15), g.ci(25, 9, 15)))
    o.shaded(body, SNOW, 0.0, 0.2, 0.0, 0.3)
    pad = o.mask(lambda g: (g.rr(-31, -7.6, -13, -0.4, 1.8), g.rr(-25.6, -13, -18.4, 5.6, 1.8)))
    o.flat(shift(pad, 0, 1.4), WHITE, 0.9)
    o.shaded(pad, CHARCOAL, 0.12, 0.1, 0.15, 0.1)
    for (x, y), c in (((23, -11), YELLOWC), ((30.5, -3.8), REDC), ((23, 3.4), GREENC), ((15.5, -3.8), BLUEC)):
        b = o.mask(lambda g, x=x, y=y: g.ci(x, y, 4.2))
        o.flat(shift(b, 0, 1.2), WHITE, 0.9)
        o.shaded(b, c, 0.2, 0.15, 0.45, 0.15)
    pills = o.mask(lambda g: (g.rr(-8.5, -12, -2.5, -9, 1.5), g.rr(2.5, -12, 8.5, -9, 1.5)))
    o.flat(pills, (150, 145, 140))


def o_emulators(o):
    body = o.mask(lambda g: g.rr(-24, -36, 24, 36, 8))
    o.shaded(body, TEALC, 0.2, 0.18)
    bezel = o.mask(lambda g: g.rr(-17.5, -29.5, 17.5, -2, 4))
    o.shaded(bezel, (66, 64, 70), 0.1, 0.1, 0.0, 0.0)
    o.inset(bezel, 0.4, 1.6)
    scr = o.mask(lambda g: g.rr(-12.5, -25, 12.5, -7, 1.5))
    o.shaded(scr, (156, 192, 112), 0.08, 0.16, 0.0, 0.0)
    sheen = o.mask(lambda g: g.poly([(-12.5, -25), (-2, -25), (-12.5, -12)]))
    o.flat(ImageChops.multiply(sheen, scr), WHITE, 0.18)
    pad = o.mask(lambda g: (g.rr(-18, 11.2, -3, 16.8, 1.5), g.rr(-13.3, 6.5, -7.7, 21.5, 1.5)))
    o.flat(shift(pad, 0, 1.2), WHITE, 0.25)
    o.shaded(pad, CHARCOAL, 0.12, 0.1, 0.15, 0.1)
    for x, y in ((9, 17), (16.5, 11)):
        b = o.mask(lambda g, x=x, y=y: g.ci(x, y, 4.4))
        o.flat(shift(b, 0, 1.2), WHITE, 0.25)
        o.shaded(b, CORAL, 0.2, 0.15, 0.45, 0.15)
    grille = o.mask(lambda g: [g.ln([(6 + i * 4.5, 31), (11 + i * 4.5, 25)], 1.8) for i in range(3)])
    o.flat(grille, tone(TEALC, -0.4))


def o_expert(o):
    c = 6.4
    x0, y0 = -c * 5.5, -c * 4

    def inv(g):
        for j, row in enumerate(INVADER):
            for i, ch in enumerate(row):
                if ch == "X":
                    g.rr(x0 + i * c - 0.15, y0 + j * c - 0.15, x0 + (i + 1) * c + 0.15, y0 + (j + 1) * c + 0.15, 0.8)
    m = o.mask(inv)
    o.shaded(m, PLUM, 0.25, 0.2, 0.45, 0.3)


def o_apps(o):
    parts = [(lambda g: g.rr(-32, -32, -5, -5, 7), BLUEC), (lambda g: g.ci(18.5, -18.5, 14), GREENC),
             (lambda g: g.rpoly([(-18.5, 6), (-5.5, 30), (-31.5, 30)], 4.5), REDC),
             (lambda g: g.rr(5, 5, 32, 32, 7), YELLOWC)]
    for fn, c in parts:
        m = o.mask(fn)
        o.shaded(m, c, 0.22, 0.18, 0.45, 0.25)


def o_setting(o):
    gear = o.mask(lambda g: g.rpoly(gear_pts(36, 27.5), 3.2))
    o.shaded(gear, STEEL, 0.32, 0.34, 0.55, 0.35)
    edge = ImageChops.subtract(gear, gear.filter(ImageFilter.MinFilter(5)))
    o.flat(edge, (70, 66, 62), 0.45)
    hub = o.mask(lambda g: g.ci(0, 0, 17))
    o.flat(blur(shift(hub, 0, 1.5), 1.2), (0, 0, 0), 0.3)
    o.shaded(hub, STEEL, 0.32, 0.12, 0.55, 0.2)
    hole = o.mask(lambda g: g.ci(0, 0, 8))
    lip = o.mask(lambda g: g.ci(0, 0, 10.5))
    o.flat(ImageChops.subtract(lip, shift(lip, 0, 1.4)), (0, 0, 0), 0.25)
    o.im.putalpha(ImageChops.subtract(o.im.getchannel("A"), hole))
    o.all = ImageChops.subtract(o.all, hole)


MENU = {"recent": o_recent, "favorite": o_favorite, "game": o_game, "emulators": o_emulators,
        "retroarch": o_expert, "app": o_apps, "setting": o_setting}


# ---- system pictures: the shared line drawings as small shaded objects -------------------------

class _Pen(Pen):
    """Lines to the draw layer, soft fills to their own mask; drawn [zoom] times its size."""

    def __init__(self, draw, soft_draw, cx, cy, zoom):
        super().__init__(draw, cx, cy, (255, 255, 255, 255), SS * zoom)
        self.sd, self.zoom = soft_draw, zoom

    def _w(self, w):
        w = self.w if w is None else w
        px = min(max(w * self.zoom, 1.5), w)
        return max(1, int(round(px * SS)))

    def rr(self, x0, y0, x1, y1, r=3, w=None, fill=False, soft=False):
        if soft and not fill:
            rad = min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2) * self.ss
            self.sd.rounded_rectangle([*self.p(x0, y0), *self.p(x1, y1)], radius=rad, fill=255)
        super().rr(x0, y0, x1, y1, r, w, fill)

    def poly(self, pts, w=None, fill=False, soft=False):
        if soft and not fill:
            self.sd.polygon([self.p(x, y) for x, y in pts], fill=255)
        super().poly(pts, w, fill)

    def ci(self, x, y, r, w=None, fill=False, soft=False):
        if soft and not fill:
            self.sd.ellipse([*self.p(x - r, y - r), *self.p(x + r, y + r)], fill=255)
        super().ci(x, y, r, w, fill)

    def el(self, x0, y0, x1, y1, w=None, fill=False, soft=False):
        if soft and not fill:
            self.sd.ellipse([*self.p(x0, y0), *self.p(x1, y1)], fill=255)
        super().el(x0, y0, x1, y1, w, fill)


def _render(sid, x, y, zoom):
    """(lines, dark, soft): SS-size masks of system [sid]'s drawing with its (0, 0) at (x, y)."""
    im, soft = clear(120, 130), blank(120, 130)
    (GLYPHS.get(sid) or GLYPHS["fallback"])(_Pen(ImageDraw.Draw(im), ImageDraw.Draw(soft), x / zoom, y / zoom, zoom))
    r, _, _, a = im.split()
    lines = ImageChops.multiply(a, r)
    return lines, ImageChops.subtract(a, lines), soft


def _enclosed(walls):
    """What [walls] (SS-size L) close in completely, found at 1x: SS-size L."""
    w, h = walls.width // SS, walls.height // SS
    wall = walls.resize((w, h), Image.BOX).point(lambda v: 255 if v > 50 else 0)
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(wall, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    inside = pad.crop((1, 1, w + 1, h + 1)).point(lambda v: 255 if v == 0 else 0)
    # (grown a pixel, under the lines, so no gap shows between fill and line)
    return inside.filter(ImageFilter.MaxFilter(3)).resize(walls.size, Image.BILINEAR)


def _solid(lines):
    """The parts of a drawing thicker than its lines (filled shapes), shrunk to leave an outline."""
    m = lines.resize((lines.width // SS, lines.height // SS), Image.BOX).point(lambda v: 255 if v > 128 else 0)
    core = m.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(3))
    return core.resize(lines.size, Image.BILINEAR)


def _area(m):
    return sum(i * n for i, n in enumerate(m.histogram())) / 255


_FIT = {}


def _fit(sid):
    """(gx, gy, w, h): the drawing's centre offset and size at zoom 1."""
    if sid not in _FIT:
        lines, dark, soft = _render(sid, 60, 65, 1.0)
        a = finish(Image.merge("RGBA", (lines, lines, lines, ImageChops.lighter(ImageChops.lighter(lines, dark), soft))))
        x0, y0, x1, y1 = a.getchannel("A").point(lambda v: 255 if v > 90 else 0).getbbox()
        _FIT[sid] = ((x0 + x1) / 2 - 60, (y0 + y1) / 2 - 65, x1 - x0, y1 - y0)
    return _FIT[sid]


def system_object(sid, cx, cy, base, maxw=108, maxh=88):
    gx, gy, gw, gh = _fit(sid)
    zoom = min(1.08, maxw / gw, maxh / gh)
    lines, dark, soft = _render(sid, cx - gx * zoom, cy - gy * zoom, zoom)
    w, h = 120, 130
    inside = _enclosed(lines)
    core = _solid(lines)
    filled = ImageChops.lighter(ImageChops.lighter(inside, core), soft)
    body = ImageChops.lighter(filled, lines)
    bare = _area(ImageChops.subtract(filled, lines)) < 0.18 * _area(body)
    if bare:  # a drawing of bare lines: the lines themselves are the object, a little bolder
        body = ImageChops.lighter(body, lines.filter(ImageFilter.MaxFilter(5)))
    o = Obj(w, h, 0, 0)
    o.shaded(body, base, 0.26, 0.2, 0.5, 0.28)
    if not bare:
        y0, y1 = bbox_y(soft)
        o.im = through(o.im, vgrad(w, h, GLASS_TOP, GLASS_BOT, y0, y1), soft)
        sheen = blank(w, h)
        ImageDraw.Draw(sheen).polygon([(0, S(y0)), (S(w), S(y0 - w * 0.55)), (S(w), S(y0 - w * 0.55 + 14)),
                                       (0, S(y0 + 14))], fill=255)
        o.flat(ImageChops.multiply(sheen, soft), WHITE, 0.1)
        # lines away from any filled area (antennas, cables) stay in the body colour: ink would vanish
        near = filled.resize((w, h), Image.BOX).point(lambda v: 255 if v > 100 else 0).filter(ImageFilter.MaxFilter(5))
        ink = ImageChops.multiply(ImageChops.subtract(lines, core), near.resize(lines.size, Image.BILINEAR))
        o.flat(ImageChops.lighter(ink, dark), tone(base, -0.66))
    else:
        o.flat(dark, tone(base, -0.66))
    return o.done((2.5, 2.4, 0.55))


class Theme(Style):
    name = "Hearth"
    author = "MainUI"
    description = "Calm, cosy dark: warm charcoal, outlined cards, a raised grey card for focus and softly shaded full-colour pictures."

    bg_top, bg_bottom = BG_TOP, BG_BOT
    accent = COPPER
    accent2 = KEYCAP
    highlight = HONEY
    text = TEXT
    muted = MUTED
    glyph_n = SUBTLE
    glyph_f = TEXT
    panel = (80, 76, 72)       # toasts; 0.8 x this is the pop-up title band (= SHEET)
    panel_alpha = 250
    bar = BAR

    font_file = "BeVietnamPro-Medium.ttf"
    font_license = "OFL-BeVietnamPro.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 24, 20, 22, 22, 15, 16

    icon_quant = 96

    # ---- big pictures ---------------------------------------------------------------------
    def background(self, w=640, h=480):
        bayer = (0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5)
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(h):
            for x in range(w):
                # light falls from the top centre
                t = min(1.0, math.hypot((x - w / 2) / w * 1.1, y / h * 0.95))
                dith = (bayer[(y & 3) * 4 + (x & 3)] + 0.5) / 16
                px[x, y] = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t + dith) for i in range(3))
        return im.convert("RGBA")

    def header_bar(self):
        w, h = 640, 60
        im = Image.new("RGBA", (w * SS, h * SS), rgba(BAR))
        im = layer(im, LINE_DARK, rect_mask(w, h, (0, h - 2, w, h - 1)))
        im = layer(im, WHITE, rect_mask(w, h, (0, h - 1, w, h)), 0.06)
        return finish(im)

    def footer_bar(self):
        w, h = 640, 60
        im = Image.new("RGBA", (w * SS, h * SS), rgba(BAR))
        im = layer(im, LINE_DARK, rect_mask(w, h, (0, 0, w, 1)))
        im = layer(im, WHITE, rect_mask(w, h, (0, 1, w, 2)), 0.05)
        return finish(im)

    def logo(self):
        w, h = 150, 42
        o = Obj(w, h, 15, 21)
        brick = o.mask(lambda g: g.rr(-10.5, -10, 10.5, 12, 1.5))
        o.shaded(brick, BRICK, 0.15, 0.2, 0.3, 0.2)
        hole = o.mask(lambda g: (g.rr(-6.5, -1, 6.5, 12, 0), g.ci(0, -1, 6.5)))
        o.flat(hole, (38, 22, 20))
        flame = o.mask(lambda g: (g.ci(0, 7.4, 4.4), g.poly([(-4.3, 6.4), (0.6, -4.5), (4.3, 6.4)])))
        o.im = through(o.im, vgrad(w, h, (255, 214, 96), (240, 104, 36), 17, 32), flame)
        core = o.mask(lambda g: (g.ci(0, 8.6, 2.3), g.poly([(-2.2, 8), (0.3, 2.4), (2.2, 8)])))
        o.flat(core, (255, 240, 180))
        stone = o.mask(lambda g: (g.rr(-13.5, -13.5, 13.5, -9.5, 1.5), g.rr(-13.5, 11, 13.5, 14.5, 1.5)))
        o.shaded(stone, (176, 166, 154), 0.2, 0.12, 0.4, 0.15)
        im = o.done((1.5, 1.5, 0.4))
        ImageDraw.Draw(im).text((S(34), S(21.5)), "Hearth", font=self.font(22), fill=rgba(TEXT), anchor="lm")
        return finish(im)

    # ---- lists --------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        box = (8, 4, w - 8, h - 4)
        m = rr_mask(w, h, box, 12 if h < 70 else 16)
        im = layer(clear(w, h), (0, 0, 0), blur(shift(m, 0, 2), 2), 0.35)
        im = through(im, vgrad(w, h, tone(SEL, 0.06), tone(SEL, -0.04), box[1], box[3]), m)
        im = layer(im, WHITE, ImageChops.subtract(m, shift(m, 0, 1)), 0.12)
        return finish(im)

    def divider(self):
        w, h = 640, 4
        return finish(layer(clear(w, h), WHITE, rect_mask(w, h, (22, 1.5, w - 22, 2.5)), 0.06))

    # ---- tiles --------------------------------------------------------------------------
    def frame(self, w, h, box, r, focused):
        """Unfocused: a thin light outline. Focused: a lighter card, raised on a soft shadow."""
        im = clear(w, h)
        if focused:
            m = rr_mask(w, h, box, r)
            im = layer(im, (0, 0, 0), ImageChops.multiply(blur(shift(m, 0, 5), 6), edge_fade(w, h, 3)), 0.55)
            im = through(im, vgrad(w, h, CARD, CARD_LOW, box[1], box[3]), m)
            im = layer(im, WHITE, ImageChops.subtract(m, shift(m, 0, 1.3)), 0.22)
            return im
        im = layer(im, OUTLINE, rr_mask(w, h, box, r), 0.025)
        return layer(im, OUTLINE, ring_mask(w, h, box, r, 1.5), 0.24)

    def card(self, w, h, focused):
        return finish(self.frame(w, h, (7, 7, w - 7, h - 7), 14, focused))

    def tile_base(self, focused):
        # the focused card a little larger: lifted towards the viewer
        return finish(self.frame(156, 278, (7, 5, 149, 268) if focused else (9, 8, 147, 266), 16, focused))

    def tile_glyph(self, key, focused):
        o = Obj(156, 278, 78, 104 if focused else 106, 1.2 if focused else 1.14)
        MENU[key](o)
        return finish(o.done((4, 4, 0.5)))

    def home_tile(self, key, focused):
        base = self.tile_base(focused)
        return Image.alpha_composite(base, self.tile_glyph(key, focused)) if key else base

    def preview_frame(self):
        return finish(self.frame(250, 360, (2, 2, 248, 358), 14, False))

    def key(self, focused):
        w, h = 52, 40
        m = rr_mask(w, h, (1, 1, w - 1, h - 1), 8)
        im = layer(clear(w, h), CARD if focused else (62, 59, 56), m)
        return finish(layer(im, WHITE, ImageChops.subtract(m, shift(m, 0, 1)), 0.14))

    def input_box(self):
        w, h = 560, 60
        m = rr_mask(w, h, (2, 3, w - 2, h - 3), 12)
        im = layer(clear(w, h), (250, 247, 241), m)
        return finish(layer(im, (0, 0, 0), ImageChops.multiply(blur(ImageChops.subtract(m, shift(m, 0, 2)), 1.2), m), 0.12))

    # ---- buttons and small parts ----------------------------------------------------------
    def button(self, label, primary):
        # A / B at their own size, X / Y scaled to 44 high: the same 30 px disc in both
        w, h = 34, (34 if label in "AB" else 44)
        im = clear(w, h)
        m = blank(w, h)
        Shape(m).ci(w / 2, h / 2, 15)
        im = through(im, vgrad(w, h, tone(KEYCAP, 0.1), tone(KEYCAP, -0.08), h / 2 - 15, h / 2 + 15), m)
        ImageDraw.Draw(im).text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(15.5), fill=rgba(KEYINK), anchor="mm")
        return finish(im)

    def pill(self, label, w, h=44):
        f = self.font(12.5)
        tw = ImageDraw.Draw(Image.new("L", (1, 1))).textlength(label, font=f) / SS
        w = int(math.ceil(tw + 24))
        im = clear(w, h)
        m = rr_mask(w, h, (1, h / 2 - 12, w - 1, h / 2 + 12), 12)
        im = through(im, vgrad(w, h, tone(KEYCAP, 0.1), tone(KEYCAP, -0.08), h / 2 - 12, h / 2 + 12), m)
        ImageDraw.Draw(im).text((S(w / 2), S(h / 2 + 0.5)), label, font=f, fill=rgba(KEYINK), anchor="mm")
        return finish(im)

    def dot(self, active):
        w, h = 22, 10
        m = rr_mask(w, h, (2, 2.5, 20, 7.5), 2.5)
        return finish(layer(clear(w, h), HONEY if active else (110, 105, 99), m))

    def toggle(self, on):
        w, h = 92, 44
        x0, x1, y0, y1 = 32, 84, 8, 36
        r = (y1 - y0) / 2
        track = rr_mask(w, h, (x0, y0, x1, y1), r)
        im = layer(clear(w, h), HONEY if on else (88, 84, 80), track)
        im = layer(im, (0, 0, 0), ImageChops.multiply(blur(ImageChops.subtract(track, shift(track, 0, 1.6)), 1), track), 0.25)
        knob = blank(w, h)
        Shape(knob).ci(x1 - r if on else x0 + r, h / 2, r - 3.5)
        im = layer(im, (0, 0, 0), blur(shift(knob, 0, 1.5), 1.5), 0.4)
        return finish(through(im, vgrad(w, h, WHITE, (226, 220, 212), y0, y1), knob))

    def arrow(self, left, size=24):
        m = blank(size, size)
        c, k = size / 2, size * 0.2
        sx = -1 if left else 1
        Shape(m).ln([(c - sx * k * 0.5, c - k), (c + sx * k * 0.5, c), (c - sx * k * 0.5, c + k)], size * 0.11)
        return finish(layer(clear(size, size), SUBTLE, m))

    def panel_image(self, w, h):
        if w >= 600:  # dialog: a rounded sheet on a soft shadow
            box = (30, 8, w - 30, h - 10)
            m = rr_mask(w, h, box, 20)
            im = layer(clear(w, h), (0, 0, 0), ImageChops.multiply(blur(shift(m, 0, 4), 6), edge_fade(w, h, 3)), 0.5)
            im = layer(im, SHEET, m)
            return finish(layer(im, WHITE, ImageChops.subtract(m, shift(m, 0, 1.2)), 0.1))
        # pop-up menus hang under MainUI's square title band: square top, rounded bottom
        m = rr_mask(w, h, (0, -24, w, h), 16)
        im = layer(clear(w, h), SHEET, m)
        return finish(layer(im, WHITE, rect_mask(w, h, (14, 0, w - 14, 1)), 0.08))

    def folder_icon(self):
        o = Obj(60, 60, 30, 31)
        back = o.mask(lambda g: (g.rr(-21, -16, -3, -6, 3), g.rr(-21, -11, 21, 15, 4)))
        o.shaded(back, (204, 146, 52), 0.1, 0.15, 0.2, 0.1)
        front = o.mask(lambda g: g.rr(-21, -5, 21, 15, 4))
        o.shaded(front, (240, 192, 88), 0.18, 0.12, 0.5, 0.18)
        return finish(o.done((1.5, 1.5, 0.45)))

    def favorite_mark(self):
        o = Obj(34, 39, 17, 19.5)
        star = o.mask(lambda g: g.rpoly(star_pts(12.5, 6, cy=0.5), 2.4))
        o.shaded(star, HONEY, 0.2, 0.14, 0.5, 0.2)
        return finish(o.done((1.2, 1.2, 0.45)))

    def battery(self, level, charging=False):
        w = h = 48
        im = clear(w, h)
        body = rr_mask(w, h, (6, 15, 40, 33), 5)
        hole = rr_mask(w, h, (8.2, 17.2, 37.8, 30.8), 3)
        im = layer(im, SUBTLE, ImageChops.subtract(body, hole))
        im = layer(im, SUBTLE, rr_mask(w, h, (41, 20.5, 44, 27.5), 1.4))
        if level > 0:
            col = CORAL if level <= 0.2 else (126, 196, 108)
            fm = rr_mask(w, h, (10.2, 19.2, 10.2 + 25.6 * level, 28.8), 1.8)
            im = through(im, vgrad(w, h, tone(col, 0.18), tone(col, -0.1), 19, 29), fm)
        if charging:
            pts = [(26, 9), (16, 26), (23, 26), (20.5, 39), (31, 21.5), (24, 21.5)]
            edge = blank(w, h)
            Shape(edge).rpoly(pts, 3.2)
            bolt = blank(w, h)
            Shape(bolt).poly(pts)
            im = layer(im, BAR, edge)
            im = through(im, vgrad(w, h, (255, 224, 110), (244, 168, 50), 9, 39), bolt)
        return finish(im)

    # ---- system and app icons -----------------------------------------------------------
    _order = None

    def body_color(self, sid):
        if Theme._order is None:
            Theme._order = {s: i for i, s in enumerate(system_ids())}
        return BODY[Theme._order.get(sid, len(sid)) % len(BODY)]

    def icon_picture(self, sid, selected, cy):
        return system_object(sid, 60, cy, self.body_color(sid), 108, 86 if cy < 60 else 104)

    def badge(self, label, selected):
        w, h = 120, 130
        im = clear(w, h)
        f = self.font(13)
        tw = ImageDraw.Draw(im).textlength(label, font=f) / SS
        bw = min(114, tw + 16)
        m = rr_mask(w, h, (60 - bw / 2, 106, 60 + bw / 2, 126), 10)
        im = layer(im, (0, 0, 0), blur(shift(m, 0, 1.2), 1.2), 0.3)
        im = through(im, vgrad(w, h, tone(KEYCAP, 0.1), tone(KEYCAP, -0.06), 106, 126), m)
        ImageDraw.Draw(im).text((S(60), S(116.3)), label, font=f, fill=rgba(KEYINK), anchor="mm")
        return im

    def system_icon(self, sid, selected):
        label = None if sid in NO_BADGE else BADGES.get(sid, sid[:7].upper())
        out = self.icon_picture(sid, selected, 54 if label else 64)
        if label:
            out = Image.alpha_composite(out, self.badge(label, selected))
        return finish(out)

    def app_icon(self, key):
        n = 96
        col = APP_TILE.get(key, BLUEC)
        box = (8, 7, n - 8, n - 9)
        m = rr_mask(n, n, box, 22)
        im = layer(clear(n, n), (0, 0, 0), blur(shift(m, 0, 3), 3), 0.5)
        im = through(im, vgrad(n, n, tone(col, 0.2), tone(col, -0.14), box[1], box[3]), m)
        im = layer(im, WHITE, ImageChops.multiply(blur(ImageChops.subtract(m, shift(m, 0, 1.6)), 0.7), m), 0.35)
        g = clear(n, n)
        APPS[key](ImageDraw.Draw(g), n / 2, n / 2 - 1, n * 0.23, rgba(WHITE), 4.4)
        ga = g.getchannel("A")
        im = layer(im, tone(col, -0.5), ImageChops.multiply(blur(shift(ga, 0, 1.6), 1.0), m), 0.6)
        return finish(layer(im, (255, 252, 246), ga))

    # ---- sound and config -----------------------------------------------------------------
    def sound(self, path):
        """A soft, low wooden 'tok', faded out (no click)."""
        rate, length = 22050, 0.05
        frames = bytearray()
        for i in range(int(rate * length)):
            t = i / rate
            env = min(1.0, t / 0.002, (length - t) / 0.006) * math.exp(-t * 95)
            s = 0.8 * math.sin(2 * math.pi * 620 * t) + 0.2 * math.sin(2 * math.pi * 1240 * t)
            frames += struct.pack("<h", int(7600 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["list"]["font"] = LIST_FONT
        cfg["hint"]["color"] = hexc(SUBTLE)
        cfg["grid"]["selectedcolor"] = hexc(WHITE)
        cfg["total"]["color"] = hexc(SUBTLE)
        cfg["mainui"] = {"accent": hexc(COPPER), "panel": hexa(self.panel, self.panel_alpha), "background": hexc(BG_BOT)}
        return cfg
