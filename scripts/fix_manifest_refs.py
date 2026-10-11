# -*- coding: utf-8 -*-
"""按 H3 提示词里的 <Picture N> 编号，重写 manifest 的 images_in_order。

规则：
  Picture 1 = 该段关键帧（单图段 → storyboards_2pass/{id}.png；多帧段 → storyboards_grid/{id}.png）
  Picture 2..N = 锚图，顺序与各段 subject_definitions 一致
"""
import json
from pathlib import Path

import mvconfig

ROOT = mvconfig.CFG.project_root
MF = ROOT / "production" / "manifest.json"
REF = "assets/references"
FR = "production/storyboards_2pass"
GR = "production/storyboards_grid"

GIRL, GIRL_HEAD, MAN, MAN_HEAD, HOUSE, FIELD = (
    "char-guardian.png", "char-guardian-head.png",
    "char-returnee.png", "char-returnee-head.png", "loc-house.png", "loc-field.png")

MULTI = {"S05", "S06", "S07", "S12"}
# 每段 Picture 2..N 对应的锚图（与 H3 文件里的 Subject 顺序一致）
MAP = {
    "S01": [HOUSE],                       # S1=堂屋, S2=煤油灯 —— 都指向 P2 的堂屋锚图
    "S02": [HOUSE],
    "S03": [GIRL, GIRL_HEAD, HOUSE],
    "S04": [GIRL, GIRL_HEAD, HOUSE],
    "S05": [GIRL, MAN, HOUSE],
    "S06": [GIRL, MAN, HOUSE],
    "S07": [GIRL, MAN, HOUSE],            # 村巷无独立锚图，用老屋（巷子两侧即白墙老屋）代
    "S08": [GIRL, HOUSE],
    "S09": [GIRL, MAN, HOUSE],
    "S10": [GIRL, HOUSE],
    "S11": [GIRL, MAN, HOUSE],
    "S12": [GIRL, MAN, HOUSE],
    "S13": [GIRL, MAN, HOUSE],
}

data = json.loads(MF.read_text(encoding="utf-8"))
for t in data["tasks"]:
    sid = t["id"]
    head = f"{GR}/{sid}.png" if sid in MULTI else f"{FR}/{sid}.png"
    t["images_in_order"] = [head] + [f"{REF}/{n}" for n in MAP[sid]]
MF.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for t in data["tasks"]:
    print(t["id"], "->", [p.split('/')[-1] for p in t["images_in_order"]])
