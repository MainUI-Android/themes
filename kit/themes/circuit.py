"""Circuit: a printed circuit board. Green solder mask with copper traces and gold pads, white
silkscreen outlines and labels; the focused item is an energised copper pour with lit LEDs."""
import math
import struct
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, GLYPHS, SS, TILES, Pen, S, Style, canvas, finish, hexc, rgba

BOARD = (12, 62, 40)          # solder mask
BOARD_D = (8, 44, 29)         # bars, panels, cells: a darker mask
TRACE = (24, 92, 58)          # copper under the mask
TENT = (34, 110, 70)          # tented vias
GOLD = (214, 172, 84)         # exposed pads (ENIG)
GOLD_L = (255, 216, 128)      # lit gold
GLOW = (255, 150, 50)         # the warm light of an energised part
CU_TOP = (198, 108, 48)       # copper pour, top to bottom
CU_BOT = (148, 72, 30)
CHIP = (24, 26, 28)           # IC packages
TIN = (196, 204, 208)         # tinned pads
SILK = (238, 242, 232)
SILK_M = (172, 204, 182)      # unfocused labels
LED = {"recent": (70, 160, 255), "favorite": (255, 196, 40), "game": (90, 235, 120), "emulators": (255, 84, 70),
       "retroarch": (190, 120, 255), "app": (40, 220, 230), "setting": (250, 250, 240)}
APP_LED = {"themes": (190, 120, 255), "pacman": (255, 196, 40), "gameswitcher": (70, 160, 255),
           "search": (40, 220, 230), "gallery": (255, 84, 70), "activity": (90, 235, 120), "retroarch": (190, 120, 255),
           "tweaks": (250, 250, 240), "download": (70, 160, 255), "folder": (255, 196, 40), "hidden": (172, 204, 182),
           "emulators": (255, 84, 70), "category": (90, 235, 120), "updates": (40, 220, 230), "repos": (255, 196, 40)}


# ---- layers --------------------------------------------------------------------------------

