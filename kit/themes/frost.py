"""Frost: a frozen window pane. Frost ferns creep in from the corners of pale ice, panels are
frosted glass cut like crystal, icicles hang from the title bar; every menu picture is a cut
ice gem of its own cold hue, and the focused card turns to clear blue ice catching the light."""
import math
import random
import struct
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, BADGES, GLYPHS, SS, TILES, Pen, S, Style, canvas, finish, g_folder, hexc, rgba

NAVY = (16, 38, 72)
INK = (22, 58, 108)        # line art
SLATE = (66, 92, 124)      # unselected labels
EDGE = (128, 172, 212)     # frosted edges
ICE = (132, 194, 240)
DEEP = (40, 110, 192)      # accent
DEEPER = (28, 82, 156)
PALE = (218, 237, 252)
WHITE = (255, 255, 255)

CERULEAN = (56, 146, 222)
VIOLET = (128, 104, 222)
TEAL = (28, 156, 166)
INDIGO = (70, 84, 196)
MINT = (40, 176, 140)
LILAC = (178, 100, 196)
STEEL = (110, 132, 158)
HUES = [CERULEAN, VIOLET, TEAL, INDIGO, MINT, LILAC, STEEL]
TILE_HUE = {"recent": CERULEAN, "favorite": VIOLET, "game": TEAL, "emulators": INDIGO, "retroarch": MINT,
            "app": LILAC, "setting": STEEL}
APP_HUE = {"themes": LILAC, "pacman": TEAL, "gameswitcher": INDIGO, "search": CERULEAN, "gallery": MINT,
           "activity": VIOLET, "retroarch": MINT, "tweaks": STEEL, "download": CERULEAN, "folder": TEAL,
           "hidden": STEEL, "emulators": INDIGO, "category": LILAC, "updates": MINT, "repos": VIOLET}
BADGE_FIX = {"xbox": None, "segacd": "MD-CD"}


# ---- small image helpers ------------------------------------------------------------------

def shade(c, k):
    return tuple(max(0, min(255, int(round(v * k)))) for v in c[:3])


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _solid(w, h, c, a=255):
    return Image.new("RGBA", (w, h), rgba(c, a))


