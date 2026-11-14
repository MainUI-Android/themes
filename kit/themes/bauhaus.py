"""Bauhaus: a 1920s poster on warm paper. Flat red, blue and yellow circles, squares and
triangles, thick black rules and a geometric sans; the focused item is a solid colour block."""
import math
import struct
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, GLYPHS, SS, Pen, S, Style, canvas, finish, hexc, rgba, system_ids

PAPER = (240, 233, 218)      # the ground
CARD = (248, 244, 234)       # tiles, cards and panels: a touch lighter than the ground
INK = (26, 24, 22)
RED = (216, 44, 32)
BLUE = (24, 72, 160)
YELLOW = (246, 188, 12)
GREY = (98, 92, 84)          # unfocused labels
RULE = (26, 24, 22, 70)      # list dividers

# main menu: (shape, its colour, the glyph's colour, the focused tile's colour)
TILE = {
    "recent": ("circle", BLUE, CARD, YELLOW),
    "favorite": ("square", RED, CARD, BLUE),
    "game": ("dome", YELLOW, INK, RED),
    "emulators": ("circle", INK, CARD, YELLOW),
    "retroarch": ("triangle", RED, CARD, BLUE),
    "app": ("square", INK, None, RED),
    "setting": ("circle", YELLOW, INK, BLUE),
}
APP_COLOR = {"themes": RED, "pacman": YELLOW, "gameswitcher": BLUE, "search": INK, "gallery": BLUE,
             "activity": YELLOW, "retroarch": RED, "tweaks": INK, "download": BLUE, "folder": YELLOW,
             "hidden": INK, "emulators": RED, "category": YELLOW, "updates": BLUE, "repos": RED}


# ---- flat shapes on a supersampled ImageDraw (coordinates in 1x pixels) ---------------------

def rect(d, box, fill):
    d.rectangle([S(v) for v in box], fill=rgba(fill))


def frame(d, box, w, fill):
    """A rectangle outline [w] thick inside [box]."""
    x0, y0, x1, y1 = box
    for b in ((x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1), (x0, y0, x0 + w, y1), (x1 - w, y0, x1, y1)):
        rect(d, b, fill)


def disc(d, cx, cy, r, fill):
    d.ellipse([S(cx - r), S(cy - r), S(cx + r), S(cy + r)], fill=rgba(fill))


def tri(d, pts, fill):
    d.polygon([(S(x), S(y)) for x, y in pts], fill=rgba(fill))


def dome(d, cx, base, r, fill):
    """Half a disc standing on y [base]."""
    d.pieslice([S(cx - r), S(base - r), S(cx + r), S(base + r)], 180, 360, fill=rgba(fill))


def bar(d, p0, p1, w, fill):
    """A straight bar with square ends, [w] thick."""
    (x0, y0), (x1, y1) = p0, p1
    a = math.atan2(y1 - y0, x1 - x0)
    nx, ny = -math.sin(a) * w / 2, math.cos(a) * w / 2
    d.polygon([(S(x0 + nx), S(y0 + ny)), (S(x1 + nx), S(y1 + ny)), (S(x1 - nx), S(y1 - ny)), (S(x0 - nx), S(y0 - ny))],
              fill=rgba(fill))


