# -*- coding: utf-8 -*-
"""把多帧段（S05/S06/S07/S12）的 4 张分镜帧合成 2×2 四宫格，作为该段 H3 的 Picture 1。

每帧 1376×768（16:9），2×2 无间隙拼接后仍为 16:9。
输入：production/storyboards_2pass/{seg}-1..4.png
输出：production/storyboards_grid/{seg}.png
"""
from pathlib import Path
from PIL import Image

import mvconfig

ROOT = mvconfig.CFG.project_root
SRC = ROOT / "production" / "storyboards_2pass"
OUT = ROOT / "production" / "storyboards_grid"
SEGS = ["S05", "S06", "S07", "S12"]

OUT.mkdir(parents=True, exist_ok=True)
for seg in SEGS:
    frames = [SRC / f"{seg}-{i}.png" for i in range(1, 5)]
    missing = [f.name for f in frames if not f.exists()]
    if missing:
        print(f"[skip] {seg}: 缺 {missing}")
        continue
    imgs = [Image.open(f).convert("RGB") for f in frames]
    w, h = imgs[0].size
    canvas = Image.new("RGB", (w * 2, h * 2))
    for idx, im in enumerate(imgs):
        canvas.paste(im, ((idx % 2) * w, (idx // 2) * h))
    dst = OUT / f"{seg}.png"
    canvas.save(dst)
    print(f"{seg}: {dst.name}  {canvas.size[0]}x{canvas.size[1]}")