def _empty(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def _mask(im, m, k=1.0):
    out = im.copy()
    a = ImageChops.multiply(im.getchannel("A"), m)
    if k != 1.0:
        a = a.point(lambda v: min(255, int(v * k)))
    out.putalpha(a)
    return out


def _fade(im, k):
    return _mask(im, Image.new("L", im.size, 255), k)


def _over(*layers):
    out = layers[0]
    for l in layers[1:]:
        out = Image.alpha_composite(out, l)
    return out


def _blur(im, r):
    if im.mode == "RGBA":
        return im.convert("RGBa").filter(ImageFilter.GaussianBlur(r)).convert("RGBA")
    return im.filter(ImageFilter.GaussianBlur(r))


def _shift(im, dx, dy):
    out = Image.new(im.mode, im.size, 0 if im.mode == "L" else (0, 0, 0, 0))
    out.paste(im, (int(dx), int(dy)))
    return out


def _arr_img(rgb, alpha=None):
    h, w = rgb.shape[:2]
    a = np.full((h, w), 255.0) if alpha is None else alpha
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 255)]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _grid(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x + 0.5, y + 0.5


def _ramp_img(t, stops):
    stops = [(s, tuple(c) + (255,) * (4 - len(c))) for s, c in stops]
    ts = [s for s, _ in stops]
    ch = [np.interp(t, ts, [c[k] for _, c in stops]) for k in range(4)]
    return Image.fromarray(np.dstack(ch).round().astype(np.uint8), "RGBA")


def _radial(w, h, cx, cy, r, stops):
    x, y = _grid(w, h)
    return _ramp_img(np.clip(np.hypot(x - cx, y - cy) / r, 0, 1), stops)


def _linear(w, h, stops, fx=0.0, fy=1.0):
    x, y = _grid(w, h)
    t = fx * x / w + fy * y / h
    lo, hi = t.min(), t.max()
    return _ramp_img((t - lo) / max(1e-6, hi - lo), stops)


def poly_mask(w, h, pts, outline=0):
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    p = [(x * SS, y * SS) for x, y in pts]
    if outline:
        d.line(p + [p[0], p[1]], fill=255, width=max(1, int(outline * SS)), joint="curve")
    else:
        d.polygon(p, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def line_mask(w, h, pts, width):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).line([(x * SS, y * SS) for x, y in pts], fill=255, width=max(1, int(width * SS)), joint="curve")
    return m.resize((w, h), Image.LANCZOS)


def grow(m, px):
    if px == 0:
        return m
    b = m.filter(ImageFilter.GaussianBlur(abs(px) * 0.8))
    if px > 0:
        return b.point(lambda v: min(255, v * 4))
    return b.point(lambda v: max(0, (v - 191) * 4))


def silhouette(alpha, g=2):
    m = alpha.point(lambda v: 255 if v > 70 else 0)
    if g:
        m = m.filter(ImageFilter.GaussianBlur(g * 0.75)).point(lambda v: 255 if v > 28 else 0)
    pad = Image.new("L", (m.width + 2, m.height + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    filled = pad.point(lambda v: 0 if v == 128 else 255).crop((1, 1, m.width + 1, m.height + 1))
    return filled.filter(ImageFilter.GaussianBlur(0.6))


def _edge_fade(w, h, n=4):
    def prof(k):
        return [int(255 * max(0.0, min(1.0, min(i, k - 1 - i) / n))) for i in range(k)]
    hx, vy = Image.new("L", (w, 1)), Image.new("L", (1, h))
    hx.putdata(prof(w))
    vy.putdata(prof(h))
    return ImageChops.darker(hx.resize((w, h)), vy.resize((w, h)))


def kquant(im, n, seed=1, iters=6, sample=4000, gamma=0.6):
    """[im] reduced to at most [n] RGBA colours by k-means in premultiplied space: far
    smaller PNGs, while soft glows keep smooth alpha steps."""
    a = np.asarray(im.convert("RGBA"), dtype=np.float32).reshape(-1, 4)
    vis = a[:, 3] > 0
    ag = 255 * (a[vis, 3:4] / 255) ** gamma
    X = np.concatenate([a[vis, :3] * (ag / 255), ag], 1)
    if len(X) == 0:
        return im
    rng = np.random.default_rng(seed)
    smp = X[rng.choice(len(X), sample, replace=False)] if len(X) > sample else X
    k = min(n - 1, len(np.unique(smp, axis=0)))

    def nearest(P, C):
        out = np.empty(len(P), np.int64)
        for i in range(0, len(P), 40000):
            out[i:i + 40000] = ((P[i:i + 40000, None, :] - C[None, :, :]) ** 2).sum(2).argmin(1)
        return out
    C = [smp[rng.integers(len(smp))]]
    d2 = ((smp - C[0]) ** 2).sum(1)
    for _ in range(1, k):
        C.append(smp[rng.choice(len(smp), p=d2 / d2.sum())] if d2.sum() > 0 else smp[rng.integers(len(smp))])
        d2 = np.minimum(d2, ((smp - C[-1]) ** 2).sum(1))
    C = np.array(C)
    for _ in range(iters):
        lab = nearest(smp, C)
        cnt = np.bincount(lab, minlength=k)
        for c in range(4):
            sums = np.bincount(lab, weights=smp[:, c], minlength=k)
            C[:, c] = np.where(cnt > 0, sums / np.maximum(cnt, 1), C[:, c])
    agc = np.clip(C[:, 3], 1, 255)
    alpha = 255 * (agc / 255) ** (1 / gamma)
    pal = np.concatenate([np.clip(C[:, :3] * 255 / agc[:, None], 0, 255), alpha[:, None]], 1).round().astype(np.uint8)
    out = np.zeros(a.shape, dtype=np.uint8)
    out[vis] = pal[nearest(X, C)]
    return Image.fromarray(out.reshape(im.height, im.width, 4), "RGBA")


# ---- crystal shapes ---------------------------------------------------------------------------

def shard(box, big, small):
    """A crystal slab: a box with two opposite corners cut [big] and the other two [small]."""
    x0, y0, x1, y1 = box
    return [(x0 + big, y0), (x1 - small, y0), (x1, y0 + small), (x1, y1 - big), (x1 - big, y1), (x0 + small, y1),
            (x0, y1 - small), (x0, y0 + big)]


def hexagon(cx, cy, r, rot=-90):
    return [(cx + r * math.cos(math.radians(rot + 60 * i)), cy + r * math.sin(math.radians(rot + 60 * i))) for i in range(6)]


def bar_pts(box, cut):
    """A long bar with its four corners cut (pointed-ish ends)."""
    x0, y0, x1, y1 = box
    return [(x0 + cut, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1 - cut), (x1 - cut, y1), (x0 + cut, y1), (x0, y1 - cut), (x0, y0 + cut)]


def snowflake(d, cx, cy, r, c, w):
    """A six-armed snowflake with two pairs of side branches per arm (supersampled draw, 1x coords)."""
    for i in range(6):
        a = math.radians(-90 + 60 * i)
        ux, uy = math.cos(a), math.sin(a)
        d.line([S(cx), S(cy), S(cx + ux * r), S(cy + uy * r)], fill=c, width=max(1, int(w * SS)))
        for t, L in ((0.42, 0.32), (0.7, 0.24)):
            px, py = cx + ux * r * t, cy + uy * r * t
            for s in (-1, 1):
                b = a + s * math.radians(55)
                d.line([S(px), S(py), S(px + math.cos(b) * r * L), S(py + math.sin(b) * r * L)], fill=c,
                       width=max(1, int(w * 0.85 * SS)))
    rr = r * 0.16
    d.polygon([(S(x), S(y)) for x, y in hexagon(cx, cy, rr)], fill=c)


def fern(d, rnd, x, y, ang, length, width, depth, col):
    """A frost fern: a gently curving stem with feathered side branches (supersampled draw)."""
    n = max(3, int(length / 2.5))
    bend = rnd.uniform(-0.35, 0.35)
    pts = [(x, y)]
    a = ang
    for i in range(n):
        a += bend / n + rnd.uniform(-0.04, 0.04)
        x += math.cos(a) * length / n
        y += math.sin(a) * length / n
        pts.append((x, y))
    for i in range(n):
        wv = max(0.35, width * (1 - i / n * 0.8))
        d.line([S(pts[i][0]), S(pts[i][1]), S(pts[i + 1][0]), S(pts[i + 1][1])], fill=col, width=max(1, int(wv * SS)))
    if depth <= 0:
        return
    step = max(2, int(n / (7 if depth > 1 else 6)))
    side = 1
    for i in range(step, n - 1, step):
        t = i / n
        (px, py), (qx, qy) = pts[i], pts[i + 1]
        heading = math.atan2(qy - py, qx - px)
        sub = length * (1 - t) * rnd.uniform(0.32, 0.46)
        for s in ((-1, 1) if depth > 1 else (side,)):
            fern(d, rnd, px, py, heading + s * math.radians(rnd.uniform(52, 64)), sub, width * 0.6, depth - 1, col)
        side = -side


class Theme(Style):
    name = "Frost"
    author = "MainUI"
    description = "A frozen window pane: frost ferns on pale ice, crystal-cut frosted panels and cold gem icons that turn to clear blue ice."

    bg_top = (214, 234, 250)
    bg_bottom = (226, 240, 252)   # light, so MainUI's own fallbacks pick dark ink
    accent = DEEP
    accent2 = DEEPER
    highlight = DEEP
    text = NAVY
    muted = SLATE
    glyph_n = INK
    glyph_f = NAVY
    panel = (218, 234, 249)
    panel_alpha = 255
    bar = WHITE
    bar_alpha = 225

    font_file = "TenorSans-Regular.ttf"
    font_license = "OFL-TenorSans.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 28, 26, 24, 22, 16, 17

    icon_quant = 64
    sel_icons = False

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc((8, 28, 60))
        return cfg

    # ---- background ------------------------------------------------------------------------
    def background(self, w=640, h=480):
        rnd = random.Random(31)
        x, y = _grid(w, h)
        # pale ice, deeper blue towards the corners where the frost grows
        t = np.clip(np.hypot((x - w * 0.5) / (w * 0.6), (y - h * 0.5) / (h * 0.62)), 0, 1.35) / 1.35
        t = t ** 1.5
        c0 = np.array([240, 247, 254], np.float32)
        c1 = np.array([128, 178, 226], np.float32)
        rgb = c0 * (1 - t[..., None]) + c1 * t[..., None]
        # a broad cold sheen across the pane
        band = np.exp(-(((x * 0.55 + y) - 300) / 120) ** 2) * 8
        rgb = rgb + band[..., None]
        bg = _arr_img(rgb)

        # hairline fractures along the ice's crystal axes
        cr = canvas(w, h)
        cd = ImageDraw.Draw(cr)
        for _ in range(16):
            ang = math.radians(rnd.choice((0, 60, 120)) + rnd.uniform(-4, 4))
            px, py = rnd.uniform(0, w), rnd.uniform(60, h - 60)
            ln = rnd.uniform(60, 200)
            if 330 < py + math.sin(ang) * ln * 0.5 < 420:
                continue
            qx, qy = px + math.cos(ang) * ln, py + math.sin(ang) * ln
            cd.line([S(px), S(py), S(qx), S(qy)], fill=(255, 255, 255, 255), width=int(1.0 * SS))
            for _ in range(rnd.randint(0, 2)):
                k = rnd.uniform(0.2, 0.8)
                bx, by = px + (qx - px) * k, py + (qy - py) * k
                b2 = ang + math.radians(rnd.choice((-60, 60)))
                l2 = ln * rnd.uniform(0.15, 0.35)
                cd.line([S(bx), S(by), S(bx + math.cos(b2) * l2), S(by + math.sin(b2) * l2)], fill=(255, 255, 255, 255), width=int(0.8 * SS))
        crack = finish(cr).getchannel("A")
        bg = _over(bg, _shift(_mask(_solid(w, h, (90, 140, 200)), crack, 0.18), 1, 1), _mask(_solid(w, h, WHITE), crack, 0.5))

        # frost ferns from the corners and edges
        fr = canvas(w, h)
        fd = ImageDraw.Draw(fr)
        col = (255, 255, 255, 255)
        seeds = [(-6, -6, 38, 190), (-6, 70, 12, 120), (80, -6, 78, 110), (-6, 170, -5, 80),
                 (w + 6, -6, 142, 190), (w + 6, 80, 168, 120), (w - 90, -6, 102, 105), (w + 6, 190, 185, 80),
                 (-6, h + 6, -38, 190), (90, h + 6, -82, 105), (-6, h - 90, -12, 120), (-6, h - 190, 5, 70),
                 (w + 6, h + 6, -142, 190), (w - 95, h + 6, -98, 110), (w + 6, h - 85, -168, 120), (w + 6, h - 200, 175, 70)]
        for sx, sy, ang, ln in seeds:
            fern(fd, rnd, sx, sy, math.radians(ang + rnd.uniform(-6, 6)), ln * rnd.uniform(0.9, 1.1), 2.4, 2, col)
        ferns = finish(fr)
        fa = ferns.getchannel("A")
        bg = _over(bg, _shift(_mask(_solid(w, h, (60, 110, 175)), fa, 0.3), 1, 1),
                   _mask(_solid(w, h, WHITE), _blur(fa, 3), 0.7), _mask(_solid(w, h, WHITE), fa, 0.92))

        # a few snowflakes, kept to the edges
        sf = canvas(w, h)
        sd = ImageDraw.Draw(sf)
        spots = [(212, 78, 6), (452, 74, 5), (586, 236, 7), (30, 250, 5.5), (606, 330, 4.5), (300, 452, 6),
                 (520, 446, 4.5), (150, 446, 5), (560, 120, 4), (64, 150, 4)]
        for fx, fy, r in spots:
            snowflake(sd, fx, fy, r, (255, 255, 255, 255), 1.1)
        flakes = finish(sf)
        bg = _over(bg, _shift(_mask(_solid(w, h, (80, 130, 190)), flakes.getchannel("A"), 0.45), 1, 1), flakes)
        return bg

    # ---- bars ----------------------------------------------------------------------------
    def header_bar(self):
        """Frosted glass with icicles hanging from its lower edge."""
        w, h = 640, 60
        rnd = random.Random(5)
        y0 = 45
        body = _linear(w, h, [(0, (255, 255, 255, 226)), (1, (240, 248, 254, 216))])
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rectangle((0, 0, w, y0), fill=255)
        layers = [_mask(body, m)]
        ic = canvas(w, h)
        idr = ImageDraw.Draw(ic)
        hi = canvas(w, h)
        hd = ImageDraw.Draw(hi)
        xx = 4.0
        while xx < w - 4:
            cluster = rnd.randint(2, 4)
            for j in range(cluster):
                iw = rnd.uniform(4.0, 7.0)
                il = rnd.uniform(7.0, 14.0) if j % 2 == 0 else rnd.uniform(3.5, 8.0)
                cx = xx + iw / 2
                tip = (cx + iw * 0.08, y0 + il)
                side = [(xx + (tip[0] - xx) * u + iw * 0.12 * math.sin(math.pi * u), y0 + il * u ** 1.25) for u in (0, 0.25, 0.5, 0.75, 1)]
                side2 = [(xx + iw + (tip[0] - xx - iw) * u - iw * 0.12 * math.sin(math.pi * u), y0 + il * u ** 1.25) for u in (1, 0.75, 0.5, 0.25, 0)]
                idr.polygon([(S(px), S(py)) for px, py in side + side2], fill=(255, 255, 255, 255))
                hd.line([S(xx + iw * 0.3), S(y0 + 0.5), S(cx), S(y0 + il * 0.8)], fill=(255, 255, 255, 255), width=SS)
                xx += iw + rnd.uniform(-0.6, 1.2)
            xx += rnd.uniform(14, 40)
        ice = finish(ic).getchannel("A")
        ice_fill = _linear(w, h, [(0.76, (214, 236, 254, 245)), (1.0, (130, 186, 236, 235))])
        edge = ImageChops.subtract(grow(ice, 0.8), ice)
        layers += [_shift(_mask(_solid(w, h, (50, 100, 165)), _blur(ice, 1.0), 0.3), 0, 1.5), _mask(ice_fill, ice),
                   _mask(_solid(w, h, (98, 150, 205)), edge, 0.7), _mask(_solid(w, h, WHITE), finish(hi).getchannel("A"), 0.9)]
        e = canvas(w, h)
        ImageDraw.Draw(e).line([0, S(y0 - 0.2), S(w), S(y0 - 0.2)], fill=rgba(EDGE, 230), width=int(1.3 * SS))
        layers.append(finish(e))
        return _over(*layers)

    def footer_bar(self):
        """A bank of snow: a soft drifted top edge over frosted white."""
        w, h = 640, 60
        rnd = random.Random(9)
        ph = [rnd.uniform(0, 6.28) for _ in range(3)]
        top = [(x, 5.2 + 2.0 * math.sin(x / 47 + ph[0]) + 1.3 * math.sin(x / 19 + ph[1]) + 0.6 * math.sin(x / 7 + ph[2]))
               for x in range(-2, w + 4, 2)]
        m = poly_mask(w, h, top + [(w + 4, h + 2), (-2, h + 2)])
        body = _linear(w, h, [(0, (255, 255, 255, 236)), (1, (238, 246, 253, 226))])
        under = _shift(m, 0, -1)
        shade_ = ImageChops.subtract(_shift(m, 0, 1), _shift(m, 0, 5))
        crest = line_mask(w, h, top, 1.3)
        return _over(_mask(_solid(w, h, (60, 110, 175)), _blur(ImageChops.subtract(under, m), 1.2), 0.55),
                     _mask(body, m), _mask(_solid(w, h, (176, 210, 240)), ImageChops.multiply(_blur(shade_, 1.5), m), 0.8),
                     _mask(_solid(w, h, WHITE), crest, 0.9))

    def logo(self):
        w, h = 160, 42
        sf = canvas(w, h)
        snowflake(ImageDraw.Draw(sf), 19, 21, 16, (255, 255, 255, 255), 2.3)
        a = finish(sf).getchannel("A")
        flake = _mask(_linear(w, h, [(0.15, (120, 196, 250)), (0.85, DEEPER)], 0.6, 1), a)
        t = canvas(w, h)
        ImageDraw.Draw(t).text((S(44), S(22)), "Frost", font=self.font(27), fill=rgba(NAVY), anchor="lm")
        return _over(_empty(w, h), _mask(_solid(w, h, WHITE), _blur(a, 1.5), 0.9), flake, finish(t))

    # ---- lists -----------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        box = (5, 5, w - 5, h - 5)
        cut = 9 if h < 70 else 14
        pts = bar_pts(box, cut)
        shape = poly_mask(w, h, pts)
        body = _linear(w, h, [(0, (196, 228, 252)), (0.55, (176, 214, 246)), (1, (160, 202, 242))], 1, 0.15)
        sheen = _linear(w, h, [(0, (255, 255, 255, 120)), (0.5, (255, 255, 255, 0))], 0, 1)
        streaks = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(streaks)
        for x0, ww in ((26, 26), (60, 8), (560, 14)):
            sd.polygon([(x0, 0), (x0 + ww, 0), (x0 + ww - h * 0.6, h), (x0 - h * 0.6, h)], fill=255)
        glow = _mask(_blur(_mask(_solid(w, h, DEEP), shape), 3), _edge_fade(w, h), 0.35)
        rim = _mask(_solid(w, h, DEEP), poly_mask(w, h, pts, 1.5))
        inner = _mask(_solid(w, h, WHITE), poly_mask(w, h, bar_pts((box[0] + 2.5, box[1] + 2.5, box[2] - 2.5, box[3] - 2.5), cut - 1.5), 1.0), 0.75)
        out = _over(_empty(w, h), glow, _mask(body, shape), _mask(sheen, shape),
                    _mask(_solid(w, h, WHITE), ImageChops.multiply(streaks, shape), 0.22), inner, rim)
        return kquant(out, 96)

    def divider(self):
        w, h = 640, 4
        im = canvas(w, h)
        ImageDraw.Draw(im).line([S(20), S(2), S(620), S(2)], fill=rgba(EDGE, 150), width=int(1.0 * SS))
        m = Image.new("L", (w, 1))
        m.putdata([int(255 * max(0.0, min(1.0, (x - 20) / 120, (620 - x) / 120))) for x in range(w)])
        return _mask(finish(im), m.resize((w, h)))

    # ---- panels and tiles -------------------------------------------------------------------
    def slab(self, w, h, pts, focused, glow=5, glint=True, quiet_band=None, bevel=5.0):
        """Frosted glass cut like a crystal slab, its bevelled edges catching light from the
        upper left; focused, clear blue ice with a glint."""
        shape = poly_mask(w, h, pts)
        rim = poly_mask(w, h, pts, 1.5)
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        layers = [_empty(w, h)]
        if focused:
            halo = _over(_fade(_blur(_mask(_solid(w, h, (90, 170, 245)), shape), glow), 0.9),
                         _shift(_fade(_blur(_mask(_solid(w, h, (30, 70, 140)), shape), glow * 0.6), 0.35), 0, 2))
            layers.append(_mask(halo, _edge_fade(w, h)))
            layers.append(_mask(_linear(w, h, [(0, (172, 224, 252)), (0.55, (122, 186, 240)), (1, (84, 152, 226))], 0.25, 1), shape))
            # facets: a few big planes inside the ice catching more or less light, with bright seams
            fac = canvas(w, h)
            fd = ImageDraw.Draw(fac)
            planes = [([(x0, y0), (x1, y0), (x0, y0 + (y1 - y0) * 0.42)], (255, 255, 255, 56)),
                      ([(x1, y0 + (y1 - y0) * 0.28), (x1, y1), (x0 + (x1 - x0) * 0.45, y1)], (20, 60, 130, 34)),
                      ([(x0, y0 + (y1 - y0) * 0.62), (x0 + (x1 - x0) * 0.45, y1), (x0, y1)], (255, 255, 255, 34))]
            for poly_, c in planes:
                fd.polygon([(S(px), S(py)) for px, py in poly_], fill=c)
            for poly_, c in planes:
                fd.line([(S(px), S(py)) for px, py in poly_ + poly_[:1]], fill=(255, 255, 255, 80), width=int(0.9 * SS))
            layers.append(_mask(finish(fac), grow(shape, -2)))
            if quiet_band:
                qb = Image.new("L", (w, h), 0)
                ImageDraw.Draw(qb).rectangle((0, quiet_band[0], w, quiet_band[1]), fill=255)
                layers.append(_mask(_solid(w, h, (146, 202, 244)), ImageChops.multiply(_blur(qb, 4), shape), 0.5))
            gl = Image.new("L", (w, h), 0)
            ImageDraw.Draw(gl).polygon([(x0 + (x1 - x0) * 0.55, y0), (x0 + (x1 - x0) * 0.68, y0),
                                        (x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.5), (x0 + (x1 - x0) * 0.07, y0 + (y1 - y0) * 0.5)], fill=255)
            gl = ImageChops.multiply(_blur(gl, 2), _linear(w, h, [(0, (255,)), (1, (0,))]).getchannel("R"))
            layers.append(_mask(_solid(w, h, WHITE), ImageChops.multiply(gl, shape), 0.35))
        else:
            layers.append(_shift(_mask(_solid(w, h, (60, 110, 170)), _blur(shape, 3), 0.26), 0, 2))
            layers.append(_mask(_linear(w, h, [(0, (255, 255, 255, 234)), (1, (236, 245, 253, 228))], 0.2, 1), shape))
        if bevel:
            layers.append(self.bevel(w, h, pts, bevel, 1.25 if focused else 1.0))
        layers.append(_mask(_solid(w, h, DEEP if focused else EDGE), rim))
        if focused and glint:
            sp = canvas(w, h)
            gx, gy = pts[1][0] - 3, pts[1][1] + 9
            _sparkle(ImageDraw.Draw(sp), gx, gy, min(9, w * 0.07), (255, 255, 255, 255))
            sp = finish(sp)
            layers += [_mask(_solid(w, h, WHITE), _blur(sp.getchannel("A"), 2.5), 1.2), sp]
        return _over(*layers)

    def bevel(self, w, h, pts, width, k=1.0):
        """The cut edge of a slab: one facet per side, lit or shaded by which way it faces."""
        n = len(pts)
        normals, lines = [], []
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            L = math.hypot(bx - ax, by - ay)
            dx, dy = (bx - ax) / L, (by - ay) / L
            nx, ny = -dy, dx        # inward (clockwise on screen)
            normals.append((nx, ny))
            lines.append((ax + nx * width, ay + ny * width, dx, dy))
        inner = []
        for i in range(n):
            px, py, dx, dy = lines[i - 1]
            qx, qy, ex, ey = lines[i]
            den = dx * ey - dy * ex
            t = ((qx - px) * ey - (qy - py) * ex) / den if abs(den) > 1e-6 else 0
            inner.append((px + dx * t, py + dy * t))
        lx, ly = -0.55, -0.83
        out = canvas(w, h)
        d = ImageDraw.Draw(out)
        for i in range(n):
            nx, ny = normals[i]
            lit = -(nx * lx + ny * ly)
            quad = [pts[i], pts[(i + 1) % n], inner[(i + 1) % n], inner[i]]
            c = (255, 255, 255, int(min(255, 150 * lit * k))) if lit > 0 else (50, 100, 170, int(min(255, -70 * lit * k)))
            d.polygon([(S(x), S(y)) for x, y in quad], fill=c)
        ring = canvas(w, h)
        ImageDraw.Draw(ring).line([(S(x), S(y)) for x, y in inner + inner[:1]], fill=(255, 255, 255, int(110 * k)), width=SS)
        return _over(finish(out), finish(ring))

    def card(self, w, h, focused):
        if (w, h) == (155, 170):
            return kquant(self.slab(w, h, shard((6, 6, 149, 164), 13, 4), focused, glow=4, quiet_band=(136, 160)), 96)
        big, small = (14, 5) if min(w, h) > 80 else (8, 3)
        return kquant(self.slab(w, h, shard((5, 5, w - 5, h - 5), big, small), focused, glow=3, glint=min(w, h) > 80), 96)

    def tile_base(self, focused):
        w, h = 156, 278
        pts = shard((9, 9, 147, 266), 18, 6)
        return self.slab(w, h, pts, focused, glow=5, quiet_band=(180, 210), bevel=6)

    def gem(self, w, h, cx, cy, R, color, focused, glyph=None, gsize=23, gw=4.2):
        """A cut ice gem: a hexagonal table ringed by six facets lit from the upper left,
        the picture etched white on the table (w x h layer)."""
        col = color if focused else mix(color, (236, 246, 255), 0.12)
        layers = [_empty(w, h)]
        outer = hexagon(cx, cy, R)
        tr = R * 0.66
        table = hexagon(cx, cy, tr)
        om = poly_mask(w, h, outer)
        if focused:
            layers.append(_mask(_blur(_mask(_solid(w, h, (255, 255, 255)), om), 6), _edge_fade(w, h), 1.3))
        else:
            layers.append(_shift(_mask(_solid(w, h, (40, 80, 140)), _blur(om, 2.5), 0.3), 0, 2))
        layers.append(_mask(_solid(w, h, shade(col, 0.6)), om))
        light = math.radians(-125)
        for i in range(6):
            a, b = outer[i], outer[(i + 1) % 6]
            c, d = table[(i + 1) % 6], table[i]
            mid = math.radians(-90 + 60 * i + 30)
            k = 1.0 + 0.32 * math.cos(mid - light)
            fm = grow(poly_mask(w, h, [a, b, c, d]), -0.5)
            fc = shade(col, k) if k <= 1 else mix(col, WHITE, (k - 1) * 0.9)
            layers.append(_mask(_solid(w, h, fc), fm))
        tm = grow(poly_mask(w, h, table), -0.5)
        layers.append(_mask(_radial(w, h, cx - tr * 0.4, cy - tr * 0.5, tr * 2.0,
                                    [(0, mix(col, WHITE, 0.32 if focused else 0.22)), (1, shade(col, 0.92))]), tm))
        # crisp light on the table's upper edges
        e = canvas(w, h)
        ed = ImageDraw.Draw(e)
        for i in (3, 4, 5):
            p, q = table[i], table[(i + 1) % 6]
            ed.line([S(p[0]), S(p[1]), S(q[0]), S(q[1])], fill=(255, 255, 255, 200), width=int(1.1 * SS))
        ed.line([S(outer[4][0]), S(outer[4][1]), S(outer[5][0]), S(outer[5][1])], fill=(255, 255, 255, 170), width=int(1.2 * SS))
        layers.append(finish(e))
        layers.append(_mask(_solid(w, h, shade(col, 0.45)), poly_mask(w, h, outer, 1.4)))
        if glyph is not None:
            g = canvas(w, h)
            glyph(ImageDraw.Draw(g), cx, cy, gsize, (255, 255, 255, 255), gw)
            ga = finish(g).getchannel("A")
            layers += [_shift(_mask(_solid(w, h, shade(col, 0.4)), _blur(ga, 1.0), 0.7), 0, 1), _mask(_solid(w, h, WHITE), ga)]
        if focused:
            sp = canvas(w, h)
            _sparkle(ImageDraw.Draw(sp), outer[5][0] - 2, outer[5][1] + 4, R * 0.24, (255, 255, 255, 255))
            sp = finish(sp)
            layers += [_mask(_solid(w, h, WHITE), _blur(sp.getchannel("A"), 2), 1.0), sp]
        return _over(*layers)

    def tile_glyph(self, key, focused):
        w, h = 156, 278
        col = TILE_HUE[key]
        # a small snowflake of the gem's hue under the label
        sf = canvas(w, h)
        snowflake(ImageDraw.Draw(sf), 78, 238, 9, (255, 255, 255, 255), 1.6)
        sa = finish(sf).getchannel("A")
        flake = _over(_mask(_solid(w, h, WHITE), grow(sa, 1.2), 0.9 if focused else 0.0), _mask(_solid(w, h, shade(col, 0.85 if focused else 1.0)), sa, 0.95))
        return _over(flake, self.gem(w, h, 78, 112, 54, col, focused, TILES[key], 23, 4.3))

    def home_tile(self, key, focused):
        base = self.tile_base(focused)
        return kquant(_over(base, self.tile_glyph(key, focused)) if key else base, 96)

    # ---- buttons and small parts ------------------------------------------------------------
    def button(self, label, primary):
        n = 54
        hx = hexagon(n / 2, n / 2, 24, rot=0)
        hm = poly_mask(n, n, hx)
        t = canvas(n, n)
        ImageDraw.Draw(t).text((S(n / 2), S(n / 2 + 0.5)), label, font=self.font(24), fill=(255, 255, 255, 255), anchor="mm")
        ta = finish(t).getchannel("A")
        sh = _shift(_mask(_solid(n, n, (40, 80, 140)), _blur(hm, 1.5), 0.35), 0, 1.5)
        if primary:
            body = _linear(n, n, [(0, (96, 168, 236)), (1, DEEPER)], 0.3, 1)
            return _over(_empty(n, n), sh, _mask(body, hm),
                         _mask(_solid(n, n, WHITE), ImageChops.subtract(grow(hm, -1.6), grow(hm, -2.8)), 0.6),
                         _mask(_solid(n, n, WHITE), ta))
        body = _linear(n, n, [(0, (255, 255, 255)), (1, (226, 240, 252))], 0, 1)
        return _over(_empty(n, n), sh, _mask(body, hm), _mask(_solid(n, n, DEEP), poly_mask(n, n, hx, 1.6)),
                     _mask(_solid(n, n, NAVY), ta))

    def pill(self, label, w, h=48):
        box = (3, 10, w - 3, h - 10)
        pts = bar_pts(box, 6)
        m = poly_mask(w, h, pts)
        t = canvas(w, h)
        ImageDraw.Draw(t).text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(14), fill=rgba(NAVY), anchor="mm")
        return _over(_shift(_mask(_solid(w, h, (40, 80, 140)), _blur(m, 1.2), 0.3), 0, 1), _mask(_solid(w, h, WHITE), m),
                     _mask(_solid(w, h, DEEP), poly_mask(w, h, pts, 1.3)), finish(t))

    def dot(self, active):
        w, h = 20, 18
        if active:
            pts = [(10, 1.5), (16.5, 9), (10, 16.5), (3.5, 9)]
            m = poly_mask(w, h, pts)
            hl = poly_mask(w, h, [(10, 1.5), (16.5, 9), (10, 9), (3.5, 9)])
            return _over(_empty(w, h), _mask(_solid(w, h, DEEP), m), _mask(_solid(w, h, (120, 190, 245)), hl, 0.9),
                         _mask(_solid(w, h, DEEPER), poly_mask(w, h, pts, 1.0)))
        pts = [(10, 4.5), (14, 9), (10, 13.5), (6, 9)]
        return _over(_empty(w, h), _mask(_solid(w, h, WHITE), poly_mask(w, h, pts), 0.9), _mask(_solid(w, h, (98, 140, 186)), poly_mask(w, h, pts, 1.2)))

    def toggle(self, on):
        w, h = 92, 44
        box = (8, 11, w - 8, h - 11)
        pts = bar_pts(box, 6)
        tm = poly_mask(w, h, pts)
        kr = 13
        kx = box[2] - 9 if on else box[0] + 9
        km = poly_mask(w, h, hexagon(kx, h / 2, kr, rot=0))
        if on:
            track = _over(_mask(_linear(w, h, [(0, (110, 182, 240)), (1, DEEP)], 0, 1), tm), _mask(_solid(w, h, DEEPER), poly_mask(w, h, pts, 1.2)))
        else:
            track = _over(_mask(_solid(w, h, (214, 228, 242)), tm), _mask(_solid(w, h, (140, 168, 198)), poly_mask(w, h, pts, 1.2)))
        knob = _over(_shift(_mask(_solid(w, h, (30, 70, 130)), _blur(km, 1.5), 0.4), 0, 1.5), _mask(_solid(w, h, WHITE), km),
                     _mask(_solid(w, h, DEEP if on else (130, 160, 192)), poly_mask(w, h, hexagon(kx, h / 2, kr, rot=0), 1.3)))
        return _over(_empty(w, h), track, knob)

    def arrow(self, left, size=24):
        im = canvas(size, size)
        d = ImageDraw.Draw(im)
        xs = (0.62, 0.32) if left else (0.38, 0.68)
        d.line([(S(size * xs[0]), S(size * 0.2)), (S(size * xs[1]), S(size * 0.5)), (S(size * xs[0]), S(size * 0.8))],
               fill=rgba(NAVY), width=int(size * 0.12 * SS), joint="curve")
        return finish(im)

    def panel_image(self, w, h):
        menu = w == 400
        pts = [(0, 0), (w, 0), (w, h - 12), (w - 12, h), (12, h), (0, h - 12)] if menu else shard((2, 2, w - 2, h - 2), 18, 6)
        shape = poly_mask(w, h, pts)
        body = _linear(w, h, [(0, (252, 254, 255)), (1, (234, 244, 252))], 0, 1)
        layers = [_empty(w, h), _mask(body, shape)]
        # a large faint snowflake in the corner, cut by the panel
        sf = canvas(w, h)
        R = min(80, h * 0.7)
        snowflake(ImageDraw.Draw(sf), w - R * 0.55, h - R * 0.5, R, (255, 255, 255, 255), 5)
        layers.append(_mask(_solid(w, h, (196, 222, 246)), ImageChops.multiply(finish(sf).getchannel("A"), shape), 0.75))
        layers.append(_mask(_solid(w, h, WHITE), ImageChops.subtract(grow(shape, -1.8), grow(shape, -3.0)), 0.9))
        rim = poly_mask(w, h, pts, 1.6)
        if menu:   # MainUI's title band sits right on top
            ImageDraw.Draw(rim).rectangle((0, 0, w, 1), fill=0)
        layers.append(_mask(_solid(w, h, DEEP), rim))
        return _over(*layers)

    def folder_icon(self):
        n = 60
        im = canvas(n, n)
        g_folder(ImageDraw.Draw(im), 30, 31, 19, (255, 255, 255, 255), 3.2)
        a = finish(im).getchannel("A")
        sil = silhouette(a, 1)
        return _over(_empty(n, n), _mask(_linear(n, n, [(0, (226, 242, 255)), (1, (168, 210, 244))]), sil), _mask(_solid(n, n, INK), a))

    def favorite_mark(self):
        w, h = 34, 39
        pts = []
        for i in range(12):
            rr = 15.5 if i % 2 == 0 else 7.2
            a = math.radians(-90 + i * 30)
            pts.append((17 + rr * math.cos(a), 20 + rr * math.sin(a)))
        m = poly_mask(w, h, pts)
        lit = poly_mask(w, h, [(17, 20)] + pts[9:] + pts[:2])
        return _over(_empty(w, h), _mask(_linear(w, h, [(0, (150, 205, 250)), (1, (70, 120, 220))], 0.3, 1), m),
                     _mask(_solid(w, h, WHITE), ImageChops.multiply(lit, m), 0.45), _mask(_solid(w, h, DEEPER), poly_mask(w, h, pts, 1.1)))

    def battery(self, level, charging=False):
        n = 48
        pts = bar_pts((6, 15, 40, 33), 3)
        layers = [_empty(n, n), _mask(_solid(n, n, NAVY), poly_mask(n, n, pts, 2.0)),
                  _mask(_solid(n, n, NAVY), poly_mask(n, n, [(40.5, 20.5), (44, 21.5), (44, 26.5), (40.5, 27.5)]))]
        if level > 0:
            fm = poly_mask(n, n, bar_pts((9.5, 18.5, 9.5 + 27 * level, 29.5), 1.5))
            fill = _solid(n, n, (224, 72, 84)) if level <= 0.2 else _linear(n, n, [(0, (110, 186, 244)), (1, DEEP)], 0, 1)
            layers.append(_mask(fill, fm))
        if charging:
            b = poly_mask(n, n, [(26, 10), (16, 26), (23, 26), (20, 38), (31, 21), (24, 21)])
            layers += [_mask(_solid(n, n, WHITE), grow(b, 1.6)), _mask(_solid(n, n, NAVY), b)]
        return _over(*layers)

    def preview_frame(self):
        w, h = 250, 360
        pts = shard((1, 1, w - 1, h - 1), 14, 5)
        return _over(_mask(_solid(w, h, WHITE), poly_mask(w, h, pts)), _mask(_solid(w, h, DEEP), poly_mask(w, h, pts, 1.8)))

    def key(self, focused):
        w, h = 52, 38
        pts = shard((2, 2, w - 2, h - 3), 7, 3)
        m = poly_mask(w, h, pts)
        if focused:
            body = _linear(w, h, [(0, (150, 208, 248)), (1, (96, 164, 230))])
            edge = DEEP
        else:
            body = _linear(w, h, [(0, (255, 255, 255)), (1, (232, 242, 251))])
            edge = EDGE
        return _over(_shift(_mask(_solid(w, h, (40, 80, 140)), _blur(m, 1.2), 0.3), 0, 1), _mask(body, m),
                     _mask(_solid(w, h, edge), poly_mask(w, h, pts, 1.3)))

    def input_box(self):
        w, h = 560, 60
        pts = bar_pts((2, 3, w - 2, h - 3), 10)
        return _over(_mask(_solid(w, h, WHITE), poly_mask(w, h, pts)), _mask(_solid(w, h, DEEP), poly_mask(w, h, pts, 1.8)))

    # ---- system and app icons ---------------------------------------------------------------
    def icon_picture(self, sid, selected, cy):
        w, h = 120, 130
        im = canvas(w, h)
        pen = Pen(ImageDraw.Draw(im), 60, cy, rgba(INK), SS, w=3.0)
        pen.soft_c = rgba(ICE, 140)
        (GLYPHS.get(sid) or GLYPHS["fallback"])(pen)
        lines = finish(im)
        sil = silhouette(lines.getchannel("A"), 2)
        hue = HUES[sum(ord(c) * (i + 1) for i, c in enumerate(sid)) % len(HUES)]
        top, bot = mix(hue, WHITE, 0.74), mix(hue, WHITE, 0.48)
        fill = _linear(w, h, [(0.2, top), (0.75, bot)], 0.3, 1)
        return _over(_empty(w, h), _shift(_mask(_solid(w, h, (40, 80, 140)), _blur(sil, 1.5), 0.25), 0, 1.5),
                     _mask(fill, sil), _mask(_solid(w, h, WHITE), ImageChops.subtract(sil, _shift(sil, 1.2, 1.2)), 0.7), lines)

    def badge(self, label, selected):
        w, h = 120, 130
        f = self.font(13)
        t = canvas(w, h)
        d = ImageDraw.Draw(t)
        tw = d.textlength(label, font=f) / SS
        bw = min(116, tw + 18)
        x0 = (w - bw) / 2
        box = (x0, 105, x0 + bw, 126)
        d.text((S(w / 2), S(115.8)), label, font=f, fill=(255, 255, 255, 255), anchor="mm")
        m = poly_mask(w, h, bar_pts(box, 5))
        return _over(_mask(_linear(w, h, [(0.78, (56, 124, 200)), (1, DEEPER)], 0, 1), m), finish(t))

    def system_icon(self, sid, selected):
        label = BADGE_FIX[sid] if sid in BADGE_FIX else BADGES.get(sid, sid[:7].upper())
        out = self.icon_picture(sid, selected, 52 if label else 62)
        return _over(out, self.badge(label, selected)) if label else out

    def app_icon(self, key):
        n = 96
        return self.gem(n, n, n / 2, n / 2, 44, APP_HUE.get(key, CERULEAN), False, APPS[key], 16.5, 3.4)

    # ---- sound ----------------------------------------------------------------------------
    def sound(self, path):
        """A crisp tick of ice: high glassy partials, very short."""
        rate = 22050
        frames = bytearray()
        for i in range(int(rate * 0.07)):
            t = i / rate
            env = min(1.0, t / 0.0008)
            s = (math.sin(2 * math.pi * 2960 * t) * math.exp(-t * 70) + 0.5 * math.sin(2 * math.pi * 4420 * t) * math.exp(-t * 95)
                 + 0.25 * math.sin(2 * math.pi * 6230 * t) * math.exp(-t * 140))
            frames += struct.pack("<h", int(5200 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))


def _sparkle(d, cx, cy, r, c, waist=0.16):
    """A four-pointed glint (supersampled draw, 1x coords)."""
    pts = []
    for i in range(16):
        a = math.radians(i * 22.5 - 90)
        k = 1.0 if i % 4 == 0 else (waist if i % 2 else waist * 1.25)
        pts.append((cx + r * k * math.cos(a), cy + r * k * math.sin(a)))
    d.polygon([(x * SS, y * SS) for x, y in pts], fill=c)
