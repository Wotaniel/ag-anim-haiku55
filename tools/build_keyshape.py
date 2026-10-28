#!/usr/bin/env python3
"""Сборка .keyshape для AG-60517 (Event Card 16:9 и Event Details 9:16) и превью index.html.

Одна модель сцены даёт два вывода:
  * document.keyshapex внутри .keyshape (zip) — рабочий файл для Keyshape;
  * SMIL-превью в index.html — только для проверки движения в браузере и на Pages.

Правила формата (спека keyshapeapp.com/file-format + референс AG Store image animation):
  * abs-key-times и ks:animate* — в секундах; ks:playRangeIn/Out — в миллисекундах;
  * timing-functions = ключей − 1; repeat-end="indefinite"; последний ключ = длина лупа;
  * ks:animate type=scale — пары "x,y"; ks:animateMotion path — абсолютный в координатах
    родителя, первая точка = позиция группы (translate у группы);
  * группа с translate(P) масштабируется вокруг P; если её контент абсолютный,
    внутри группы ставится компенсатор translate(-P).

Запуск: python3 tools/build_keyshape.py
"""
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIECES = ROOT / "assets" / "pieces"
META = ROOT / "assets" / "meta.json"
GLOW_PROFILE = ROOT / "assets" / "glow_profile.json"
GLOW_PNG = ROOT / "reference" / "glow__card16x9.png"

LOOP = 12.0  # длина лупа, секунды
EASE = "cubic-bezier(0.45,0,0.55,1)"
GLOW_COLOR = "#67B279"  # из макета: заливка эллипса свечения
GLOW_R = 1482.0  # полуразмер эллипса 964 + blur 1000 с каждой стороны (радиус градиента)

# Каналы общие для обоих форматов (тайминг одинаковый, амплитуды — в CONFIGS)
CAM_KEYS = [0, 1, 3, 5, 6.6, 9, 12]  # покой / пролёт 1 / замереть / пролёт 2 / замереть / отъезд
BR_KEYS = [0, 2, 4, 6, 8, 10, 12]  # дыхание: период 4 с, три вдоха за луп
BR_SCALE = [(1, 1), (1, 1.008), (1, 1), (1, 1.008), (1, 1), (1, 1.008), (1, 1)]
GLOW_OPS = [0.92, 1, 0.92, 1, 0.92, 1, 0.92]  # в такт груди: максимум свечения на вдохе (2, 6, 10 с)
TW_KEYS = [0, 2.6, 3.3, 4.0, 9.2, 9.9, 10.6, 12]  # блик на короне: два коротких «мерцания»
TW_SCALE = [(0.4, 0.4), (0.4, 0.4), (1, 1), (0.4, 0.4), (0.4, 0.4), (0.8, 0.8), (0.4, 0.4), (0.4, 0.4)]
TW_OPS = [0, 0, 1, 0, 0, 0.9, 0, 0]
SH_MOVE_KEYS = [0, 6.5, 8.6, 12]  # блик по клинку (только 9:16)
SH_OP_KEYS = [0, 6.4, 6.8, 8.2, 8.6, 12]
SH_OPS = [0, 0, 1, 1, 0, 0]

CONFIGS = {
    "16x9": dict(
        name="AG-60517_event-card-16x9",
        title="AG-60517 · Event Card 16:9",
        W=1920, H=1080,
        glow=(1530, 671),  # центр эллипса 3187:2996: rel (1048,189) + 482
        face=(1540, 290),  # пивот камеры — лицо
        chest=(1540, 900),  # пивот дыхания — грудь
        cam=[1, 1, 1.10, 1.10, 1.16, 1.16, 1],
        piece="card16x9", character="character-bust",
        crown=(1543, 138), crown_r=22,  # звезда на короне
        sheen=None,
        slug="c169",
    ),
    "9x16": dict(
        name="AG-60517_event-details-9x16",
        title="AG-60517 · Event Details 9:16",
        W=1080, H=1920,
        glow=(1210, 1001),  # центр эллипса 3187:3530: rel (728,519) + 482
        face=(700, 600),
        chest=(700, 1100),
        cam=[1, 1, 1.05, 1.05, 1.07, 1.07, 1],  # пик 1.07: кончик меча (y≈1830) не уходит за кадр
        piece="details9x16", character="character-full",
        crown=(700, 525), crown_r=18,
        sheen=dict(pos=[(700, 1120), (700, 1120), (705, 1560), (705, 1560)], r=16),  # клинок
        slug="d916",
    ),
}

