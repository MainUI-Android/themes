"""Stained Glass: a cathedral window at dusk. Dim jewel panes in thick lead behind pointed
gothic arches; every menu picture sits in its own jewel roundel, and the focused window
lights up gold as if the sun had just reached it. Text sits on dark stone plates."""
import hashlib
import math
import struct
import wave

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from theme_kit import APPS, BADGES, GLYPHS, SS, TILES, Pen, S, Style, canvas, finish, g_folder, hexc, rgba

LEAD = (16, 13, 18)
LEAD_HI = (84, 76, 86)
STONE = (40, 35, 42)
PLATE = (17, 14, 19)
BRONZE = (150, 116, 72)
GOLD = (226, 178, 88)
GOLD_HI = (255, 226, 150)
CREAM = (250, 238, 212)
MUTED = (184, 166, 142)

RUBY = (178, 24, 48)
SAPPHIRE = (30, 70, 178)
EMERALD = (18, 132, 74)
AMBER = (222, 136, 22)
AMETHYST = (116, 48, 160)
TEAL = (14, 124, 138)
ROSE = (184, 50, 118)
JEWELS = [RUBY, SAPPHIRE, EMERALD, AMBER, AMETHYST, TEAL, ROSE]

TILE_JEWEL = {"recent": SAPPHIRE, "favorite": RUBY, "game": EMERALD, "emulators": AMETHYST,
              "retroarch": AMBER, "app": ROSE, "setting": TEAL}
APP_JEWEL = {"themes": ROSE, "pacman": AMBER, "gameswitcher": AMETHYST, "search": SAPPHIRE, "gallery": EMERALD,
             "activity": RUBY, "retroarch": AMBER, "tweaks": TEAL, "download": SAPPHIRE, "folder": AMBER,
             "hidden": AMETHYST, "emulators": AMETHYST, "category": ROSE, "updates": EMERALD, "repos": TEAL}
# the kit's badges for these spell brand names
BADGE_FIX = {"xbox": None, "segacd": "MD-CD"}


# ---- small image helpers ------------------------------------------------------------------

def shade(c, k):
    return tuple(max(0, min(255, int(round(v * k)))) for v in c[:3])


def mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _solid(w, h, c, a=255):
    return Image.new("RGBA", (w, h), rgba(c, a))


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


def _empty(w, h):
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def _arr_img(rgb, alpha=None):
    """float RGB array (h, w, 3) 0..255 (+ optional alpha array) to an RGBA image."""
    h, w = rgb.shape[:2]
    a = np.full((h, w), 255.0) if alpha is None else alpha
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 255)]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _grid(w, h):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    return x + 0.5, y + 0.5


def _radial(w, h, cx, cy, r, stops):
    """RGBA radial gradient; stops [(t, rgba)] over t = distance / r."""
    x, y = _grid(w, h)
    t = np.clip(np.hypot(x - cx, y - cy) / r, 0, 1)
    return _ramp_img(t, stops)


def _linear(w, h, stops, fx=0.0, fy=1.0):
    x, y = _grid(w, h)
    t = fx * x / w + fy * y / h
    lo, hi = t.min(), t.max()
    return _ramp_img((t - lo) / max(1e-6, hi - lo), stops)


def _ramp_img(t, stops):
    stops = [(s, tuple(c) + (255,) * (4 - len(c))) for s, c in stops]
    ts = [s for s, _ in stops]
    ch = [np.interp(t, ts, [c[k] for _, c in stops]) for k in range(4)]
    return Image.fromarray(np.dstack(ch).round().astype(np.uint8), "RGBA")


