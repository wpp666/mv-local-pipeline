# -*- coding: utf-8 -*-
"""重排 manifest.json 里每段的 images_in_order（H3 的 <Picture N> 顺序）。

规则：
  Picture 1 = 该段关键帧（单图段 storyboards_2pass/{id}.png；多帧段 storyboards_grid/{id}.png）
  Picture 2..N = 该段各帧提示词用到的参考图，按「场景 → 人物 → 道具」排序，
                 同一类内按其在各帧里首次出现的顺序。

参考图集合直接从 production/storyboard_prompts/ 的 Sxx*.txt 汇总，避免手工维护漂移。
"""
import json
import re
from pathlib import Path

import mvconfig

ROOT = mvconfig.CFG.project_root
MF = ROOT / "production" / "manifest.json"
PD = ROOT / "production" / "storyboard_prompts"
FR = "production/storyboards_2pass"
GR = "production/storyboards_grid"

MULTI = {"S04", "S05", "S06", "S09", "S13", "S14"}
CAT = {"loc-": 0, "char-": 1, "prop-": 2}


def frame_refs(sid):
    """该段所有帧文件里出现的参考图（去重、保持首次出现顺序）。"""
    out = []
    for f in sorted(PD.glob(f"{sid}-*.txt")) or [PD / f"{sid}.txt"]:
        if not f.exists():
            continue
        for ln in f.read_text(encoding="utf-8").splitlines():
            # 参考图行：官方多图编辑的引用标记是 <imageN>；兼容旧写法「图N =」。
            m = re.match(r"^(?:图\s*\d+|<image\d+>)\s*=\s*(.+)$", ln.strip())
            if m:
                p = m.group(1).strip()
                if p not in out:
                    out.append(p)
    return out


def rank(item):
    name = Path(item[1]).name
    cat = 3
    for k, v in CAT.items():
        if name.startswith(k):
            cat = v
    return (cat, item[0])


data = json.loads(MF.read_text(encoding="utf-8"))
for t in data["tasks"]:
    sid = t["id"]
    kf = f"{GR}/{sid}.png" if sid in MULTI else f"{FR}/{sid}.png"
    refs = [(i, p) for i, p in enumerate(frame_refs(sid))]
    refs.sort(key=rank)
    files = [rf[len(str(ROOT)) + 1:].replace("\\", "/") for _, rf in refs]
    t["images_in_order"] = [kf] + files

MF.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for t in data["tasks"]:
    print(t["id"], "->", [p.split("/")[-1] for p in t["images_in_order"]])