UI = [("ui-badge", "badge"), ("ui-title", "title"), ("ui-subtitle", "subtitle"), ("ui-chips", "features")]


def fmt(v):
    s = f"{float(v):.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


class Ch:
    """Канал анимации: kind = scale | opacity | motion."""

    def __init__(self, kind, keys, values):
        assert len(keys) == len(values) >= 2, (kind, keys)
        assert keys[0] == 0 and keys[-1] == LOOP, (kind, keys)
        assert all(a < b for a, b in zip(keys, keys[1:])), (kind, keys)
        self.kind, self.keys, self.values = kind, list(keys), list(values)
        self.tf = [EASE] * (len(keys) - 1)


class G:
    """Группа. at = translate(P) (пивот/позиция). comp=True — контент абсолютный, внутри компенсатор."""

    def __init__(self, gid, at=None, ch=(), kids=(), comp=False):
        self.id, self.at, self.ch, self.kids, self.comp = gid, at, list(ch), list(kids), comp
        if comp:
            assert at is not None, gid
        for c in self.ch:
            if c.kind == "motion":
                assert at is not None and tuple(at) == tuple(c.values[0]), f"{gid}: path[0] != translate"
                assert not comp, gid


class Raw:
    def __init__(self, xml):
        self.xml = xml


# ---------- Keyshape XML ----------

def ks_ch(c):
    times = ";".join(fmt(k) for k in c.keys)
    tf = ";".join(c.tf)
    if c.kind == "motion":
        path = "M" + "L".join(f"{fmt(x)},{fmt(y)}" for x, y in c.values)
        return f'<ks:animateMotion abs-key-times="{times}" path="{path}" timing-functions="{tf}" repeat-end="indefinite"/>'
    if c.kind == "scale":
        vals = ";".join(f"{fmt(x)},{fmt(y)}" for x, y in c.values)
        return (f'<ks:animate attribute="transform" type="scale" abs-key-times="{times}" '
                f'values="{vals}" timing-functions="{tf}" repeat-end="indefinite"/>')
    vals = ";".join(fmt(v) for v in c.values)
    return (f'<ks:animate attribute="opacity" abs-key-times="{times}" '
            f'values="{vals}" timing-functions="{tf}" repeat-end="indefinite"/>')


def ks_node(n, ind=0):
    pad = "  " * ind
    if isinstance(n, Raw):
        return pad + n.xml
    attrs = [f'id="{n.id}"']
    if n.at:
        attrs.append(f'transform="translate({fmt(n.at[0])},{fmt(n.at[1])})"')
    ops = [c for c in n.ch if c.kind == "opacity"]
    if ops:
        attrs.append(f'opacity="{fmt(ops[0].values[0])}"')
    lines = [f"{pad}<g {' '.join(attrs)}>"]
    for c in n.ch:
        lines.append(f"{pad}  {ks_ch(c)}")
    if n.comp:
        lines.append(f'{pad}  <g transform="translate({fmt(-n.at[0])},{fmt(-n.at[1])})">')
        lines += [ks_node(k, ind + 2) for k in n.kids]
        lines.append(f"{pad}  </g>")
    else:
        lines += [ks_node(k, ind + 1) for k in n.kids]
    lines.append(f"{pad}</g>")
    return "\n".join(lines)


# ---------- SMIL-превью (только для проверки в браузере) ----------

def spline(tf):
    m = re.match(r"cubic-bezier\(([^)]*)\)", tf)
    return " ".join(m.group(1).split(","))