def star_pts(cx, cy, r0, r1, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r0 if i % 2 == 0 else r1
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def shape(d, kind, cx, cy, size, fill):
    """A primary shape about [size] across, centred on (cx, cy)."""
    h = size / 2
    if kind == "circle":
        disc(d, cx, cy, h, fill)
    elif kind == "square":
        rect(d, (cx - h * 0.9, cy - h * 0.9, cx + h * 0.9, cy + h * 0.9), fill)
    elif kind == "dome":
        dome(d, cx, cy + h * 0.5, h * 1.08, fill)
    elif kind == "triangle":
        tri(d, [(cx, cy - h * 1.02), (cx + h * 1.14, cy + h * 0.92), (cx - h * 1.14, cy + h * 0.92)], fill)


# glyph centre and size inside each shape (dx, dy, scale)
INSET = {"circle": (0, 0, 1.0), "square": (0, 0, 1.0), "dome": (0, 6, 0.95), "triangle": (0, 14, 0.78)}


# ---- the main menu glyphs: solid, flat, square-cornered (fg on bg) ----------------------------

def gl_recent(d, cx, cy, s, fg, bg):
    disc(d, cx, cy, s, fg)
    disc(d, cx, cy, s * 0.72, bg)
    bar(d, (cx, cy + s * 0.08), (cx, cy - s * 0.52), s * 0.17, fg)
    bar(d, (cx - s * 0.08, cy), (cx + s * 0.4, cy), s * 0.17, fg)


def gl_favorite(d, cx, cy, s, fg, bg):
    tri(d, star_pts(cx, cy + s * 0.06, s * 1.05, s * 0.44), fg)


def gl_game(d, cx, cy, s, fg, bg):
    rect(d, (cx - s * 1.05, cy - s * 0.5, cx + s * 1.05, cy + s * 0.2), fg)
    disc(d, cx - s * 0.66, cy + s * 0.2, s * 0.42, fg)
    disc(d, cx + s * 0.66, cy + s * 0.2, s * 0.42, fg)
    x, y, a, t = cx - s * 0.58, cy - s * 0.1, s * 0.28, s * 0.075
    rect(d, (x - a, y - t, x + a, y + t), bg)
    rect(d, (x - t, y - a, x + t, y + a), bg)
    disc(d, cx + s * 0.44, cy + s * 0.0, s * 0.13, bg)
    disc(d, cx + s * 0.72, cy - s * 0.24, s * 0.13, bg)


def gl_emulators(d, cx, cy, s, fg, bg, screen=None):
    rect(d, (cx - s * 0.62, cy - s, cx + s * 0.62, cy + s), fg)
    rect(d, (cx - s * 0.44, cy - s * 0.8, cx + s * 0.44, cy - s * 0.08), screen or bg)
    x, y, a, t = cx - s * 0.26, cy + s * 0.46, s * 0.17, s * 0.06
    rect(d, (x - a, y - t, x + a, y + t), bg)
    rect(d, (x - t, y - a, x + t, y + a), bg)
    disc(d, cx + s * 0.22, cy + s * 0.56, s * 0.1, bg)
    disc(d, cx + s * 0.4, cy + s * 0.36, s * 0.1, bg)


def gl_retroarch(d, cx, cy, s, fg, bg):
    rows = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX",
            "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."]
    px = s * 2 / 11
    x0, y0 = cx - px * 5.5, cy - px * 4
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "X":
                rect(d, (x0 + i * px - 0.15, y0 + j * px - 0.15, x0 + (i + 1) * px + 0.15, y0 + (j + 1) * px + 0.15), fg)


def gl_app(d, cx, cy, s, fg, bg):
    """Four primaries; [fg] None keeps them in colour."""
    h, g = s * 0.4, s * 0.52
    cols = [RED, YELLOW, BLUE, CARD] if fg is None else [fg] * 4
    disc(d, cx - g, cy - g, h, cols[0])
    rect(d, (cx + g - h, cy - g - h, cx + g + h, cy - g + h), cols[1])
    tri(d, [(cx - g, cy + g - h * 1.05), (cx - g + h * 1.1, cy + g + h * 0.9), (cx - g - h * 1.1, cy + g + h * 0.9)], cols[2])
    rect(d, (cx + g - h, cy + g - h, cx + g + h, cy + g + h), cols[3])


def gl_setting(d, cx, cy, s, fg, bg):
    pts = []
    teeth = 8
    for i in range(teeth * 4):
        a = math.radians(i * 360 / (teeth * 4) - 90 + 360 / teeth / 8)
        r = s if (i % 4) in (1, 2) else s * 0.74
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    tri(d, pts, fg)
    disc(d, cx, cy, s * 0.3, bg)


