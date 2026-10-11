# -*- coding: utf-8 -*-
"""走本地 Krea 2 文生图出场景锚图（挂同一套 MJ 风格 LoRA 栈，保证风格与锚图一致）。

用法：
    python run_krea2_t2i.py loc-field            # 读 anchor_prompts/loc-field.txt
    python run_krea2_t2i.py loc-field --w 1376 --h 768 --steps 10

提示词文件格式：含一行「提示词：」，正文在下一行。
输出：assets/references/{name}.png
"""
import argparse
import json
import random
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

import mvconfig

CFG = mvconfig.CFG
ROOT = CFG.project_root
PROMPTS = ROOT / "production" / "anchor_prompts"
OUT = ROOT / "assets" / "references"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

UNET = CFG.model("krea2_unet")
CLIP = CFG.model("krea2_clip")
VAE = CFG.model("krea2_vae")
# 与 run_krea2_edit.py 相同的干净 MJ 风格栈（不含 krea2_10000，避免武侠偏置）
MJ_LORAS = list(CFG.mj_loras)


def read_prompt(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith("提示词：") and i + 1 < len(lines):
            return lines[i + 1].strip()
    raise SystemExit(f"{path} 里找不到「提示词：」")


def build(prompt, w, h, seed, steps, cfg, neg):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
    }
    src = ["1", 0]
    for i, (name, st) in enumerate(MJ_LORAS):
        nid = str(200 + i)
        g[nid] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": src, "lora_name": name, "strength_model": st}}
        src = [nid, 0]
    g["9"] = {"class_type": "KSampler",
              "inputs": {"model": src, "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "euler", "scheduler": "simple",
                         "positive": ["6", 0], "negative": ["7", 0],
                         "latent_image": ["8", 0], "denoise": 1.0}}
    g["10"] = {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}}
    g["11"] = {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "K2T2I"}}
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--w", type=int, default=CFG.defv("still_w"))
    ap.add_argument("--h", type=int, default=CFG.defv("still_h"))
    ap.add_argument("--steps", type=int, default=CFG.defv("krea2_steps"))
    ap.add_argument("--cfg", type=float, default=CFG.defv("krea2_cfg"))
    ap.add_argument("--neg", default="")
    ap.add_argument("--seed", type=int, default=-1)
    a = ap.parse_args()

    pf = PROMPTS / f"{a.name}.txt"
    prompt = read_prompt(pf)
    seed = random.randint(1, 2**31 - 1) if a.seed < 0 else a.seed
    print(f"[{a.name}] seed={seed} steps={a.steps} {a.w}x{a.h}")
    g = build(prompt, a.w, a.h, seed, a.steps, a.cfg, a.neg)
    req = urllib.request.Request(SERVER + "/prompt",
                                 data=json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode(),
                                 headers={"Content-Type": "application/json"})
    pid = json.load(urllib.request.urlopen(req, timeout=60)).get("prompt_id")
    print("  queued", pid)
    t0 = time.time()
    while True:
        time.sleep(3)
        try:
            hist = json.load(urllib.request.urlopen(f"{SERVER}/history/{pid}", timeout=20))
        except Exception:
            continue
        if pid in hist:
            e = hist[pid]
            if e.get("status", {}).get("status_str") == "error":
                print("  出错:", json.dumps(e["status"], ensure_ascii=False)[:800]); return
            imgs = []
            for o in e.get("outputs", {}).values():
                imgs += o.get("images", [])
            if imgs:
                src = COMFY_OUT / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                OUT.mkdir(parents=True, exist_ok=True)
                dst = OUT / f"{a.name}.png"
                shutil.copyfile(src, dst)
                print(f"  done {time.time()-t0:.0f}s -> {dst}")
                return
            print("  无输出"); return
        if time.time() - t0 > 1800:
            print("  超时"); return


if __name__ == "__main__":
    main()
