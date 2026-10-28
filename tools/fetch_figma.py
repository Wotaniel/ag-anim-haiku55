#!/usr/bin/env python3
"""Выгрузка кусков AG-60517 из Figma (REST, только GET/чтение).

Ключ файла: ветка HAd3I2CYWl0dzYKKN5cKiC (макеты лежат в ней, не в основном файле).
Токен берётся из env FIGMA_API_KEY, в репозиторий не пишется.

Позиция каждого куска = absoluteRenderBounds узла минус absoluteBoundingBox кадра.
REST-экспорт SVG отдаёт содержимое по render-bounds (ink для текста), поэтому
позиционировать по bbox нельзя — это даёт сдвиг текста.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

FILE_KEY = "HAd3I2CYWl0dzYKKN5cKiC"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "pieces"
REF = ROOT / "reference"
TOKEN = os.environ.get("FIGMA_API_KEY", "")

FRAMES = {"card16x9": "3187:2995", "details9x16": "3187:3529"}

# имя куска -> (node id, в каком кадре)
PIECES = {
    "card16x9": {
        "glow": ("3187:2996", "card16x9"),
        "character-bust": ("3187:3022", "card16x9"),
        "badge": ("3187:2997", "card16x9"),
        "title": ("3187:2999", "card16x9"),
        "subtitle": ("3187:3000", "card16x9"),
        "features": ("3187:3001", "card16x9"),
    },
    "details9x16": {
        "glow": ("3187:3530", "details9x16"),
        "character-full": ("3187:3531", "details9x16"),
        "badge": ("3187:4163", "details9x16"),
        "title": ("3187:4165", "details9x16"),
        "subtitle": ("3187:4166", "details9x16"),
        "features": ("3187:4167", "details9x16"),
    },
}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def get(url, binary=False):
    """GET с повтором до 3 раз при сетевых сбоях/5xx (пауза 15–30 с)."""
    last = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"X-Figma-Token": TOKEN})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except Exception as e:  # сетевые сбои, 5xx
            last = e
            log(f"  попытка {attempt} не удалась: {e}; пауза 20 с")
            time.sleep(20)
    raise RuntimeError(f"GET не удался после 3 попыток: {last}")


def fetch_nodes(ids):
    q = urllib.parse.urlencode({"ids": ",".join(ids), "depth": 0})
    return get(f"https://api.figma.com/v1/files/{FILE_KEY}/nodes?{q}")["nodes"]


def fetch_images(ids, fmt, extra=""):
    q = f"ids={','.join(ids)}&format={fmt}{extra}"
    res = get(f"https://api.figma.com/v1/images/{FILE_KEY}?{q}")
    if res.get("err"):
        raise RuntimeError(res["err"])
    return res["images"]


def download(url, dest):
    dest.write_bytes(get(url, binary=True))


def main():
    if not TOKEN:
        sys.exit("FIGMA_API_KEY не задан в окружении")
    ASSETS.mkdir(parents=True, exist_ok=True)
    REF.mkdir(parents=True, exist_ok=True)

    all_ids = list(FRAMES.values())
    for frame_pieces in PIECES.values():
        all_ids += [nid for nid, _ in frame_pieces.values()]
    nodes = fetch_nodes(all_ids)
    log(f"узлы получены: {len(nodes)}")

    def doc(nid):
        return nodes[nid]["document"]

    meta = {"file": FILE_KEY, "frames": {}, "pieces": {}}
    for fname, fid in FRAMES.items():
        fb = doc(fid)["absoluteBoundingBox"]
        meta["frames"][fname] = {
            "node": fid,
            "width": fb["width"],
            "height": fb["height"],
            "origin_abs": [fb["x"], fb["y"]],
        }

    jobs_svg = []
    jobs_png = []
    for fname, pieces in PIECES.items():
        fb = meta["frames"][fname]["origin_abs"]
        for pname, (nid, _) in pieces.items():
            d = doc(nid)
            rb = d.get("absoluteRenderBounds") or d["absoluteBoundingBox"]
            rel = [round(rb["x"] - fb[0], 3), round(rb["y"] - fb[1], 3),
                   round(rb["width"], 3), round(rb["height"], 3)]
            key = f"{fname}/{pname}"
            meta["pieces"][key] = {"node": nid, "name": d["name"], "type": d["type"],
                                   "rel_xywh": rel}
            if pname == "glow":
                jobs_png.append((key, nid))
            else:
                jobs_svg.append((key, nid))

    # SVG-куски: текст в контурах, без фильтров; растров в макетах нет
    imgs = fetch_images([nid for _, nid in jobs_svg], "svg",
                        "&svg_outline_text=true&svg_include_id=false&svg_simplify_stroke=true")
    for key, nid in jobs_svg:
        url = imgs.get(nid)
        if not url:
            raise RuntimeError(f"нет SVG для {key} ({nid})")
        out = ASSETS / (key.replace("/", "__") + ".svg")
        download(url, out)
        log(f"svg {key}: {out.stat().st_size} байт")

    # PNG свечения (LAYER_BLUR рендерится Figma, в Keyshape фильтров нет — возьмём альфу)
    imgs = fetch_images([nid for _, nid in jobs_png], "png", "&scale=1")
    for key, nid in jobs_png:
        out = REF / ("glow__" + key.split("/")[0] + ".png")
        download(imgs[nid], out)
        log(f"png {key}: {out.stat().st_size} байт")

    # эталонные рендеры кадров для сверки
    imgs = fetch_images(list(FRAMES.values()), "png", "&scale=1")
    for fname, fid in FRAMES.items():
        out = REF / f"frame__{fname}.png"
        download(imgs[fid], out)
        log(f"эталон {fname}: {out.stat().st_size} байт")

    (ROOT / "assets" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    log("готово: assets/meta.json")


if __name__ == "__main__":
    main()