GLYPH = {"recent": gl_recent, "favorite": gl_favorite, "game": gl_game, "emulators": gl_emulators,
         "retroarch": gl_retroarch, "app": gl_app, "setting": gl_setting}


# ---- system pictures: GLYPHS line art in black over paper, colour in the soft parts -------------

class BauPen(Pen):
    """A Pen drawn [sc] times bigger with lines [k] times thicker; soft fills go to their own mask."""

    def __init__(self, draw, soft_draw, cx, cy, sc=1.0, k=1.0, w=3.4):
        super().__init__(draw, cx, cy, (255, 255, 255, 255), SS, w)
        self.sd, self.sc, self.k = soft_draw, sc, k

    def p(self, x, y):
        return ((self.cx + x * self.sc) * self.ss, (self.cy + y * self.sc) * self.ss)

    def _w(self, w):
        return max(1, int(round((self.w if w is None else w) * self.k * self.sc * self.ss)))

    def rr(self, x0, y0, x1, y1, r=3, w=None, fill=False, soft=False):
        rad = min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2) * self.sc * self.ss
        box = [*self.p(x0, y0), *self.p(x1, y1)]
        if soft and not fill:
            self.sd.rounded_rectangle(box, radius=rad, fill=255)
        if fill:
            self.d.rounded_rectangle(box, radius=rad, fill=self.c)
        else:
            self.d.rounded_rectangle(box, radius=rad, outline=self.c, width=self._w(w))

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