def smil_ch(c):
    kt = ";".join(fmt(k / LOOP) for k in c.keys)
    ksp = ";".join(spline(t) for t in c.tf)
    common = f'keyTimes="{kt}" calcMode="spline" keySplines="{ksp}" dur="{fmt(LOOP)}s" repeatCount="indefinite"'
    if c.kind == "scale":
        vals = ";".join(f"{fmt(x)} {fmt(y)}" for x, y in c.values)
        return f'<animateTransform attributeName="transform" type="scale" values="{vals}" {common}/>'
    if c.kind == "opacity":
        vals = ";".join(fmt(v) for v in c.values)
        return f'<animate attributeName="opacity" values="{vals}" {common}/>'
    x0, y0 = c.values[0]
    vals = ";".join(f"{fmt(x - x0)},{fmt(y - y0)}" for x, y in c.values)
    return f'<animateTransform attributeName="transform" type="translate" values="{vals}" {common}/>'


def smil_node(n):
    if isinstance(n, Raw):
        return n.xml
    body = "".join(smil_node(k) for k in n.kids)
    if n.comp:
        body = f'<g transform="translate({fmt(-n.at[0])},{fmt(-n.at[1])})">{body}</g>'
    by = {k: [c for c in n.ch if c.kind == k] for k in ("motion", "scale", "opacity")}
    if by["opacity"]:
        c = by["opacity"][0]
        body = f'<g opacity="{fmt(c.values[0])}">{smil_ch(c)}{body}</g>'
    if by["scale"]:
        body = f"<g>{smil_ch(by['scale'][0])}{body}</g>"
    if by["motion"]:
        body = f"<g>{smil_ch(by['motion'][0])}{body}</g>"
    if n.at:
        body = f'<g id="{n.id}" transform="translate({fmt(n.at[0])},{fmt(n.at[1])})">{body}</g>'
    else:
        body = f'<g id="{n.id}">{body}</g>'
    return body


# ---------- Ассеты ----------

def inline_piece(stem, prefix):
    """Внутренность Figma-SVG куска: без корневого <svg>, ids с префиксом (уникальность в документе)."""
    txt = (PIECES / f"{stem}.svg").read_text(encoding="utf-8")
    txt = re.sub(r"<\?xml[^>]*\?>", "", txt).strip()
    m = re.search(r"<svg\b[^>]*>", txt)
    assert m, stem
    inner = txt[m.end():txt.rfind("</svg>")]
    assert "xlink:" not in txt and "<style" not in txt and "class=" not in txt, stem
    ids = set(re.findall(r'(?<![\w-])id="([^"]+)"', inner))
    for i in ids:
        new = f"{prefix}-{i}"
        inner = re.sub(r'(?<![\w-])id="%s"' % re.escape(i), f'id="{new}"', inner)
        inner = inner.replace(f"url(#{i})", f"url(#{new})")
        inner = inner.replace(f'href="#{i}"', f'href="#{new}"')
    refs = set(re.findall(r"url\(#([^)]+)\)", inner))
    defined = set(re.findall(r'(?<![\w-])id="([^"]+)"', inner))
    assert not (refs - defined), (stem, refs - defined)
    return f'<g fill="none">{inner}</g>'


def star_d(R):
    r0 = R * 0.18
    pts = [(0, -R), (r0, -r0), (R, 0), (r0, r0), (0, R), (-r0, r0), (-R, 0), (-r0, -r0)]
    return "M" + "L".join(f"{fmt(x)},{fmt(y)}" for x, y in pts) + "Z"


def star(R):
    return Raw(f'<path fill="#FFFFFF" d="{star_d(R)}"/>')


def glow_profile():
    """Радиальный профиль альфы свечения из Figma-рендера (кешируется в assets/glow_profile.json)."""
    if GLOW_PROFILE.exists():
        return json.loads(GLOW_PROFILE.read_text(encoding="utf-8"))
    import numpy as np
    from PIL import Image

    a = np.array(Image.open(GLOW_PNG))[:, :, 3].astype(float) / 255.0
    h, w = a.shape
    yy, xx = np.indices(a.shape)
    r = np.hypot(xx + 0.5 - w / 2, yy + 0.5 - h / 2)
    stops = []
    for i in range(20):
        t = i / 20
        lo, hi = max(0.0, t - 0.025) * GLOW_R, (t + 0.025) * GLOW_R
        m = (r >= lo) & (r < hi)
        stops.append([round(t, 3), round(float(a[m].mean()), 4)])
    stops.append([1.0, 0.0])
    GLOW_PROFILE.write_text(json.dumps(stops), encoding="utf-8")
    return stops


