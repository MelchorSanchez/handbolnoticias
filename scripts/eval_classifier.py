"""Mide el clasificador contra los artículos corregidos a mano (is_manual=1).

Pasa resolve_sections() por cada artículo manual y compara con la sección y
extra_sections guardadas en la DB (la "verdad"). Imprime precisión y recall por
sección y la lista de fallos. No modifica nada.

Uso:
  python3 scripts/eval_classifier.py                      # resumen
  python3 scripts/eval_classifier.py --section fichajes   # fallos de una sección
  python3 scripts/eval_classifier.py --save antes.json    # guardar predicciones
  python3 scripts/eval_classifier.py --compare antes.json # qué cambió desde entonces

Limitaciones: la DB guarda el resumen traducido y recortado a 300 caracteres y no
guarda las etiquetas del RSS, así que en fuentes extranjeras el resultado puede
diferir del que dio classify() al descargar el artículo.
"""
import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml

from classifier import resolve_sections

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "articles.db"
SOURCES_PATH = ROOT / "config" / "sources.yaml"


def _source_defaults():
    with open(SOURCES_PATH) as f:
        return {s["name"]: s["section"] for s in yaml.safe_load(f)["sources"]}


def _split(section, extra):
    return [section] + [s for s in (extra or "").split("|") if s]


def load_gold(con):
    defaults = _source_defaults()
    rows = con.execute(
        "SELECT id, url, title, title_orig, summary, source_name, section, extra_sections "
        "FROM articles WHERE is_manual = 1"
    ).fetchall()
    gold = []
    unknown_sources = Counter()
    for r in rows:
        default = defaults.get(r["source_name"])
        if default is None:
            # Fuente ya retirada de sources.yaml: aproximamos con el país de la sección guardada
            unknown_sources[r["source_name"]] += 1
            default = r["section"].split("/")[0]
        gold.append({
            "id": r["id"],
            "url": r["url"],
            "title": r["title_orig"] or r["title"],
            "summary": r["summary"] or "",
            "source_name": r["source_name"] or "",
            "default": default,
            "sections": _split(r["section"], r["extra_sections"]),
        })
    return gold, unknown_sources


def predict(item):
    article = {
        "url": item["url"],
        "title_orig": item["title"],
        "summary": item["summary"],
        "source_name": item["source_name"],
        "section": item["default"],
    }
    primary, extras = resolve_sections(article)
    return [primary] + extras


def per_section_counts(gold, preds):
    tp, fp, fn = Counter(), Counter(), Counter()
    for item in gold:
        g, p = set(item["sections"]), set(preds[item["id"]])
        for s in g & p:
            tp[s] += 1
        for s in p - g:
            fp[s] += 1
        for s in g - p:
            fn[s] += 1
    return tp, fp, fn


def _ratio(a, b):
    return a / b if b else float("nan")


def print_summary(gold, preds, min_support):
    n = len(gold)
    primary_ok = sum(preds[i["id"]][0] == i["sections"][0] for i in gold)
    exact_ok = sum(set(preds[i["id"]]) == set(i["sections"]) for i in gold)
    tp, fp, fn = per_section_counts(gold, preds)
    TP, FP, FN = sum(tp.values()), sum(fp.values()), sum(fn.values())

    print(f"Artículos manuales: {n}")
    print(f"  Sección principal correcta: {primary_ok}/{n} ({_ratio(primary_ok, n):.1%})")
    print(f"  Todas las secciones exactas: {exact_ok}/{n} ({_ratio(exact_ok, n):.1%})")
    print(f"  Global (todas las secciones): precisión {_ratio(TP, TP + FP):.1%}, "
          f"recall {_ratio(TP, TP + FN):.1%}  (TP {TP}, FP {FP}, FN {FN})")
    print()
    print(f"{'sección':32} {'real':>5} {'TP':>4} {'FP':>4} {'FN':>4} {'precisión':>10} {'recall':>7}")
    sections = set(tp) | set(fp) | set(fn)
    rows = []
    for s in sections:
        support = tp[s] + fn[s]
        if support + fp[s] < min_support:
            continue
        rows.append((s, support, tp[s], fp[s], fn[s]))
    # Las secciones con más errores primero
    rows.sort(key=lambda r: (-(r[3] + r[4]), r[0]))
    for s, support, t, f_p, f_n in rows:
        print(f"{s:32} {support:5} {t:4} {f_p:4} {f_n:4} "
              f"{_ratio(t, t + f_p):10.0%} {_ratio(t, t + f_n):7.0%}")


def print_failures(gold, preds, section):
    fps, fns = [], []
    for item in gold:
        g, p = set(item["sections"]), set(preds[item["id"]])
        if section in p - g:
            fps.append(item)
        if section in g - p:
            fns.append(item)
    for label, items in (("Falsos positivos", fps), ("Falsos negativos", fns)):
        print(f"\n{label} de {section}: {len(items)}")
        for item in items:
            print(f"  [{item['id']}] {item['source_name']}: {item['title'][:100]}")
            print(f"      real: {'|'.join(item['sections'])}")
            print(f"      pred: {'|'.join(preds[item['id']])}")


def print_compare(gold, preds, old_preds):
    better, worse, other = [], [], []
    for item in gold:
        old, new = old_preds.get(item["id"]), preds[item["id"]]
        if old is None or set(old) == set(new) and old[0] == new[0]:
            continue
        g = set(item["sections"])
        # Errores = secciones de más + secciones que faltan + 1 si la principal está mal
        def errors(p):
            return len(set(p) ^ g) + (p[0] != item["sections"][0])
        e_old, e_new = errors(old), errors(new)
        bucket = better if e_new < e_old else worse if e_new > e_old else other
        bucket.append((item, old, new))
    for label, items in (("Mejoran", better), ("Empeoran", worse), ("Cambian sin mejorar ni empeorar", other)):
        print(f"\n{label}: {len(items)}")
        for item, old, new in items:
            print(f"  [{item['id']}] {item['source_name']}: {item['title'][:100]}")
            print(f"      real:  {'|'.join(item['sections'])}")
            print(f"      antes: {'|'.join(old)}")
            print(f"      ahora: {'|'.join(new)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", help="listar falsos positivos y negativos de esta sección")
    ap.add_argument("--min-support", type=int, default=1,
                    help="ocultar secciones con menos apariciones (reales + predichas)")
    ap.add_argument("--save", type=Path, help="guardar las predicciones en un JSON")
    ap.add_argument("--compare", type=Path, help="comparar con predicciones guardadas antes")
    args = ap.parse_args()

    logging.disable(logging.WARNING)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    gold, unknown_sources = load_gold(con)
    preds = {item["id"]: predict(item) for item in gold}

    print_summary(gold, preds, args.min_support)
    if unknown_sources:
        print(f"\nAviso: {sum(unknown_sources.values())} artículos de fuentes que ya no están "
              f"en sources.yaml ({', '.join(sorted(unknown_sources))}); "
              "se usa el país de su sección como sección por defecto.")
    if args.section:
        print_failures(gold, preds, args.section)
    if args.compare:
        print_compare(gold, preds, json.loads(args.compare.read_text()))
    if args.save:
        args.save.write_text(json.dumps(preds, ensure_ascii=False, indent=0))
        print(f"\nPredicciones guardadas en {args.save}")


if __name__ == "__main__":
    main()