def _soft_noise(w, h, cells, seed, lo=0.85, hi=1.15):
    """Low-frequency mottling (float array lo..hi), like uneven antique glass."""
    rng = np.random.default_rng(seed)
    small = Image.fromarray((rng.random((max(2, h // cells), max(2, w // cells))) * 255).astype(np.uint8), "L")
    big = np.asarray(small.resize((w, h), Image.BICUBIC), dtype=np.float32) / 255
    return lo + (hi - lo) * big


def poly_mask(w, h, pts, outline=0):
    """Anti-aliased polygon mask (L, 1x); [outline] > 0 gives just its edge, that wide."""
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    p = [(x * SS, y * SS) for x, y in pts]
    if outline:
        d.line(p + [p[0], p[1]], fill=255, width=max(1, int(outline * SS)), joint="curve")
    else:
        d.polygon(p, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def circle_mask(w, h, cx, cy, r, outline=0):
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    if outline:
        e = outline / 2
        d.ellipse([(cx - r - e) * SS, (cy - r - e) * SS, (cx + r + e) * SS, (cy + r + e) * SS], outline=255,
                  width=max(1, int(outline * SS)))
    else:
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=255)
    return m.resize((w, h), Image.LANCZOS)


def grow(m, px):
    """L mask dilated (px > 0) or eroded (px < 0) by about |px| pixels, smoothly."""
    if px == 0:
        return m
    b = m.filter(ImageFilter.GaussianBlur(abs(px) * 0.8))
    if px > 0:
        return b.point(lambda v: min(255, v * 4))
    return b.point(lambda v: max(0, (v - 191) * 4))


def silhouette(alpha, g=2):
    """[alpha]'s shape with its holes filled, as L."""
    m = alpha.point(lambda v: 255 if v > 70 else 0)
    if g:
        m = m.filter(ImageFilter.GaussianBlur(g * 0.75)).point(lambda v: 255 if v > 28 else 0)
    pad = Image.new("L", (m.width + 2, m.height + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    filled = pad.point(lambda v: 0 if v == 128 else 255).crop((1, 1, m.width + 1, m.height + 1))
    return filled.filter(ImageFilter.GaussianBlur(0.6))


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


# ---- gothic shapes --------------------------------------------------------------------------

def lancet(x0, x1, ys, yb, rise, n=40):
    """A pointed (lancet) arch: sides from yb up to ys, two arcs meeting [rise] above ys."""
    s = x1 - x0
    r = (s * s / 4 + rise * rise) / s
    ta = math.acos((s / 2 - r) / r)
    pts = [(x0, yb), (x0, ys)]
    for i in range(1, n + 1):
        t = math.pi + (ta - math.pi) * i / n
        pts.append((x0 + r + r * math.cos(t), ys - r * math.sin(t)))
    for i in range(1, n + 1):
        t = (math.pi - ta) * (1 - i / n)
        pts.append((x1 - r + r * math.cos(t), ys - r * math.sin(t)))
    pts.append((x1, yb))
    return pts


def tudor(x0, x1, ys, yb, ya, rs, n=16):
    """A four-centred (Tudor) arch: round shoulders of radius rs, straight to a point at ya."""
    mid = (x0 + x1) / 2
    cx, cy = x0 + rs, ys
    dx, dy = mid - cx, ya - cy
    L = math.hypot(dx, dy)
    al = math.acos(rs / L)
    phi = math.atan2(dy, dx)
    cands = [(cx + rs * math.cos(phi + s * al), cy + rs * math.sin(phi + s * al)) for s in (1, -1)]
    tx, ty = min(cands, key=lambda p: p[1])
    t_end = math.atan2(-(ty - cy), tx - cx)
    left = [(cx + rs * math.cos(math.pi + (t_end - math.pi) * i / n), cy - rs * math.sin(math.pi + (t_end - math.pi) * i / n))
            for i in range(n + 1)]
    right = [(x0 + x1 - x, y) for x, y in reversed(left)]
    return [(x0, yb)] + left + [(mid, ya)] + right + [(x1, yb)]


def quatrefoil(n, cx, cy, R):
    """Four-lobed gothic quatrefoil mask (L, n x n)."""
    m = Image.new("L", (n * SS, n * SS), 0)
    d = ImageDraw.Draw(m)
    lr = R * 0.5
    off = R - lr
    for dx, dy in ((off, 0), (-off, 0), (0, off), (0, -off)):
        d.ellipse([S(cx + dx - lr), S(cy + dy - lr), S(cx + dx + lr), S(cy + dy + lr)], fill=255)
    d.rectangle([S(cx - off), S(cy - off), S(cx + off), S(cy + off)], fill=255)
    return m.resize((n, n), Image.LANCZOS)


def lozenge(cx, cy, rx, ry):
    return [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)]


# ---- glass ----------------------------------------------------------------------------------

def glass_fill(w, h, color, light=(0.4, 0.3), seed=1, k=1.0, glow=0.55, mottle=False):
    """A pane of coloured glass: lit from behind at [light] (fractions of the box), mottled."""
    lx, ly = light[0] * w, light[1] * h
    x, y = _grid(w, h)
    d = np.clip(np.hypot(x - lx, y - ly) / (0.85 * math.hypot(w, h)), 0, 1)
    lum = (1 + glow) - (glow + 0.35) * d          # brighter where the light comes through
    lum = lum * (_soft_noise(w, h, 9, seed, 0.9, 1.08) if mottle else 1.0) * k
    base = np.array(color[:3], np.float32)
    rgb = base[None, None, :] * lum[..., None]
    # light bleaches the glass a little towards white where it is brightest
    hot = np.clip(lum - 1.05, 0, 1)[..., None] * 0.55
    rgb = rgb + (255 - rgb) * hot
    return _arr_img(rgb)


def jewel_of(sid):
    return JEWELS[int(hashlib.md5(sid.encode()).hexdigest()[:6], 16) % len(JEWELS)]


class Theme(Style):
    name = "Stained Glass"
    author = "MainUI"
    description = "A cathedral window at dusk: jewel glass in thick lead, gothic arches and roundels that light up gold when chosen."

    bg_top = (24, 20, 28)
    bg_bottom = (14, 12, 17)
    accent = (150, 32, 54)        # MainUI's own fills under white text
    accent2 = SAPPHIRE
    highlight = GOLD
    text = CREAM
    muted = MUTED
    glyph_n = CREAM
    glyph_f = (255, 250, 236)
    panel = (34, 29, 37)
    panel_alpha = 255
    bar = PLATE
    bar_alpha = 238

    font_file = "CinzelDecorative-Bold.ttf"
    font_license = "OFL-CinzelDecorative.txt"
    title_size, hint_size, list_size, grid1x4, grid3x4, battery_size = 26, 23, 22, 19, 15, 16

    icon_quant = 96
    sel_icons = False

    def config(self):
        cfg = super().config()
        cfg["grid"]["selectedcolor"] = hexc(GOLD_HI)
        cfg["mainui"]["background"] = hexc(self.bg_bottom)
        return cfg

    # ---- background ------------------------------------------------------------------------
    def background(self, w=640, h=480):
        """Irregular jewel panes in thick lead, dim at dusk, lit from high above."""
        rng = np.random.default_rng(11)
        cols, rows = 13, 10
        seeds = np.array([((i + rng.uniform(-0.42, 0.42)) * w / cols, (j + rng.uniform(-0.42, 0.42)) * h / rows)
                          for j in range(rows + 1) for i in range(cols + 1)], np.float32)
        n = len(seeds)
        weights = np.array([1.4, 1.7, 0.9, 0.6, 0.9, 0.6, 0.45])
        pick = rng.choice(len(JEWELS), n, p=weights / weights.sum())
        x, y = _grid(w, h)
        xf, yf = x.ravel(), y.ravel()
        idx1 = np.empty(xf.size, np.int32)
        edge = np.empty(xf.size, np.float32)
        step = 20000
        for a in range(0, xf.size, step):
            px, py = xf[a:a + step, None], yf[a:a + step, None]
            d2 = (px - seeds[None, :, 0]) ** 2 + (py - seeds[None, :, 1]) ** 2
            two = np.argsort(d2, axis=1)[:, :2]
            r = np.arange(two.shape[0])
            d1, dd2 = d2[r, two[:, 0]], d2[r, two[:, 1]]
            sep = np.hypot(*(seeds[two[:, 0]] - seeds[two[:, 1]]).T)
            idx1[a:a + step] = two[:, 0]
            edge[a:a + step] = (dd2 - d1) / (2 * np.maximum(sep, 1e-3))
        idx1 = idx1.reshape(h, w)
        edge = edge.reshape(h, w)
        # flat panes (cheap to store), each lit by where it sits: brightest high in the
        # middle, restrained so the menus carry the colour, falling into stone at the edges
        sx, sy = seeds[:, 0], seeds[:, 1]
        light = 0.19 + 0.24 * np.exp(-(((sx - w * 0.5) / (w * 0.5)) ** 2 + ((sy + h * 0.1) / (h * 0.8)) ** 2))
        vig = 1 - 0.5 * np.clip((np.hypot((sx - w / 2) / (w * 0.6), (sy - h * 0.45) / (h * 0.6)) - 0.6) / 0.6, 0, 1)
        col = np.array([JEWELS[p] for p in pick], np.float32) * (rng.uniform(0.8, 1.15, n) * light * vig)[:, None]
        col = col * 0.8 + col.mean(axis=1, keepdims=True) * 0.2 + np.array([12, 10, 14], np.float32)
        rgb = np.round(col)[idx1]
        lead_a = np.clip(2.1 - edge, 0, 1)[..., None]
        ridge = np.clip(0.8 - edge, 0, 1)[..., None] * 0.3
        lead = np.array(LEAD, np.float32) * (1 - ridge) + np.array(LEAD_HI, np.float32) * ridge
        rgb = rgb * (1 - lead_a) + lead * lead_a
        return _arr_img(rgb)

    # ---- bars ----------------------------------------------------------------------------
    def border_strip(self, w, y0, hh, seed=5, k=0.75, x0=0, x1=None):
        """A window border: a row of small jewel panes between two lead lines."""
        x1 = w if x1 is None else x1
        h = int(math.ceil(y0 + hh + 2))
        out = canvas(w, h)
        d = ImageDraw.Draw(out)
        seq = [RUBY, SAPPHIRE, AMBER, EMERALD, SAPPHIRE, AMETHYST]
        pw = 13
        nx = int((x1 - x0) / pw) + 1
        off = x0 + ((x1 - x0) - (nx - 1) * pw) / 2 - pw / 2
        for i in range(nx):
            xa = off + i * pw
            c = shade(seq[i % len(seq)], k)
            d.rectangle([S(max(x0, xa)), S(y0), S(min(x1, xa + pw)), S(y0 + hh)], fill=rgba(c))
            d.rectangle([S(max(x0, xa + 2)), S(y0 + 1), S(min(x1, xa + pw - 3)), S(y0 + 2)], fill=rgba(mix(c, (255, 255, 255), 0.35), 120))
        for i in range(nx + 1):
            xa = off + i * pw
            if x0 <= xa <= x1:
                d.line([S(xa), S(y0), S(xa), S(y0 + hh)], fill=rgba(LEAD), width=int(1.6 * SS))
        d.line([S(x0), S(y0), S(x1), S(y0)], fill=rgba(LEAD), width=int(1.8 * SS))
        d.line([S(x0), S(y0 + hh), S(x1), S(y0 + hh)], fill=rgba(LEAD), width=int(1.8 * SS))
        return finish(out)

    def _bar(self, top):
        w, h = 640, 60
        im = _linear(w, h, [(0, PLATE + (242,)), (1, (26, 22, 29, 236))] if top else [(0, (26, 22, 29, 236)), (1, PLATE + (242,))])
        strip = self.border_strip(w, 0, 5, k=0.82)
        y = h - 7 if top else 1
        layer = _empty(w, h)
        layer.alpha_composite(strip, (0, y))
        g = canvas(w, h)
        gd = ImageDraw.Draw(g)
        gy = (y - 1.6) if top else (y + 7.6)
        gd.line([0, S(gy), S(w), S(gy)], fill=rgba(GOLD, 150), width=int(1.0 * SS))
        return _over(im, layer, finish(g))

    def header_bar(self):
        return self._bar(True)

    def footer_bar(self):
        return self._bar(False)

    def rose_window(self, w, h, cx, cy, R, lit=1.0):
        """A tiny rose window: eight jewel petals round a gold heart, in lead (w x h layer)."""
        out = _empty(w, h)
        disc = circle_mask(w, h, cx, cy, R)
        out = _over(out, _mask(_solid(w, h, LEAD), disc))
        cols = [RUBY, SAPPHIRE, EMERALD, AMBER, AMETHYST, SAPPHIRE, RUBY, TEAL]
        for i in range(8):
            a0 = math.radians(i * 45 - 90 - 22.5)
            pts = [(cx, cy)] + [(cx + (R - 1.6) * math.cos(a0 + math.radians(45) * t / 6),
                                 cy + (R - 1.6) * math.sin(a0 + math.radians(45) * t / 6)) for t in range(7)]
            m = poly_mask(w, h, pts)
            m = grow(m, -0.6)
            out = _over(out, _mask(glass_fill(w, h, shade(cols[i], 1.15 * lit), (0.4, 0.35), i, glow=0.4), m))
        out = _over(out, _mask(_solid(w, h, LEAD), circle_mask(w, h, cx, cy, R * 0.36)))
        out = _over(out, _mask(_solid(w, h, GOLD_HI), circle_mask(w, h, cx, cy, R * 0.26)))
        return out

    def logo(self):
        w, h = 160, 42
        out = _over(_empty(w, h), self.rose_window(w, h, 18, 21, 17.5))
        t = canvas(w, h)
        d = ImageDraw.Draw(t)
        f = self.font(16.5)
        d.text((S(43), S(13)), "STAINED", font=f, fill=(255, 255, 255, 255), anchor="lm")
        d.text((S(43), S(30.5)), "GLASS", font=f, fill=(255, 255, 255, 255), anchor="lm")
        t = finish(t)
        gold = _linear(w, h, [(0.2, GOLD_HI), (0.8, GOLD)], 0, 1)
        return _over(out, _mask(_solid(w, h, (0, 0, 0), 200), _blur(t.getchannel("A"), 1.2)), _mask(gold, t.getchannel("A")))

    # ---- lists -------------------------------------------------------------------------------
    def selection(self, h):
        w = 640
        box = (5, 4, w - 5, h - 4)
        r = 6
        outer = poly_mask(w, h, _rect_pts(box, r))
        inner = poly_mask(w, h, _rect_pts((box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3), r - 2))
        glass = glass_fill(w, h, (150, 78, 16), (0.12, 0.2), 4, glow=0.35)
        deep = _linear(w, h, [(0, (0, 0, 0, 0)), (0.5, (60, 10, 20, 70)), (1, (60, 8, 24, 150))], 1, 0)
        body = _over(_mask(glass, inner), _mask(deep, inner))
        halo = _mask(_blur(_mask(_solid(w, h, GOLD), outer), 3), _edge_fade(w, h), 0.55)
        frame = _mask(_solid(w, h, LEAD), outer)
        hl = canvas(w, h)
        hd = ImageDraw.Draw(hl)
        hd.line([S(box[0] + 8), S(box[1] + 4.2), S(box[2] - 8), S(box[1] + 4.2)], fill=(255, 230, 170, 70), width=SS)
        gold = _mask(_solid(w, h, GOLD), poly_mask(w, h, _rect_pts((box[0] + 1.5, box[1] + 1.5, box[2] - 1.5, box[3] - 1.5), r - 1), 1.1))
        return kquant(_over(_empty(w, h), halo, frame, body, finish(hl), gold), 96)

    def divider(self):
        w, h = 640, 4
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        d.line([S(20), S(1.6), S(620), S(1.6)], fill=rgba(LEAD, 230), width=int(2.2 * SS))
        d.line([S(20), S(3.0), S(620), S(3.0)], fill=rgba(BRONZE, 70), width=int(0.8 * SS))
        m = Image.new("L", (w, 1))
        m.putdata([int(255 * max(0.0, min(1.0, (x - 20) / 90, (620 - x) / 90))) for x in range(w)])
        return _mask(finish(im), m.resize((w, h)))

    # ---- windows ------------------------------------------------------------------------------
    def lit_glass(self, w, h, shape, seed=2, center=None, lattice=21.0):
        """Sunlit amber-gold quarry glass inside [shape]: diamond quarries in a lead lattice,
        each quarry one flat tone (brighter nearer the light), as old glass is."""
        cx, cy = center or (w / 2, h * 0.4)
        x, y = _grid(w, h)
        k = math.tan(math.radians(62))
        u = (x - y / k) / lattice
        v = (x + y / k) / lattice
        cu, cv = np.floor(u) + 0.5, np.floor(v) + 0.5
        qx, qy = (cu + cv) / 2 * lattice, (cv - cu) / 2 * lattice * k
        d = np.clip(np.hypot((qx - cx) / (w * 0.72), (qy - cy) / (h * 0.6)), 0, 1) ** 1.1
        jit = 0.94 + 0.1 * np.mod(np.sin(cu * 12.9898 + cv * 78.233 + seed) * 43758.5453, 1.0)
        warm = np.array([255, 222, 140], np.float32)
        deep = np.array([170, 86, 16], np.float32)
        rgb = (warm[None, None, :] * (1 - d[..., None]) + deep[None, None, :] * d[..., None]) * jit[..., None]
        rgb = np.round(rgb)
        norm = lattice / math.sqrt(1 + 1 / k ** 2)
        dist = np.minimum(np.abs(u - np.round(u)), np.abs(v - np.round(v))) * norm
        la = (np.clip(1.15 - dist, 0, 1) * 0.62)[..., None]
        rgb = rgb * (1 - la) + np.array(LEAD, np.float32) * la
        return _mask(_arr_img(rgb), shape)

    def window(self, w, h, pts, focused, band, glow_r=5, lattice=21.0, center=None, seed=2):
        """A gothic window: lead outline, dark smoky glass or sunlit gold glass, and a dark
        stone label plate across it (y band[0]..band[1])."""
        shape = poly_mask(w, h, pts)
        ring = poly_mask(w, h, pts, 3.0)
        layers = [_empty(w, h)]
        if focused:
            halo = _over(_fade(_blur(_mask(_solid(w, h, (255, 196, 90)), ring), glow_r), 1.5),
                         _fade(_blur(_mask(_solid(w, h, (255, 214, 130)), ring), glow_r * 0.4), 0.9))
            layers.append(_mask(halo, _edge_fade(w, h)))
            layers.append(self.lit_glass(w, h, shape, seed, center, lattice))
        else:
            body = _linear(w, h, [(0, (34, 29, 38, 236)), (1, (20, 17, 23, 240))])
            layers.append(_mask(body, shape))
            # a whisper of the coloured window behind the stone
            tint = _radial(w, h, w / 2, h * 0.35, h * 0.7, [(0, (70, 50, 110, 40)), (1, (40, 30, 60, 0))])
            layers.append(_mask(tint, shape))
        # the label plate, inside the frame
        p = Image.new("L", (w, h), 0)
        ImageDraw.Draw(p).rectangle((0, band[0], w, band[1]), fill=255)
        plate = ImageChops.multiply(p, grow(shape, -2))
        layers.append(_mask(_solid(w, h, PLATE, 250 if focused else 200), plate))
        g = canvas(w, h)
        gd = ImageDraw.Draw(g)
        gc = rgba(GOLD, 230) if focused else rgba(BRONZE, 120)
        for yy in (band[0] + 0.5, band[1] - 0.5):
            gd.line([0, S(yy), S(w), S(yy)], fill=gc, width=int(1.1 * SS))
        layers.append(_mask(finish(g), grow(shape, -3)))
        # the lead frame, with a gilded or bronze line just inside
        layers.append(_mask(_solid(w, h, LEAD), ring))
        inner = ImageChops.subtract(grow(shape, -2.2), grow(shape, -3.4))
        layers.append(_mask(_solid(w, h, GOLD_HI if focused else BRONZE), inner, 0.9 if focused else 0.55))
        return _over(*layers)

    def card(self, w, h, focused):
        if (w, h) == (155, 170):
            pts = tudor(6, 149, 40, 165, 5, 18)
            return kquant(self.window(w, h, pts, focused, (135, 161), glow_r=4, lattice=17, center=(77, 62)), 96)
        pts = _rect_pts((5, 5, w - 5, h - 5), 6)
        return self.window(w, h, pts, focused, (h, h), glow_r=3, lattice=15)

    def tile_base(self, focused):
        w, h = 156, 278
        pts = lancet(9, 147, 96, 262, 88)
        im = self.window(w, h, pts, focused, (179, 211), glow_r=5, center=(78, 112))
        # a stone sill under the window
        sill = canvas(w, h)
        sd = ImageDraw.Draw(sill)
        sd.rounded_rectangle([S(3), S(261), S(153), S(272)], radius=S(2.5), fill=rgba(STONE))
        sd.rectangle([S(4), S(261), S(152), S(262.4)], fill=rgba((96, 86, 94)))
        sd.rectangle([S(4), S(270.6), S(152), S(272)], fill=rgba((20, 17, 22)))
        return _over(im, finish(sill))

    def roundel(self, w, h, cx, cy, R, color, focused, glyph=None, gsize=25, gw=4.4):
        """A jewel roundel: a ring of small panes round a lit disc, all in lead, with the
        picture drawn on it in pale glass (w x h layer)."""
        layers = [_empty(w, h)]
        disc = circle_mask(w, h, cx, cy, R)
        if focused:
            layers.append(_mask(_blur(_mask(_solid(w, h, (255, 210, 120)), disc), 5), _edge_fade(w, h), 1.2))
        layers.append(_mask(_solid(w, h, LEAD), disc))
        k = 1.12 if focused else 0.9
        rin = R * 0.72
        # ring of panes, alternating the jewel with a paler glass; each pane one flat tone,
        # brighter towards the light (upper left)
        for i in range(12):
            a0 = math.radians(i * 30 - 90)
            pts = [(cx + (R - 2.4) * math.cos(a0 + math.radians(30) * t / 6), cy + (R - 2.4) * math.sin(a0 + math.radians(30) * t / 6))
                   for t in range(7)]
            pts += [(cx + (rin + 1.2) * math.cos(a0 + math.radians(30) * (6 - t) / 6),
                     cy + (rin + 1.2) * math.sin(a0 + math.radians(30) * (6 - t) / 6)) for t in range(7)]
            m = grow(poly_mask(w, h, pts), -0.7)
            c = color if i % 2 == 0 else mix(color, (255, 236, 190), 0.42)
            lit = 1.0 + 0.2 * math.cos(a0 + math.radians(15) - math.radians(-130))
            layers.append(_mask(_solid(w, h, shade(c, k * lit)), m))
        inner = circle_mask(w, h, cx, cy, rin - 1.0)
        layers.append(_mask(glass_fill(w, h, shade(color, 1.04 if focused else 0.9), ((cx - R * 0.25) / w, (cy - R * 0.35) / h), 7,
                                       glow=0.55 if focused else 0.5), inner))
        if glyph is not None:
            g = canvas(w, h)
            glyph(ImageDraw.Draw(g), cx, cy, gsize, (255, 255, 255, 255), gw)
            ga = finish(g).getchannel("A")
            layers.append(_mask(_solid(w, h, LEAD), grow(ga, 1.6), 0.95))
            pale = _linear(w, h, [(0.3, (255, 250, 232)), (0.75, (246, 222, 170))], 0, 1)
            layers.append(_mask(pale, ga))
        return _over(*layers)

    def tile_glyph(self, key, focused):
        w, h = 156, 278
        col = TILE_JEWEL[key]
        # a small quatrefoil of the same glass under the label plate
        m = Image.new("L", (w, h), 0)
        m.paste(quatrefoil(30, 15, 15, 12.5), (63, 222))
        mi = Image.new("L", (w, h), 0)
        mi.paste(quatrefoil(30, 15, 15, 10), (63, 222))
        q = _over(_empty(w, h), _mask(_solid(w, h, LEAD), m),
                  _mask(_radial(w, h, 75, 234, 13, [(0, shade(mix(col, (255, 240, 200), 0.3), 1.1 if focused else 0.8)),
                                                   (1, shade(col, 1.0 if focused else 0.62))]), mi))
        return _over(q, self.roundel(w, h, 78, 112, 55, col, focused, TILES[key], 25, 4.6))

    def home_tile(self, key, focused):
        base = self.tile_base(focused)
        return kquant(_over(base, self.tile_glyph(key, focused)) if key else base, 96)

    # ---- buttons and small parts ------------------------------------------------------------
    def button(self, label, primary):
        n = 54
        col = {"A": RUBY, "B": SAPPHIRE, "X": EMERALD, "Y": AMBER}[label]
        q = quatrefoil(n, n / 2, n / 2, 24)
        qi = quatrefoil(n, n / 2, n / 2, 21.2)
        body = glass_fill(n, n, shade(col, 1.1), (0.38, 0.3), 3, glow=0.6)
        t = canvas(n, n)
        ImageDraw.Draw(t).text((S(n / 2), S(n / 2 + 1)), label, font=self.font(21), fill=(255, 255, 255, 255), anchor="mm")
        ta = finish(t).getchannel("A")
        return _over(_empty(n, n), _mask(_solid(n, n, (0, 0, 0), 120), _blur(q, 1.5)), _mask(_solid(n, n, LEAD), q),
                     _mask(body, qi), _mask(_solid(n, n, LEAD), grow(ta, 1.5), 0.85), _mask(_solid(n, n, (255, 248, 230)), ta))

    def pill(self, label, w, h=48):
        box = (3, 10, w - 3, h - 10)
        pts = _hex_pts(box)
        shape = poly_mask(w, h, pts)
        t = canvas(w, h)
        ImageDraw.Draw(t).text((S(w / 2), S(h / 2 + 0.5)), label, font=self.font(13), fill=rgba(CREAM), anchor="mm")
        return _over(_mask(_solid(w, h, LEAD, 235), shape), _mask(_solid(w, h, GOLD), poly_mask(w, h, _hex_pts((4.5, 11.5, w - 4.5, h - 11.5)), 1.1), 0.85),
                     finish(t))

    def dot(self, active):
        w, h = 20, 18
        if active:
            m = poly_mask(w, h, lozenge(10, 9, 6.5, 8))
            mi = poly_mask(w, h, lozenge(10, 9, 4.6, 6))
            return _over(_empty(w, h), _mask(_blur(_mask(_solid(w, h, (255, 200, 100)), m), 2), _edge_fade(w, h, 2), 1.2),
                         _mask(_solid(w, h, LEAD), m), _mask(_radial(w, h, 9, 7, 7, [(0, GOLD_HI), (1, AMBER)]), mi))
        m = poly_mask(w, h, lozenge(10, 9, 5.2, 7))
        mi = poly_mask(w, h, lozenge(10, 9, 3.4, 5))
        return _over(_empty(w, h), _mask(_solid(w, h, LEAD), m), _mask(_solid(w, h, (120, 100, 116)), mi))

    def toggle(self, on):
        w, h = 92, 44
        box = (8, 11, w - 8, h - 11)
        r = (box[3] - box[1]) / 2
        track = poly_mask(w, h, _rect_pts(box, r))
        inner = poly_mask(w, h, _rect_pts((box[0] + 2.5, box[1] + 2.5, box[2] - 2.5, box[3] - 2.5), r - 2.5))
        kx = box[2] - r if on else box[0] + r
        kr = r + 2
        knob = circle_mask(w, h, kx, h / 2, kr)
        knob_i = circle_mask(w, h, kx, h / 2, kr - 2.6)
        if on:
            fill = glass_fill(w, h, (190, 118, 28), (0.3, 0.3), 5, glow=0.5)
            halo = _mask(_blur(_mask(_solid(w, h, (255, 200, 100)), track), 3), _edge_fade(w, h), 0.8)
            kfill = _radial(w, h, kx - 2, h / 2 - 3, kr, [(0, (255, 250, 230)), (1, (236, 210, 160))])
        else:
            fill = _solid(w, h, (40, 34, 44))
            halo = _empty(w, h)
            kfill = _radial(w, h, kx - 2, h / 2 - 3, kr, [(0, (150, 136, 140)), (1, (96, 86, 92))])
        return _over(_empty(w, h), halo, _mask(_solid(w, h, LEAD), track), _mask(fill, inner),
                     _mask(_solid(w, h, (0, 0, 0), 110), _blur(knob, 1.5)), _mask(_solid(w, h, LEAD), knob), _mask(kfill, knob_i))

    def arrow(self, left, size=24):
        im = canvas(size, size)
        d = ImageDraw.Draw(im)
        xs = (0.64, 0.3) if left else (0.36, 0.7)
        pts = [(S(size * xs[0]), S(size * 0.18)), (S(size * xs[1]), S(size * 0.5)), (S(size * xs[0]), S(size * 0.82))]
        d.line(pts, fill=(255, 255, 255, 255), width=int(size * 0.13 * SS), joint="curve")
        a = finish(im).getchannel("A")
        return _over(_empty(size, size), _mask(_solid(size, size, LEAD), grow(a, 1.2), 0.8), _mask(_solid(size, size, GOLD_HI), a))

    def panel_image(self, w, h):
        menu = w == 400
        layers = [_empty(w, h)]
        box = (0, 0, w, h) if menu else (2, 2, w - 2, h - 2)
        shape = Image.new("L", (w, h), 0)
        ImageDraw.Draw(shape).rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=255)
        stone = _linear(w, h, [(0, (38, 33, 42)), (1, (26, 22, 29))])
        layers.append(_mask(stone, shape))
        # a border of small jewel panes inside a lead frame
        bw = 6
        x0, y0, x1, y1 = box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3
        strip = self.border_strip(w, 0, bw, k=0.8, x0=x0, x1=x1)
        side = self.border_strip(h, 0, bw, k=0.8, x0=y0, x1=y1).rotate(90, expand=True)
        b = _empty(w, h)
        if not menu:
            b.alpha_composite(strip, (0, int(y0)))
        b.alpha_composite(strip, (0, int(y1 - bw - 1)))
        b.alpha_composite(side.crop((0, 0, side.width, h)), (int(x0), 0))
        b.alpha_composite(side.crop((0, 0, side.width, h)).transpose(Image.Transpose.FLIP_LEFT_RIGHT), (int(x1 - side.width), 0))
        if menu:   # MainUI's title band sits right on top: the border starts under it
            ImageDraw.Draw(b).rectangle((0, 0, w, 2), fill=(0, 0, 0, 0))
        layers.append(b)
        frame = canvas(w, h)
        fd = ImageDraw.Draw(frame)
        fd.rectangle([S(box[0]), S(box[1]), S(box[2]) - 1, S(box[3]) - 1], outline=rgba(LEAD), width=int(3 * SS))
        ins = bw + 4.6
        fd.rectangle([S(box[0] + ins), S(box[1] + (2 if menu else ins)), S(box[2] - ins), S(box[3] - ins)],
                     outline=rgba(GOLD, 150), width=int(1.0 * SS))
        layers.append(finish(frame))
        return _over(*layers)

    def folder_icon(self):
        n = 60
        im = canvas(n, n)
        g_folder(ImageDraw.Draw(im), 30, 31, 19, (255, 255, 255, 255), 3.4)
        a = finish(im).getchannel("A")
        sil = silhouette(a, 1)
        return _over(_empty(n, n), _mask(_solid(n, n, LEAD), grow(sil, 1.5)), _mask(glass_fill(n, n, AMBER, (0.3, 0.3), 2, glow=0.4), sil),
                     _mask(_solid(n, n, LEAD), grow(a, 1.0), 0.8), _mask(_solid(n, n, (255, 240, 205)), a))

    def favorite_mark(self):
        w, h = 34, 39
        pts = []
        for i in range(10):
            rr = 15 if i % 2 == 0 else 6.8
            a = math.radians(-90 + i * 36)
            pts.append((17 + rr * math.cos(a), 20.5 + rr * math.sin(a)))
        m = poly_mask(w, h, pts)
        mi = grow(m, -1.6)
        return _over(_empty(w, h), _mask(_solid(w, h, LEAD), grow(m, 1.0)),
                     _mask(_radial(w, h, 15, 16, 15, [(0, (255, 236, 170)), (0.5, (236, 170, 50)), (1, (190, 110, 20))]), mi))

    def battery(self, level, charging=False):
        n = 48
        layers = [_empty(n, n)]
        body = (6, 15, 40, 33)
        o = canvas(n, n)
        d = ImageDraw.Draw(o)
        d.rounded_rectangle([S(v) for v in body], radius=S(3.5), outline=rgba(CREAM, 235), width=int(2.0 * SS))
        d.rounded_rectangle([S(v) for v in (40.5, 20.5, 44, 27.5)], radius=S(1.2), fill=rgba(CREAM, 235))
        layers.append(finish(o))
        if level > 0:
            fm = poly_mask(n, n, _rect_pts((9.5, 18.5, 9.5 + 27 * level, 29.5), 1.5))
            col = RUBY if level <= 0.2 else (186, 132, 44)
            layers.append(_mask(glass_fill(n, n, shade(col, 1.15), (0.3, 0.3), 1, glow=0.5), fm))
        if charging:
            b = poly_mask(n, n, [(26, 10), (16, 26), (23, 26), (20, 38), (31, 21), (24, 21)])
            layers += [_mask(_solid(n, n, LEAD), grow(b, 1.5)), _mask(_solid(n, n, (255, 244, 200)), b)]
        return _over(*layers)

    def preview_frame(self):
        w, h = 250, 360
        im = canvas(w, h)
        d = ImageDraw.Draw(im)
        d.rectangle([S(1), S(1), S(w - 1), S(h - 1)], fill=rgba(PLATE, 245), outline=rgba(LEAD), width=int(2 * SS))
        d.rectangle([S(3.5), S(3.5), S(w - 3.5), S(h - 3.5)], outline=rgba(GOLD, 170), width=int(1.0 * SS))
        return finish(im)

    def key(self, focused):
        w, h = 52, 38
        pts = _rect_pts((2, 2, w - 2, h - 2), 5)
        shape = poly_mask(w, h, pts)
        inner = grow(shape, -2)
        fill = glass_fill(w, h, (200, 130, 30), (0.4, 0.3), 3, glow=0.5) if focused else _linear(w, h, [(0, (52, 46, 56)), (1, (36, 31, 40))])
        return _over(_empty(w, h), _mask(_solid(w, h, LEAD), shape), _mask(fill, inner),
                     _mask(_solid(w, h, GOLD_HI if focused else BRONZE), ImageChops.subtract(inner, grow(inner, -1.0)), 0.7))

    def input_box(self):
        w, h = 560, 60
        box = (2, 3, w - 2, h - 3)
        shape = poly_mask(w, h, _rect_pts(box, 6))
        return _over(_mask(_solid(w, h, PLATE, 235), shape), _mask(_solid(w, h, LEAD), poly_mask(w, h, _rect_pts(box, 6), 2.4)),
                     _mask(_solid(w, h, GOLD), poly_mask(w, h, _rect_pts((box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3), 4), 1.0), 0.8))

    # ---- system and app icons ---------------------------------------------------------------
    def icon_picture(self, sid, selected, cy):
        w, h = 120, 130
        im = canvas(w, h)
        pen = Pen(ImageDraw.Draw(im), 60, cy, (255, 255, 255, 255), SS, w=3.0)
        (GLYPHS.get(sid) or GLYPHS["fallback"])(pen)
        lines = finish(im)
        a = lines.getchannel("A")
        sil = silhouette(a, 2)
        col = jewel_of(sid)
        glass = glass_fill(w, h, shade(col, 1.1 if selected else 0.95), (0.36, (cy - 30) / h), int(hashlib.md5(sid.encode()).hexdigest()[6:10], 16) % 50, glow=0.55)
        pale = _linear(w, h, [(0.15, (255, 250, 234)), (0.8, (242, 216, 162))], 0, 1)
        layers = [_empty(w, h)]
        if selected:
            layers.append(_mask(_blur(_mask(_solid(w, h, (255, 200, 110)), sil), 4), _edge_fade(w, h), 1.0))
        layers += [_mask(_solid(w, h, LEAD), grow(sil, 2.2)), _mask(glass, sil),
                   _mask(_solid(w, h, LEAD), grow(a, 1.2), 0.9), _mask(pale, a)]
        return _over(*layers)

    def badge(self, label, selected):
        w, h = 120, 130
        f = self.font(12.5)
        t = canvas(w, h)
        d = ImageDraw.Draw(t)
        tw = d.textlength(label, font=f) / SS
        bw = min(116, tw + 22)
        x0 = (w - bw) / 2
        box = (x0, 105, x0 + bw, 126)
        d.text((S(w / 2), S(115.8)), label, font=f, fill=rgba(CREAM), anchor="mm")
        shape = poly_mask(w, h, _hex_pts(box))
        return _over(_mask(_solid(w, h, LEAD), grow(shape, 1.2)), _mask(_solid(w, h, PLATE), shape),
                     _mask(_solid(w, h, GOLD if selected else BRONZE), poly_mask(w, h, _hex_pts((box[0] + 2, box[1] + 2, box[2] - 2, box[3] - 2)), 0.9), 0.9),
                     finish(t))

    def system_icon(self, sid, selected):
        label = BADGE_FIX[sid] if sid in BADGE_FIX else BADGES.get(sid, sid[:7].upper())
        out = self.icon_picture(sid, selected, 52 if label else 62)
        return _over(out, self.badge(label, selected)) if label else out

    def app_icon(self, key):
        n = 96
        return self.roundel(n, n, n / 2, n / 2, 44, APP_JEWEL.get(key, SAPPHIRE), False, APPS[key], 20, 3.8)

    # ---- sound ----------------------------------------------------------------------------
    def sound(self, path):
        """A small bright bell: inharmonic partials, quick fade."""
        rate = 22050
        frames = bytearray()
        parts = [(1318, 1.0, 38), (2637 * 1.002, 0.5, 52), (3160, 0.32, 70), (3955, 0.22, 95), (5540, 0.1, 140)]
        for i in range(int(rate * 0.14)):
            t = i / rate
            env = min(1.0, t / 0.0015)
            s = sum(a * math.sin(2 * math.pi * f * t) * math.exp(-t * dcy) for f, a, dcy in parts)
            frames += struct.pack("<h", int(4600 * env * s))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wv:
            wv.setnchannels(1)
            wv.setsampwidth(2)
            wv.setframerate(rate)
            wv.writeframes(bytes(frames))


def _rect_pts(box, r, n=6):
    """Rounded rectangle as a polygon."""
    x0, y0, x1, y1 = box
    r = max(0.01, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _hex_pts(box):
    """A plate with pointed ends."""
    x0, y0, x1, y1 = box
    k = (y1 - y0) / 2
    return [(x0, (y0 + y1) / 2), (x0 + k * 0.8, y0), (x1 - k * 0.8, y0), (x1, (y0 + y1) / 2), (x1 - k * 0.8, y1), (x0 + k * 0.8, y1)]


def _edge_fade(w, h, n=4):
    """L mask: 0 on the outer pixel ring, rising to full over [n] px, so halos never hit the edge."""
    def prof(k):
        return [int(255 * max(0.0, min(1.0, min(i, k - 1 - i) / n))) for i in range(k)]
    hx, vy = Image.new("L", (w, 1)), Image.new("L", (1, h))
    hx.putdata(prof(w))
    vy.putdata(prof(h))
    return ImageChops.darker(hx.resize((w, h)), vy.resize((w, h)))