def build_scene(kind, meta):
    c = CONFIGS[kind]
    slug, piece = c["slug"], c["piece"]

    def pos(key):
        return tuple(meta["pieces"][f"{piece}/{key}"]["rel_xywh"][:2])

    def inner(key):
        return inline_piece(f"{piece}__{key}", f"{slug}-{key}")

    gx, gy = c["glow"]
    glow = G("glow", ch=[Ch("opacity", BR_KEYS, GLOW_OPS)], kids=[
        Raw(f'<ellipse cx="{fmt(gx)}" cy="{fmt(gy)}" rx="{fmt(GLOW_R)}" ry="{fmt(GLOW_R)}" '
            f'fill="url(#glow-gradient-{slug})"/>')])

    # блики едут внутри дыхания: они лежат на персонаже, а не над ним
    character = G("character", at=pos(c["character"]), kids=[Raw(inner(c["character"]))])
    body_kids = [character]
    body_kids.append(G("glint-crown", at=c["crown"],
                       ch=[Ch("scale", TW_KEYS, TW_SCALE), Ch("opacity", TW_KEYS, TW_OPS)],
                       kids=[star(c["crown_r"])]))
    if c["sheen"]:
        s = c["sheen"]
        body_kids.append(G("glint-blade-sheen", at=s["pos"][0],
                           ch=[Ch("motion", SH_MOVE_KEYS, s["pos"]), Ch("opacity", SH_OP_KEYS, SH_OPS)],
                           kids=[star(s["r"])]))
    breath = G("character-breath", at=c["chest"], comp=True,
               ch=[Ch("scale", BR_KEYS, BR_SCALE)], kids=body_kids)
    camera = G("camera-zoom", at=c["face"], comp=True,
               ch=[Ch("scale", CAM_KEYS, [(v, v) for v in c["cam"]])], kids=[breath])

    ui = G("ui", kids=[G(gid, at=pos(key), kids=[Raw(inner(key))]) for gid, key in UI])
    background = G("background", kids=[Raw(f'<rect width="{c["W"]}" height="{c["H"]}" fill="#000000"/>')])
    # порядок как в Figma: фон, свечение, UI, персонаж (сверху)
    return [background, glow, ui, camera]


def gradient_defs(kind, stops):
    c = CONFIGS[kind]
    gx, gy = c["glow"]
    st = "".join(f'<stop offset="{fmt(o)}" stop-color="{GLOW_COLOR}" stop-opacity="{fmt(a)}"/>' for o, a in stops)
    return (f'<radialGradient id="glow-gradient-{c["slug"]}" gradientUnits="userSpaceOnUse" '
            f'cx="{fmt(gx)}" cy="{fmt(gy)}" r="{fmt(GLOW_R)}">{st}</radialGradient>')


def document(kind, stops, meta, mode):
    c = CONFIGS[kind]
    W, H, slug = c["W"], c["H"], c["slug"]
    nodes = build_scene(kind, meta)
    if mode == "ks":
        body = "\n".join(ks_node(n, 1) for n in nodes)
        head = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:ks="http://ns.keyshapeapp.com" '
                f'viewBox="0 0 {W} {H}" ks:preview="svg/css" ks:fps="60" ks:playRangeIn="0" '
                f'ks:playRangeOut="{int(LOOP * 1000)}" ks:version="1.1" style="white-space: pre;">\n'
                f"  <title>{c['title']}</title>\n"
                f'  <ks:export filename="{c["name"]}.svg" format="svg" animation="css" loop-count="0"/>\n')
        clip_attr = ' ks:expand-timeline="collapsed"'
    else:
        body = "".join(smil_node(n) for n in nodes)
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" class="scene" viewBox="0 0 {W} {H}" '
                f'width="{W}" height="{H}">')
        clip_attr = ""
    defs = (gradient_defs(kind, stops)
            + f'<clipPath id="clip-{slug}"{clip_attr}><rect width="{W}" height="{H}"/></clipPath>')
    return f"{head}  <defs>{defs}</defs>\n  <g clip-path=\"url(#clip-{slug})\">\n{body}\n  </g>\n</svg>\n"


