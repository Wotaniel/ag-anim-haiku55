#!/usr/bin/env python3
"""Валидация .keyshape перед сдачей.

Проверяет: zip цел и содержит document.keyshapex; XML парсится; playRange в мс = длина лупа;
для каждого ks:animate / ks:animateMotion: ключи в секундах возрастают, начинаются с 0,
заканчиваются длиной лупа; timing-functions = ключей − 1; значения = ключей;
repeat-end="indefinite"; motion path — абсолютный, вершин = ключей, первая = translate группы;
scale — пары "x,y"; ids уникальны; url(#…) ссылаются на существующие определения.
Печатает итог, при ошибке — ненулевой код выхода.
"""
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KS_NS = "{http://ns.keyshapeapp.com}"
LOOP = 12.0
ERR = []


def err(msg):
    ERR.append(msg)


def nums(s):
    return [float(x) for x in s.split(";")] if s else []


def parent_map(root):
    return {c: p for p in root.iter() for c in p}


def check_channel(el, label):
    keys = nums(el.get("abs-key-times"))
    if not keys:
        err(f"{label}: нет abs-key-times")
        return
    if keys[0] != 0:
        err(f"{label}: первый ключ {keys[0]} != 0")
    if abs(keys[-1] - LOOP) > 1e-6:
        err(f"{label}: последний ключ {keys[-1]} != длине лупа {LOOP}")
    if any(b <= a for a, b in zip(keys, keys[1:])):
        err(f"{label}: ключи не возрастают: {keys}")
    tf = el.get("timing-functions")
    if tf is None or len(tf.split(";")) != len(keys) - 1:
        n = 0 if tf is None else len(tf.split(";"))
        err(f"{label}: timing-functions={n}, ожидалось {len(keys) - 1}")
    if el.get("repeat-end") != "indefinite":
        err(f"{label}: repeat-end != indefinite")
    if el.tag == KS_NS + "animateMotion":
        pts = el.get("path", "")
        if not pts.startswith("M"):
            err(f"{label}: path не начинается с M")
        if re.search(r"[CcQqSsAaZzHhVvmlr]", pts.replace("M", "").replace("L", "")):
            err(f"{label}: path содержит неподдержанные команды")
        verts = [p for p in re.split(r"[ML]", pts) if p]
        if len(verts) != len(keys):
            err(f"{label}: вершин {len(verts)} != ключей {len(keys)}")
        return keys, verts
    vals = el.get("values", "").split(";")
    if len(vals) != len(keys):
        err(f"{label}: значений {len(vals)} != ключей {len(keys)}")
    if el.get("type") == "scale":
        for v in vals:
            if len(v.split(",")) != 2:
                err(f"{label}: scale-значение не пара x,y: {v}")
    return keys, vals


def validate(path):
    ERR.clear()
    print(f"\n== {path.name}")
    if not zipfile.ZipFile(path).testzip() is None:
        err("zip повреждён")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if names != ["document.keyshapex"]:
            err(f"состав архива: {names}")
        raw = z.read("document.keyshapex")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print("XML: ПАРСИНГ НЕ УДАЛСЯ:", e)
        return False
    pm = parent_map(root)
    if root.get(KS_NS + "playRangeOut") != str(int(LOOP * 1000)):
        err(f"playRangeOut={root.get(KS_NS + 'playRangeOut')} != {int(LOOP * 1000)} мс")
    if root.get(KS_NS + "playRangeIn") != "0":
        err("playRangeIn != 0")

    ids = [e.get("id") for e in root.iter() if e.get("id")]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        err(f"дублирующиеся id: {sorted(dup)}")
    defined = set(ids)
    text = raw.decode("utf-8")
    for ref in set(re.findall(r"url\(#([^)]+)\)", text)):
        if ref not in defined:
            err(f"url(#{ref}) не определён")

    n_motion = n_anim = 0
    for el in root.iter():
        if el.tag not in (KS_NS + "animate", KS_NS + "animateMotion"):
            continue
        parent = pm[el]
        label = f"{parent.get('id', parent.tag)}/{el.tag.split('}')[1]}"
        if el.tag == KS_NS + "animateMotion":
            n_motion += 1
            res = check_channel(el, label)
            tr = parent.get("transform", "")
            m = re.match(r"translate\(([-\d.]+),([-\d.]+)\)", tr)
            if res and m:
                x0, y0 = float(m.group(1)), float(m.group(2))
                # первая вершина path = позиция группы (Keyshape: позиция до движения = translate)
                fx, fy = [float(v) for v in re.search(r"M([-\d.]+),([-\d.]+)", el.get("path")).groups()]
                if abs(fx - x0) > 1e-3 or abs(fy - y0) > 1e-3:
                    err(f"{label}: первая точка path ({fx},{fy}) != translate группы ({x0},{y0})")
            elif res and not m:
                err(f"{label}: motion без translate у группы")
        else:
            n_anim += 1
            check_channel(el, label)

    print(f"каналов: motion={n_motion}, animate={n_anim}; id всего={len(ids)}")
    if ERR:
        print(f"ОШИБКИ ({len(ERR)}):")
        for e in ERR:
            print("  -", e)
        return False
    print("OK")
    return True


def main():
    files = sorted(ROOT.glob("*.keyshape"))
    if not files:
        sys.exit("нет *.keyshape в корне")
    ok = all([validate(f) for f in files])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