def enclosed(walls, w, h):
    """The areas [walls] (SS-size L mask) close in completely, found at 2x: SS-size L mask."""
    w2, h2 = w * 2, h * 2
    wall = walls.resize((w2, h2), Image.BOX).point(lambda v: 255 if v > 50 else 0)
    pad = Image.new("L", (w2 + 2, h2 + 2), 0)
    pad.paste(wall, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    inside = pad.crop((1, 1, w2 + 1, h2 + 1)).point(lambda v: 255 if v == 0 else 0)
    return inside.filter(ImageFilter.MaxFilter(3)).resize((w * SS, h * SS), Image.BILINEAR)


def paint(im, color, mask):
    c = Image.new("RGBA", im.size, rgba(color))
    c.putalpha(mask)
    return Image.alpha_composite(im, c)


class Theme(Style):
    name = "Bauhaus"
    author = "MainUI"
    description = "A 1920s poster on warm paper: flat red, blue and yellow shapes, thick black rules, a geometric sans."

    bg_top = PAPER
    bg_bottom = PAPER
    accent = BLUE               # toast borders, progress bars (MainUI writes white on it)
    accent2 = RED
    highlight = RED             # the page counter's current page
    text = INK
    muted = GREY
    glyph_n = INK
    glyph_f = CARD
    panel = YELLOW              # toasts; 20 % darker it is the pop-up title strip
    panel_alpha = 255

    font_file = "MontserratAlternates-Bold.ttf"
    font_license = "OFL-MontserratAlternates.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 26, 21, 22, 20, 13, 16
    icon_quant = 48

    # ---- big pictures -------------------------------------------------------------------
    def background(self, w=640, h=480):
        """Paper with a poster's edges. MainUI cover-scales it, so only yellow may land behind
        black list text; the black rule, red and blue keep to the side margins."""
        im = canvas(w, h, rgba(PAPER))
        d = ImageDraw.Draw(im)
        rect(d, (630, 54, 636, 420), INK)                 # the header's rule turning down the margin
        rect(d, (0, 60, 14, 196), RED)
        d.pieslice([S(-108), S(312), S(108), S(528)], 270, 360, fill=rgba(YELLOW))
        disc(d, 611, 399, 15, BLUE)
        return finish(im)

    def header_bar(self):
        im = canvas(640, 60, rgba(PAPER))
        rect(ImageDraw.Draw(im), (0, 54, 640, 60), INK)
        return finish(im)

    def footer_bar(self):
        im = canvas(640, 60, rgba(PAPER))
        rect(ImageDraw.Draw(im), (0, 0, 640, 6), INK)
        return finish(im)

    def logo(self):
        w, h = 210, 42
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        disc(d, 13, 21, 10, BLUE)
        rect(d, (27, 11, 47, 31), RED)
        tri(d, [(61, 10), (73, 31), (49, 31)], YELLOW)
        d.text((S(80), S(21)), "bauhaus", font=self.font(25), fill=rgba(INK), anchor="lm")
        return finish(im)

    # ---- lists --------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        rect(d, (4, 3, w - 4, h - 3), YELLOW)
        rect(d, (4, 3, 12, h - 3), INK)
        return finish(im)

    def divider(self):
        im = canvas(640, 4)
        rect(ImageDraw.Draw(im), (20, 1.5, 620, 2.5), RULE)
        return finish(im)

    # ---- tiles --------------------------------------------------------------------------
    BOX = (10, 12, 146, 266)
    BOX_F = (6, 4, 150, 270)     # the focused block stands a little proud of the row
    BAND = (6, 175, 150, 215)

    def plain_tile(self, focused, block):
        im = canvas(156, 278)
        d = ImageDraw.Draw(im)
        if focused:
            rect(d, self.BOX_F, block)
            rect(d, self.BAND, INK)
        else:
            rect(d, self.BOX, CARD)
            frame(d, self.BOX, 2, INK)
        return im, d

    def tile_base(self, focused):
        """bg-home-tile: the system row's tile. MainUI fits the system name into 142 px (two
        lines for long ones, 170-204) and writes the game count at 222: the band covers both."""
        im = canvas(156, 278)
        d = ImageDraw.Draw(im)
        box = (6, 12, 150, 266)
        if focused:
            rect(d, box, BLUE)
            rect(d, (6, 160, 150, 236), INK)
        else:
            rect(d, box, CARD)
            frame(d, box, 2, INK)
        return finish(im)

    def home_tile(self, key, focused):
        if key is None:
            return self.tile_base(focused)
        kind, col, fg, block = TILE[key]
        im, d = self.plain_tile(focused, block)
        cx, cy = 78, 98
        shape(d, kind, cx, cy, 92, col)
        dx, dy, k = INSET[kind]
        s = 25 * k
        if key == "emulators":
            gl_emulators(d, cx + dx, cy + dy, s * 1.1, fg, col, YELLOW)
        elif key == "app":
            gl_app(d, cx + dx, cy + dy, s * 1.05, None, col)
        else:
            GLYPH[key](d, cx + dx, cy + dy, s, fg, col)
        return finish(im)

    def card(self, w, h, focused):
        """Games grid cell; its top stays clear of the header rule (the grid starts at y 55)."""
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        box = (4, 9, w - 4, h - 5)
        if focused:
            rect(d, box, BLUE)
        else:
            rect(d, box, CARD)
            frame(d, box, 2, INK)
        return finish(im)

    # ---- buttons and small parts ----------------------------------------------------------
    def button(self, label, primary):
        n = 54
        im = canvas(n, n)
        d = ImageDraw.Draw(im)
        f = self.font(25, "Poppins-SemiBold.ttf")    # (the theme font's Y looks like a y)
        if label == "A":
            rect(d, (6, 6, 48, 48), RED)
            tc, cy = CARD, 27
        elif label == "B":
            disc(d, 27, 27, 22, BLUE)
            tc, cy = CARD, 27
        elif label == "X":
            tri(d, [(27, 1), (54, 50), (0, 50)], YELLOW)
            tc, cy, f = INK, 36, self.font(22, "Poppins-SemiBold.ttf")
        else:
            dome(d, 27, 49, 27, INK)
            tc, cy, f = CARD, 37, self.font(22, "Poppins-SemiBold.ttf")
        d.text((S(27), S(cy)), label, font=f, fill=rgba(tc), anchor="mm")
        return finish(im)

    def pill(self, label, w, h=48):
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        rect(d, (3, 10, w - 3, h - 10), INK)
        d.text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(15, "Poppins-SemiBold.ttf"), fill=rgba(CARD), anchor="mm")
        return finish(im)

    def dot(self, active):
        im = canvas(24, 14)
        d = ImageDraw.Draw(im)
        if active:
            rect(d, (6, 1, 18, 13), RED)
        else:
            disc(d, 12, 7, 3.5, INK)
        return finish(im)

    def toggle(self, on):
        w, h = 92, 44
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        box = (8, 9, 84, 35)
        if on:
            rect(d, box, BLUE)
            rect(d, (58, 9, 84, 35), INK)
            rect(d, (62, 13, 80, 31), YELLOW)
        else:
            rect(d, box, CARD)
            frame(d, box, 3, INK)
            rect(d, (8, 9, 34, 35), INK)
        return finish(im)

    def arrow(self, left, size=24):
        s = size
        im = canvas(s, s)
        pts = [(0.2, 0.5), (0.74, 0.16), (0.74, 0.84)] if left else [(0.8, 0.5), (0.26, 0.16), (0.26, 0.84)]
        tri(ImageDraw.Draw(im), [(x * s, y * s) for x, y in pts], INK)
        return finish(im)

    def panel_image(self, w, h):
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        if w >= 600:  # pop-bg (dialogs)
            box = (24, 14, w - 24, h - 14)
            rect(d, box, CARD)
            frame(d, box, 4, INK)
            rect(d, (box[0], box[1], box[2], box[1] + 14), INK)
            rect(d, (box[0], box[1], box[0] + 70, box[1] + 14), RED)
            return finish(im)
        rect(d, (0, 0, w, h), CARD)
        frame(d, (0, -10, w, h), 4, INK)
        rect(d, (0, 0, w, 4), INK)
        return finish(im)

    def folder_icon(self):
        im = canvas(60, 60)
        d = ImageDraw.Draw(im)
        rect(d, (8, 13, 28, 22), INK)
        rect(d, (8, 18, 52, 48), INK)
        rect(d, (11, 24, 49, 45), YELLOW)
        return finish(im)

    def favorite_mark(self):
        im = canvas(34, 39)
        tri(ImageDraw.Draw(im), star_pts(17, 20, 15, 6.4), RED)
        return finish(im)

    def battery(self, level, charging=False):
        im = canvas(48, 48)
        d = ImageDraw.Draw(im)
        frame(d, (5, 15, 40, 33), 3, INK)
        rect(d, (40, 20, 44, 28), INK)
        if level > 0:
            rect(d, (9, 19, 9 + 27 * level, 29), RED if level <= 0.2 else INK)
        if charging:
            pts = [(26, 6), (14, 26), (22, 26), (19, 42), (33, 20), (25, 20)]
            d.line([(S(x), S(y)) for x, y in pts + pts[:1]], fill=rgba(INK), width=int(S(4)), joint="curve")
            tri(d, pts, YELLOW)
        return finish(im)

    def preview_frame(self):
        im = canvas(250, 360)
        d = ImageDraw.Draw(im)
        rect(d, (4, 4, 246, 356), CARD)
        frame(d, (4, 4, 246, 356), 3, INK)
        rect(d, (4, 4, 34, 34), RED)
        return finish(im)

    def key(self, focused):
        """MainUI writes white letters on the keys; drawn at about the real key size (52 x 40)."""
        w, h = 52, 40
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        rect(d, (1.5, 1.5, w - 1.5, h - 1.5), RED if focused else INK)
        return finish(im)

    def input_box(self):
        im = canvas(560, 60)
        d = ImageDraw.Draw(im)
        rect(d, (2, 2, 558, 58), CARD)
        frame(d, (2, 2, 558, 58), 4, INK)
        return finish(im)

    # ---- system and app icons -----------------------------------------------------------
    _order = None
    _boxes = {}
    K = 1.2

    def icon_index(self, sid):
        if Theme._order is None:
            Theme._order = {s: i for i, s in enumerate(system_ids())}
        return Theme._order.get(sid, len(sid))

    def icon_box(self, sid):
        """The drawing's extent around its centre at scale 1."""
        if sid not in self._boxes:
            lines, m = canvas(160, 160), Image.new("L", (160 * SS, 160 * SS), 0)
            (GLYPHS.get(sid) or GLYPHS["fallback"])(BauPen(ImageDraw.Draw(lines), ImageDraw.Draw(m), 80, 80, 1.0, self.K))
            x0, y0, x1, y1 = ImageChops.lighter(lines.split()[3], m).getbbox()
            self._boxes[sid] = (x0 / SS - 80, y0 / SS - 80, x1 / SS - 80, y1 / SS - 80)
        return self._boxes[sid]

    def icon_picture(self, sid, selected, cy):
        w, h = 120, 130
        draw = GLYPHS.get(sid) or GLYPHS["fallback"]
        bx0, by0, bx1, by1 = self.icon_box(sid)
        sc = min(1.2, 98 / (bx1 - bx0), 90 / (by1 - by0))
        cx = 60 - (bx0 + bx1) / 2 * sc
        cy = cy - (by0 + by1) / 2 * sc
        x0, y0, x1, y1 = cx + bx0 * sc, cy + by0 * sc, cx + bx1 * sc, cy + by1 * sc

        i = self.icon_index(sid)
        kind = i % 4
        col = RED if (i + i // 4) % 2 == 0 else YELLOW
        out = canvas(w, h)
        d = ImageDraw.Draw(out)
        bw, bh = x1 - x0, y1 - y0
        r = max(18, min(30, 0.36 * max(bw, bh)))
        if kind == 0:
            disc(d, min(x1 - r * 0.35, 112 - r), max(y0 + r * 0.2, 6 + r), r, col)
        elif kind == 1:
            rect(d, (max(6, x0 - 8), y1 - r * 1.7, max(6, x0 - 8) + r * 1.7, min(124, y1 + 8)), col)
        elif kind == 2:
            dome(d, 60, min(124, y1 + 6), min(54, bw / 2 + 10), col)
        else:
            base = min(124, y1 + 4)
            hw = min(54, bw / 2 + 4)
            tri(d, [(60, max(4, base - hw * 1.7)), (60 + hw, base), (60 - hw, base)], col)

        lines, soft = canvas(w, h), Image.new("L", (w * SS, h * SS), 0)
        draw(BauPen(ImageDraw.Draw(lines), ImageDraw.Draw(soft), cx, cy, sc, self.K))
        la = lines.split()[3]
        inside = enclosed(la, w, h)
        out = paint(out, CARD, ImageChops.lighter(inside, soft))
        out = paint(out, BLUE, soft)
        out = paint(out, INK, la)
        return finish(out)

    def system_icon(self, sid, selected):
        # (no name badge: MainUI writes the name under each picture)
        return self.icon_picture(sid, selected, 64)

    def app_icon(self, key):
        n = 96
        col = APP_COLOR.get(key, RED)
        im = canvas(n, n)
        d = ImageDraw.Draw(im)
        rect(d, (6, 6, 90, 90), col)
        dark = col in (YELLOW,)
        if key == "retroarch":
            gl_retroarch(d, 48, 48, 24, INK if dark else CARD, col)
        else:
            APPS[key](d, 48, 48, n * 0.24, rgba(INK if dark else CARD), n * 0.07)
        return finish(im)

    # ---- sound and config -----------------------------------------------------------------
    def sound(self, path):
        """A dry wood-block 'tock'."""
        rate, length = 22050, 0.04
        frames = bytearray()
        for i in range(int(rate * length)):
            t = i / rate
            env = min(1.0, t / 0.001) * math.exp(-t * 120)
            s = math.sin(2 * math.pi * 1180 * t) * 0.7 + math.sin(2 * math.pi * 2950 * t) * 0.3 * math.exp(-t * 200)
            frames += struct.pack("<h", int(9000 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc(CARD)  # (on the black bands and the blue cells)
        return cfg