def write_keyshape(kind, xml):
    path = ROOT / (CONFIGS[kind]["name"] + ".keyshape")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("document.keyshapex", xml.encode("utf-8"))
    return path


def index_html(previews):
    rows = [
        ("0.0–1.0", "покой: кадр совпадает с макетом Figma"),
        ("1.0–3.0", "пролёт 1: плавный наезд на лицо (16:9 ×1.10, 9:16 ×1.05)"),
        ("3.0–5.0", "замереть; блик на короне 3.3 с"),
        ("5.0–6.6", "пролёт 2: ещё наезд (16:9 ×1.16, 9:16 ×1.07)"),
        ("6.6–9.0", "замереть"),
        ("9.0–12.0", "медленный отъезд к исходному кадру; второй блик на короне 9.9 с"),
        ("6.5–8.6 (только 9:16)", "блик скользит по клинку"),
        ("все 12 с", "дыхание: вертикальное растяжение груди ×1.008 каждые 4 с, свечение дышит в такт; UI статичен"),
    ]
    table = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    figs = []
    for kind, svg in previews:
        cls = "f169" if kind == "16x9" else "f916"
        figs.append(f'<figure class="{cls}">{svg}<figcaption>{CONFIGS[kind]["title"]}</figcaption></figure>')
    files = "".join(
        f'<li><a href="{CONFIGS[k]["name"]}.keyshape">{CONFIGS[k]["name"]}.keyshape</a></li>' for k in CONFIGS)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AG-60517 · анимация Event Card (превью)</title>
<style>
body{{margin:0;background:#141414;color:#ddd;font:15px/1.5 -apple-system,system-ui,sans-serif;padding:24px}}
h1{{font-size:20px;margin:0 0 6px}} h2{{font-size:16px;margin:28px 0 8px}}
.row{{display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap}}
figure{{margin:0}} figcaption{{color:#999;font-size:13px;margin-top:6px}}
.f169 svg{{display:block;width:min(960px,100%);height:auto;background:#000}}
.f916 svg{{display:block;height:80vh;width:auto;background:#000}}
table{{border-collapse:collapse}} td{{padding:4px 14px 4px 0;vertical-align:top}}
td:first-child{{color:#9fd3ab;white-space:nowrap}}
a{{color:#9fd3ab}}
</style></head><body>
<h1>AG-60517 · AdGuard v5 is here — анимация Event Card</h1>
<p>Превью для проверки движения в браузере. Рабочие файлы — <code>.keyshape</code> ниже; превью — SMIL-имитация той же модели.</p>
<div class="row">{''.join(figs)}</div>
<h2>Файлы для Keyshape</h2><ul>{files}</ul>
<h2>Таймлайн (луп 12 с)</h2><table>{table}</table>
<script>
const t = new URLSearchParams(location.search).get('t');
if (t !== null) document.querySelectorAll('svg.scene').forEach(s => {{ s.pauseAnimations(); s.setCurrentTime(parseFloat(t)); }});
</script>
</body></html>
"""


def main():
    meta = json.loads(META.read_text(encoding="utf-8"))
    stops = glow_profile()
    previews = []
    for kind in CONFIGS:
        xml = document(kind, stops, meta, "ks")
        print("written", write_keyshape(kind, xml).name, len(xml), "chars XML")
        previews.append((kind, document(kind, stops, meta, "smil")))
    (ROOT / "index.html").write_text(index_html(previews), encoding="utf-8")
    print("written index.html")


if __name__ == "__main__":
    main()