def clear(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def paint(mask, c, k=1.0):
    """Colour [c] shaped by L [mask], its alpha scaled by [k]."""
    if k != 1.0:
        mask = mask.point(lambda v: min(255, int(v * k)))
    out = Image.new("RGBA", mask.size, rgba(c))
    out.putalpha(mask)
    return out


def over(*layers):
    out = layers[0]
    for lay in layers[1:]:
        out = Image.alpha_composite(out, lay)
    return out


def masked(im, mask):
    out = im.copy()
    out.putalpha(ImageChops.multiply(im.split()[3], mask))
    return out


def blur(m, r):
    return m.filter(ImageFilter.GaussianBlur(r))


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def vgrad(w, h, top, bottom, y0=0, y1=None):
    y1 = h - 1 if y1 is None else y1
    col = Image.new("RGBA", (1, h))
    for y in range(h):
        col.putpixel((0, y), rgba(mix(top, bottom, min(1, max(0, (y - y0) / max(1, y1 - y0))))))
    return col.resize((w, h), Image.NEAREST)


def mask(w, h, fn):
    """An L mask drawn supersampled by fn(ImageDraw) and returned at 1x."""
    m = Image.new("L", (w * SS, h * SS), 0)
    fn(ImageDraw.Draw(m))
    return m.resize((w, h), Image.LANCZOS)


def rr_mask(w, h, box, r, width=0):
    """Rounded rect (L, 1x): filled, or an outline [width] wide inside the box."""
    def fn(d):
        if width:
            d.rounded_rectangle([S(v) for v in box], radius=S(r), outline=255, width=max(1, int(S(width))))
        else:
            d.rounded_rectangle([S(v) for v in box], radius=S(r), fill=255)
    return mask(w, h, fn)


def chamfer(box, c):
    """A rectangle with its top-left corner cut: a silkscreen pin-1 outline."""
    x0, y0, x1, y1 = box
    return [(x0 + c, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + c)]


def outline(d, pts, w):
    pts = [(S(x), S(y)) for x, y in pts] + [(S(pts[0][0]), S(pts[0][1]))]
    d.line(pts, fill=255, width=int(S(w)), joint="curve")


def edge_fade(w, h, n=8):
    """L mask: 0 on the canvas border, 255 from [n] px inside, so a glow fades instead of being cut."""
    def ramp(m):
        return [int(255 * min(1.0, min(i, m - 1 - i) / n) ** 1.5) for i in range(m)]
    row = Image.new("L", (w, 1))
    row.putdata(ramp(w))
    col = Image.new("L", (1, h))
    col.putdata(ramp(h))
    return ImageChops.multiply(row.resize((w, h), Image.NEAREST), col.resize((w, h), Image.NEAREST))


def halo(m, layers, fade=None, cut=None):
    out = Image.new("L", m.size, 0)
    for r, k in layers:
        out = ImageChops.add(out, blur(m, r).point(lambda v: min(255, int(v * k))))
    if fade is not None:
        out = ImageChops.multiply(out, fade)
    if cut is not None:
        out = ImageChops.subtract(out, cut)
    return out


def text_mask(w, h, s, font, x, cy, anchor="mm"):
    return mask(w, h, lambda d: d.text((S(x), S(cy)), s, font=font, fill=255, anchor=anchor))


def lean(im):
    """Channels rounded down to multiples of 3: invisible, and the PNG shrinks."""
    return Image.merge("RGBA", [c.point(lambda v: v - v % 3) for c in im.split()])


def via(d, x, y, r, hole):
    d.ellipse([S(x - r), S(y - r), S(x + r), S(y + r)], fill=255)
    if hole:
        d.ellipse([S(x - hole), S(y - hole), S(x + hole), S(y + hole)], fill=0)


# ---- system pictures: GLYPHS line art as silkscreen, soft parts as gold pads ---------------------

class SilkPen(Pen):
    """A Pen drawn [sc] times bigger; soft fills go to their own mask."""

    def __init__(self, draw, soft_draw, cx, cy, sc=1.0, w=3.0):
        super().__init__(draw, cx, cy, (255, 255, 255, 255), SS, w)
        self.sd, self.sc = soft_draw, sc

    def p(self, x, y):
        return ((self.cx + x * self.sc) * self.ss, (self.cy + y * self.sc) * self.ss)

    def _w(self, w):
        return max(1, int(round((self.w if w is None else w) * self.sc * self.ss)))

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


class Theme(Style):
    name = "Circuit"
    author = "MainUI"
    description = "A printed circuit board: green solder mask, copper traces, gold pads, white silkscreen; focus lights up like a live trace."

    bg_top = BOARD
    bg_bottom = BOARD
    accent = (176, 88, 36)       # toast borders, progress bars (MainUI writes white on it)
    accent2 = BOARD_D
    highlight = GOLD_L           # the page counter's current page
    text = SILK
    muted = SILK_M
    glyph_n = SILK
    glyph_f = SILK
    panel = (20, 84, 55)         # toasts; 20 % darker it is the pop-up title strip, over a darker panel
    panel_alpha = 250
    bar = BOARD_D

    font_file = "ShareTechMono-Regular.ttf"
    font_license = "OFL-ShareTechMono.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 27, 23, 24, 21, 16, 18
    icon_quant = 64
    sel_icons = True

    # ---- background ----------------------------------------------------------------------
    def background(self, w=640, h=480):
        im = Image.new("RGBA", (w, h), rgba(BOARD))

        ends = []

        def traces(d):
            def run(pts, wd=2.6):
                d.line([(S(x), S(y)) for x, y in pts], fill=255, width=int(S(wd)), joint="curve")
            k = 9 * (math.sqrt(2) - 1)   # (keeps a bus 9 px apart through its 45 degree bends)
            for i in range(4):          # a bus in from the left, turning down
                x, end = 110 - 9 * i, 300 + 14 * (i % 2)
                run([(-5, 120 + 9 * i), (60 - k * i, 120 + 9 * i), (x, 170 + k * i), (x, end)])
                ends.append((x, end))
            for i in range(3):          # one in from the right, turning up
                x, end = 520 - 9 * i, 150 - 14 * (i % 2)
                run([(w + 5, 330 + 9 * i), (560 - k * i, 330 + 9 * i), (x, 290 + k * i), (x, end)])
                ends.append((x, end))
            # runs along the rows' top and bottom edges and in the margins, clear of list text
            run([(150, 70), (330, 70), (352, 70)])
            run([(230, 412), (600, 412)])
            run([(w + 5, 210), (622, 210), (614, 202), (614, 92)], 3.4)
            ends.extend([(150, 70), (352, 70), (230, 412), (600, 412), (614, 92)])
        tm = mask(w, h, traces)

        def vias(d):
            for x, y in ends + [(300, 130), (360, 250), (420, 310), (200, 370), (470, 190), (250, 250)]:
                via(d, x, y, 5.5, 2.2)
        vm = mask(w, h, vias)
        im = over(im, paint(tm, TRACE), paint(vm, TENT))
        # fiducials and mounting holes in the corners, silk reference marks
        # (in the margins, where no list text or icon reaches)
        def pads(d):
            via(d, 9, 236, 3.5, 0)
            via(d, 631, 300, 3.5, 0)

        def rings(d):
            via(d, 9, 236, 7.5, 6.3)
            via(d, 631, 300, 7.5, 6.3)
        im = over(im, paint(mask(w, h, pads), GOLD, 0.9), paint(mask(w, h, rings), SILK, 0.45))
        f = self.font(13)

        def silk(d):
            # (just under a list row's top edge, clear of its text)
            for x, y, s in ((44, 131, "U1"), (124, 311, "R12"), (540, 131, "C7"), (604, 191, "J2"), (84, 371, "TP3"),
                            (486, 371, "REV A")):
                d.text((S(x), S(y)), s, font=f, fill=255, anchor="lm")
        im = over(im, paint(mask(w, h, silk), SILK, 0.38))
        return im.convert("RGB").convert("RGBA")

    # ---- bars ----------------------------------------------------------------------------
    def _bar(self, top):
        w, h = 640, 60
        im = Image.new("RGBA", (w, h), rgba(BOARD_D))
        y = 57 if not top else 3
        ln = mask(w, h, lambda d: d.line([(0, S(y)), (S(w), S(y))], fill=255, width=int(S(2.2))))
        return over(im, paint(blur(ln, 2.5), GLOW, 0.55), paint(ln, GOLD))

    def header_bar(self):
        return self._bar(False)

    def footer_bar(self):
        return self._bar(True)

    # ---- logo ----------------------------------------------------------------------------
    def logo(self):
        w, h = 200, 42
        body = rr_mask(w, h, (6, 9, 34, 33), 2.5)

        def legs(d):
            for i in range(4):
                x = 10 + i * 6.6
                d.rectangle([S(x), S(4), S(x + 3.4), S(38)], fill=255)
        leg = ImageChops.subtract(mask(w, h, legs), body)
        dot = mask(w, h, lambda d: via(d, 11, 14, 2, 0))
        tm = text_mask(w, h, "CIRCUIT", self.font(26), 44, 22, "lm")
        return over(clear(w, h), paint(leg, GOLD), paint(body, CHIP), paint(dot, SILK, 0.7), paint(tm, SILK))

    # ---- lists ---------------------------------------------------------------------------
    def _pour(self, w, h, box, r, glow=True, rim=2.0):
        """The energised copper pour: copper with a lit gold rim and a warm glow around it."""
        shape = rr_mask(w, h, box, r)
        ring = rr_mask(w, h, box, r, rim)
        fill = masked(vgrad(w, h, CU_TOP, CU_BOT, box[1], box[3]), shape)
        out = clear(w, h)
        if glow:
            out = paint(halo(ring, ((5, 2.4), (2, 1.2)), edge_fade(w, h, 6), shape), GLOW)
        sheen = rr_mask(w, h, (box[0] + rim, box[1] + rim, box[2] - rim, box[1] + rim + 1.2), 0)
        return over(out, fill, paint(sheen, (255, 226, 160), 0.5), paint(ring, GOLD_L))

    def selection(self, h):
        w = 640
        r = 6 if h < 70 else 8
        return lean(self._pour(w, h, (8, 6, w - 8, h - 6), r))

    def divider(self):
        w = 640
        ln = mask(w, 4, lambda d: d.line([(S(20), S(2)), (S(620), S(2))], fill=255, width=int(S(1.4))))
        return paint(ln, TRACE, 1.0)

    # ---- tiles ---------------------------------------------------------------------------
    def _slot(self, w, h, box, r=4, notch=10):
        """An unfocused part: darker mask in a silkscreen outline with its pin-1 corner cut."""
        x0, y0, x1, y1 = box
        fill = mask(w, h, lambda d: d.polygon([(S(x), S(y)) for x, y in chamfer(box, notch)], fill=255))
        line = mask(w, h, lambda d: outline(d, chamfer(box, notch), 1.6))
        dot = mask(w, h, lambda d: via(d, x0 + notch * 0.5 + 4, y0 + notch * 0.5 + 4, 2.2, 0))
        return over(paint(fill, BOARD_D), paint(line, SILK, 0.62), paint(dot, SILK, 0.62))

    def _focus(self, w, h, box, notch=10, glow=True):
        """The focused part: the copper pour in the same pin-1 outline, lit."""
        x0, y0, x1, y1 = box
        shape = mask(w, h, lambda d: d.polygon([(S(x), S(y)) for x, y in chamfer(box, notch)], fill=255))
        ring = mask(w, h, lambda d: outline(d, chamfer((x0 + 1, y0 + 1, x1 - 1, y1 - 1), notch - 0.6), 2.2))
        fill = masked(vgrad(w, h, CU_TOP, CU_BOT, y0, y1), shape)
        out = clear(w, h)
        if glow:
            out = paint(halo(ring, ((6, 2.6), (2.2, 1.3)), edge_fade(w, h, 7), shape), GLOW)
        dot = mask(w, h, lambda d: via(d, x0 + notch * 0.5 + 4, y0 + notch * 0.5 + 4, 2.4, 0))
        return over(out, fill, paint(ring, GOLD_L), paint(dot, GOLD_L))

    def card(self, w, h, focused):
        box = (8, 11, w - 8, h - 7)
        return lean(self._focus(w, h, box, 9) if focused else self._slot(w, h, box, notch=9))

    def _fingers(self, im, focused, y0=232, y1=258):
        """An edge connector's gold fingers along the bottom of a tile."""
        def fn(d):
            for i in range(7):
                x = 30 + i * 14
                d.rounded_rectangle([S(x), S(y0), S(x + 8), S(y1)], radius=S(1.5), fill=255)
        m = mask(156, 278, fn)
        return over(im, paint(m, GOLD_L if focused else GOLD, 1.0 if focused else 0.42))

    BOX = (13, 12, 143, 266)

    def tile_base(self, focused):
        """bg-home-tile: the system row's tile (names at 142-204, the game count at 222)."""
        box = (8, 12, 148, 266)
        return lean(self._focus(156, 278, box, 12) if focused else self._slot(156, 278, box, notch=12))

    def _led(self, key, focused):
        """The tile's picture: its glyph on an LED lens in a gold pad ring; lit when focused."""
        w, h = 156, 278
        cx, cy = 78, 100
        c = LED[key]
        pad = mask(w, h, lambda d: via(d, cx, cy, 45, 39.5))
        lens = mask(w, h, lambda d: via(d, cx, cy, 38, 0))
        flat = mask(w, h, lambda d: d.rectangle([S(cx + 33), S(cy - 50), S(cx + 52), S(cy + 50)], fill=255))
        pad = ImageChops.subtract(pad, flat)
        g = canvas(w, h)
        TILES[key](ImageDraw.Draw(g), cx, cy, 22, (255, 255, 255, 255), 4.6)
        gm = finish(g).split()[3]
        if focused:
            core = mask(w, h, lambda d: via(d, cx - 8, cy - 9, 18, 0))
            return over(clear(w, h), paint(halo(lens, ((10, 1.6), (4, 1.0)), edge_fade(w, h, 8)), c, 0.9),
                        paint(pad, GOLD_L), paint(lens, c), paint(blur(core, 8), (255, 255, 255), 0.35),
                        paint(gm, (16, 30, 22)))
        dim = mix(c, BOARD_D, 0.62)
        return over(clear(w, h), paint(pad, GOLD, 0.85), paint(lens, dim), paint(gm, mix(c, SILK, 0.7)))

    def home_tile(self, key, focused):
        if key is None:
            return self.tile_base(focused)
        base = self._focus(156, 278, self.BOX, 12) if focused else self._slot(156, 278, self.BOX, notch=12)
        base = self._fingers(base, focused)
        return lean(over(base, self._led(key, focused)))

    # ---- buttons and small parts -----------------------------------------------------------
    def button(self, label, primary):
        n = 54
        f = self.font(27)
        if label in "AY":
            pad = rr_mask(n, n, (5, 5, 49, 49), 3)
        else:
            pad = mask(n, n, lambda d: via(d, 27, 27, 22.5, 0))
        col = GOLD if label in "AB" else TIN
        tm = text_mask(n, n, label, f, 27, 28)
        return over(clear(n, n), paint(pad, col), paint(tm, BOARD_D))

    def pill(self, label, w, h=48):
        """A small SOIC chip with its name on it."""
        body = rr_mask(w, h, (4, 11, w - 4, h - 11), 3)

        def legs(d):
            n = max(3, int((w - 16) / 11))
            step = (w - 20) / (n - 1)
            for i in range(n):
                x = 10 + i * step
                d.rectangle([S(x - 2), S(6), S(x + 2), S(h - 6)], fill=255)
        leg = ImageChops.subtract(mask(w, h, legs), body)
        tm = text_mask(w, h, label, self.font(16), w / 2, h / 2 + 0.5)
        return over(clear(w, h), paint(leg, GOLD), paint(body, CHIP), paint(tm, SILK))

    def dot(self, active):
        w, h = 24, 14
        led = rr_mask(w, h, (7, 4, 17, 10), 1.5)
        if active:
            return over(clear(w, h), paint(halo(led, ((2.5, 1.6),), edge_fade(w, h, 3)), GLOW), paint(led, GOLD_L),
                        paint(rr_mask(w, h, (9, 5.5, 15, 8.5), 1), (255, 250, 220)))
        return paint(led, mix(SILK_M, BOARD, 0.45))

    def toggle(self, on):
        w, h = 92, 44
        box = (8, 10, 84, 34)
        body = rr_mask(w, h, box, 4)
        ring = rr_mask(w, h, box, 4, 1.6)
        knob_box = (54, 13, 81, 31) if on else (11, 13, 38, 31)
        knob = rr_mask(w, h, knob_box, 2.5)
        out = over(clear(w, h), paint(body, (60, 34, 16) if on else CHIP),
                   paint(ring, SILK if on else SILK_M, 0.8 if on else 0.6))
        if on:
            out = over(paint(halo(ring, ((4, 1.4),), edge_fade(w, h, 6), body), GLOW), out)
        return over(out, paint(knob, GOLD_L if on else TIN))

    def arrow(self, left, size=24):
        s = size
        pts = [(0.24, 0.5), (0.72, 0.2), (0.72, 0.8)] if left else [(0.76, 0.5), (0.28, 0.2), (0.28, 0.8)]
        m = mask(s, s, lambda d: d.polygon([(S(x * s), S(y * s)) for x, y in pts], fill=255))
        return paint(m, GOLD_L)

    def panel_image(self, w, h):
        box = (3, 3, w - 3, h - 3)
        shape = rr_mask(w, h, box, 6)
        line = rr_mask(w, h, (7, 7, w - 7, h - 7), 3, 1.4)

        def corners(d):
            n = 12
            for x, y, sx, sy in ((7, 7, 1, 1), (w - 7, 7, -1, 1), (7, h - 7, 1, -1), (w - 7, h - 7, -1, -1)):
                d.line([(S(x), S(y + sy * n)), (S(x), S(y)), (S(x + sx * n), S(y))], fill=255, width=int(S(3)))
        tr = rr_mask(w, h, box, 6, 2)
        return over(paint(shape, (8, 40, 27)), paint(tr, GOLD, 0.9), paint(line, SILK, 0.35),
                    paint(mask(w, h, corners), SILK, 0.85))

    def folder_icon(self):
        n = 60
        def fn(d):
            d.rounded_rectangle([S(9), S(14), S(29), S(24)], radius=S(2), fill=255)
            d.rounded_rectangle([S(9), S(19), S(51), S(47)], radius=S(3), fill=255)
        m = mask(n, n, fn)
        inner = mask(n, n, lambda d: d.rounded_rectangle([S(12), S(25), S(48), S(44)], radius=S(2), fill=255))
        return over(clear(n, n), paint(m, SILK), paint(inner, GOLD))

    def favorite_mark(self):
        w, h = 34, 39
        pts = []
        for i in range(10):
            r = 14 if i % 2 == 0 else 6.2
            a = math.radians(-90 + i * 36)
            pts.append((17 + r * math.cos(a), 20 + r * math.sin(a)))
        m = mask(w, h, lambda d: d.polygon([(S(x), S(y)) for x, y in pts], fill=255))
        return over(paint(halo(m, ((2.5, 1.2),), edge_fade(w, h, 4)), GLOW, 0.7), paint(m, GOLD_L))

    def battery(self, level, charging=False):
        n = 48
        shell = rr_mask(n, n, (5, 15, 40, 33), 2.5, 2.2)
        tip = rr_mask(n, n, (40.5, 20, 44, 28), 1)
        out = over(clear(n, n), paint(shell, SILK), paint(tip, SILK))
        k = int(round(level * 4))
        if k:
            c = (255, 84, 70) if level <= 0.2 else GOLD_L
            cells = mask(n, n, lambda d: [d.rectangle([S(9 + i * 7.6), S(19), S(14.4 + i * 7.6), S(29)], fill=255)
                                           for i in range(k)])
            out = over(out, paint(cells, c))
        if charging:
            pts = [(26, 7), (15, 26), (22, 26), (19, 41), (32, 20), (25, 20)]
            b = mask(n, n, lambda d: d.polygon([(S(x), S(y)) for x, y in pts], fill=255))
            out = over(out, paint(b.filter(ImageFilter.MaxFilter(5)), BOARD_D), paint(b, GOLD_L))
        return out

    def preview_frame(self):
        w, h = 250, 360
        return self.panel_image(w, h)

    def key(self, focused):
        w, h = 52, 40
        box = (2, 2, w - 2, h - 2)
        if focused:
            return lean(self._pour(w, h, box, 3, glow=False, rim=1.6))
        return over(paint(rr_mask(w, h, box, 3), CHIP), paint(rr_mask(w, h, box, 3, 1.2), SILK, 0.35))

    def input_box(self):
        w, h = 560, 60
        box = (3, 3, w - 3, h - 3)
        return over(paint(rr_mask(w, h, box, 5), (6, 32, 22)), paint(rr_mask(w, h, box, 5, 1.8), GOLD))

    # ---- system and app icons --------------------------------------------------------------
    _boxes = {}

    def icon_box(self, sid):
        if sid not in self._boxes:
            lines, m = canvas(160, 160), Image.new("L", (160 * SS, 160 * SS), 0)
            (GLYPHS.get(sid) or GLYPHS["fallback"])(SilkPen(ImageDraw.Draw(lines), ImageDraw.Draw(m), 80, 80))
            x0, y0, x1, y1 = ImageChops.lighter(lines.split()[3], m).getbbox()
            self._boxes[sid] = (x0 / SS - 80, y0 / SS - 80, x1 / SS - 80, y1 / SS - 80)
        return self._boxes[sid]

    def icon_picture(self, sid, selected, cy):
        w, h = 120, 130
        bx0, by0, bx1, by1 = self.icon_box(sid)
        sc = min(1.2, 100 / (bx1 - bx0), 94 / (by1 - by0))
        cx = 60 - (bx0 + bx1) / 2 * sc
        cy = cy - (by0 + by1) / 2 * sc
        lines, soft = canvas(w, h), Image.new("L", (w * SS, h * SS), 0)
        (GLYPHS.get(sid) or GLYPHS["fallback"])(SilkPen(ImageDraw.Draw(lines), ImageDraw.Draw(soft), cx, cy, sc, 2.8))
        la = lines.split()[3].resize((w, h), Image.LANCZOS)
        sm = soft.resize((w, h), Image.LANCZOS)
        if selected:
            return over(clear(w, h), paint(sm, (40, 20, 8), 0.55), paint(la, (255, 255, 250)))
        return over(clear(w, h), paint(sm, GOLD, 0.9), paint(la, SILK))

    def system_icon(self, sid, selected):
        # (no name badge: MainUI writes the name under each picture)
        return self.icon_picture(sid, selected, 64)

    def app_icon(self, key):
        """An IC: a black package with gold pins, its glyph lit in its own colour."""
        n = 96
        c = APP_LED.get(key, LED["app"])
        body = rr_mask(n, n, (14, 14, 82, 82), 6)

        def pins(d):
            for i in range(5):
                t = 24 + i * 12
                d.rectangle([S(t - 2.5), S(5), S(t + 2.5), S(91)], fill=255)
                d.rectangle([S(5), S(t - 2.5), S(91), S(t + 2.5)], fill=255)
        pin = ImageChops.subtract(mask(n, n, pins), body)
        g = canvas(n, n)
        APPS[key](ImageDraw.Draw(g), n / 2, n / 2, 18, (255, 255, 255, 255), 4.4)
        gm = finish(g).split()[3]
        dot = mask(n, n, lambda d: via(d, 22, 22, 2.4, 0))
        return over(clear(n, n), paint(pin, GOLD), paint(body, CHIP), paint(dot, SILK, 0.6),
                    paint(halo(gm, ((3, 0.9),)), c, 0.8), paint(gm, mix(c, (255, 255, 255), 0.25)))

    # ---- sound and config -------------------------------------------------------------------
    def sound(self, path):
        """A relay tick and a short square-wave beep."""
        rate = 22050
        n = int(rate * 0.045)
        frames = bytearray()
        prev = 0.0
        for i in range(n):
            t = i / rate
            s = 0.6 if (t * 2400) % 1 < 0.5 else -0.6
            if t < 0.002:
                s += 0.8 * (1 - t / 0.002) * (1 if i % 3 else -1)
            prev += (s - prev) * 0.45
            env = min(1.0, t / 0.001) * math.exp(-t * 70)
            frames += struct.pack("<h", int(6500 * env * prev))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc((255, 255, 255))
        return cfg
