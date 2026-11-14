#!/usr/bin/env python3
"""Build the themes in kit/themes/ (one module per theme, see theme_kit.py).

    python3 kit/build.py [ID ...] [--out DIR] [--mock DIR] [--previews DIR] [--release DIR] [--mainui]
    python3 kit/build.py --gallery README.md [ID ...]

ID is a module name in kit/themes/ (all of them by default). Each theme is written to
DIR/<theme name> (default dist/themes). Prints any problem theme_kit.check() finds.

  --mock DIR      also writes DIR/<id>-mock.png: the home screen, Games grid, a list and a
                  pop-up as MainUI lays them out.
  --previews DIR  copies each theme's preview.png to DIR/<id>.png (the README's pictures).
  --release DIR   what MainUI's Theme Store downloads: DIR/<id>.zip (the theme in a folder of
                  its name), DIR/<id>.png (its preview) and DIR/catalog.json listing them.
  --mainui        also builds MainUI's default theme (kit/make_mainui_theme.py) to
                  DIR/MainUI. MainUI bundles it; it is not in the catalog.
  --gallery FILE  only rewrites the theme table between FILE's <!-- gallery --> markers, from
                  the theme modules and previews/<id>.png (no build).

Requires Pillow.
"""
import argparse
import importlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mock_screens  # noqa: E402
import theme_kit  # noqa: E402


def write_zip(theme_dir, name, path):
    """The theme in a top folder [name]; fixed dates and order, so the same theme gives the same zip."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(p for p in theme_dir.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f"{name}/{f.relative_to(theme_dir).as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes())


def gallery(readme, ids):
    """The README's table of themes: two per row, preview over name and description."""
    cells = []
    for i in ids:
        st = importlib.import_module(f"themes.{i}").Theme
        cells.append(f'<img src="previews/{i}.png" width="320" alt="{st.name}"><br><b>{st.name}</b><br>{st.description}')
    rows = ["<table>"]
    for k in range(0, len(cells), 2):
        pair = cells[k:k + 2] + [""] * (2 - len(cells[k:k + 2]))
        rows.append("<tr>" + "".join(f'<td valign="top" width="50%">{c}</td>' for c in pair) + "</tr>")
    rows.append("</table>")
    text = Path(readme).read_text()
    a, b = "<!-- gallery -->", "<!-- /gallery -->"
    head, rest = text.split(a, 1)
    tail = rest.split(b, 1)[1]
    Path(readme).write_text(f"{head}{a}\n{chr(10).join(rows)}\n{b}{tail}")
    print(f"{readme}: {len(cells)} themes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--out", default=str(HERE.parent / "dist/themes"))
    ap.add_argument("--mock")
    ap.add_argument("--previews")
    ap.add_argument("--release")
    ap.add_argument("--mainui", action="store_true")
    ap.add_argument("--gallery")
    a = ap.parse_args()
    ids = a.ids or sorted(p.stem for p in (HERE / "themes").glob("*.py") if not p.stem.startswith("_"))
    if a.gallery:
        gallery(a.gallery, ids)
        return
    release = Path(a.release) if a.release else None
    if release:
        release.mkdir(parents=True, exist_ok=True)
    catalog = []
    bad = 0
    for i in ids:
        mod = importlib.import_module(f"themes.{i}")
        st = mod.Theme()
        out = Path(a.out) / st.name
        theme_kit.build(st, out)
        probs = theme_kit.check(out)
        size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) // 1024
        print(f"{i}: {out} ({size} KB){'' if not probs else ' PROBLEMS: ' + '; '.join(probs)}")
        bad += bool(probs)
        if a.mock:
            Path(a.mock).mkdir(parents=True, exist_ok=True)
            mock_screens.sheet(out).convert("RGB").save(Path(a.mock) / f"{i}-mock.png")
        if a.previews:
            Path(a.previews).mkdir(parents=True, exist_ok=True)
            shutil.copy(out / "preview.png", Path(a.previews) / f"{i}.png")
        if release:
            write_zip(out, st.name, release / f"{i}.zip")
            shutil.copy(out / "preview.png", release / f"{i}.png")
            cfg = json.loads((out / "config.json").read_text())
            catalog.append({"id": i, "name": st.name, "author": st.author, "description": st.description,
                            "zip": f"{i}.zip", "preview": f"{i}.png",
                            "size": (release / f"{i}.zip").stat().st_size,
                            "stamp": cfg.get("mainui", {}).get("stamp", "")})
    if release:
        (release / "catalog.json").write_text(json.dumps({"version": 1, "themes": catalog}, indent=2) + "\n")
        print(f"release: {release} ({len(catalog)} themes)")
    if a.mainui:
        subprocess.run([sys.executable, str(HERE / "make_mainui_theme.py"), str(Path(a.out) / "MainUI")], check=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
