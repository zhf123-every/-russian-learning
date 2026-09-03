#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 OpenRussian 开源词典 CSV（CC BY-SA 4.0）处理成 dict-full.js 离线词典。"""
import csv, json, os

BASE = os.path.dirname(os.path.abspath(__file__))

def rows(fn):
    with open(os.path.join(BASE, "data", fn), encoding="utf-8") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)  # 跳过表头
        for row in r:
            yield row

out = {}
counts = {"n": 0, "v": 0, "a": 0, "o": 0}

def add(word, entry):
    if not word or word in out:
        return
    out[word] = entry
    counts[entry["p"]] += 1

# 名词：完整 6×2 变格
for r in rows("nouns.csv"):
    if len(r) < 22:
        continue
    bare, acc, en, de, gender, partner, animate, indecl, sg_only, pl_only = r[:10]
    sg_nom, sg_gen, sg_dat, sg_acc, sg_inst, sg_prep = r[10:16]
    pl_nom, pl_gen, pl_dat, pl_acc, pl_inst, pl_prep = r[16:22]
    e = {"p": "n", "e": en}
    if acc:
        e["s"] = acc
    if gender:
        e["g"] = gender
    if animate in ("1", "true", "True"):
        e["a"] = 1
    e["f"] = {
        "sg": [sg_nom, sg_gen, sg_dat, sg_acc, sg_inst, sg_prep],
        "pl": [pl_nom, pl_gen, pl_dat, pl_acc, pl_inst, pl_prep],
    }
    add(bare, e)

# 动词：变位 + 体 + 配对 + 命令式 + 过去时
for r in rows("verbs.csv"):
    if len(r) < 18:
        continue
    bare, acc, en, de, aspect, partner = r[:6]
    imp_sg, imp_pl = r[6], r[7]
    past_m, past_f, past_n, past_pl = r[8:12]
    p1, p2, p3, p4, p5, p6 = r[12:18]
    e = {"p": "v", "e": en}
    if acc:
        e["s"] = acc
    if aspect:
        e["asp"] = aspect[0]  # i / p
    if partner:
        e["part"] = partner
    e["f"] = {
        "imp": [imp_sg, imp_pl],
        "past": [past_m, past_f, past_n, past_pl],
        "pres": [p1, p2, p3, p4, p5, p6],
    }
    add(bare, e)

# 形容词：比较级/最高级/短尾 + 四性六格全变格
for r in rows("adjectives.csv"):
    if len(r) < 34:
        continue
    bare, acc, en, de, comp, sup, sh_m, sh_f, sh_n, sh_pl = r[:10]
    dm = r[10:16]; df = r[16:22]; dn = r[22:28]; dpl = r[28:34]
    e = {"p": "a", "e": en}
    if acc:
        e["s"] = acc
    if comp:
        e["cmp"] = comp
    if sup:
        e["sup"] = sup
    e["f"] = {
        "m": dm, "f": df, "n": dn, "pl": dpl,
        "sh": [sh_m, sh_f, sh_n, sh_pl],
    }
    add(bare, e)

# 其它：代词/副词/数词等，仅释义
for r in rows("others.csv"):
    if len(r) < 4:
        continue
    bare, acc, en, de = r[:4]
    e = {"p": "o", "e": en}
    if acc:
        e["s"] = acc
    add(bare, e)

out_path = os.path.join(BASE, "dict-full.js")
with open(out_path, "w", encoding="utf-8") as f:
    f.write("window.RU_DICT_FULL=")
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    f.write(";")

size = os.path.getsize(out_path)
print("总词条:", len(out), "| 名词:", counts["n"], "动词:", counts["v"],
      "形容词:", counts["a"], "其它:", counts["o"])
print("输出:", out_path)
print("大小: %.2f MB" % (size / 1024 / 1024))
