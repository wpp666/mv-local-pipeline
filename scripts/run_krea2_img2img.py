# -*- coding: utf-8 -*-
"""Krea 2 图生图「风格遍」：拿别人（如 Qwen 2.1）合成好的构图，用低去噪重渲染成 Krea/MJ 风格。

用法：
    python run_krea2_img2img.py S03 --denoise 0.45
    python run_krea2_img2img.py S03 --denoise 0.55

提示词文件 production/krea2_style_prompts/{name}.txt：
    图1 = <输入图路径>
    提示词：
    <画面内容 + 风格描述>
输出：production/storyboards_2pass/{name}.png
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
PROMPTS = ROOT / "production" / "krea2_style_prompts"
OUT = ROOT / "production" / "storyboards_2pass"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

UNET = CFG.model("krea2_unet")
CLIP = CFG.model("krea2_clip")
VAE = CFG.model("krea2_vae")
MJ_LORAS = list(CFG.mj_loras)
NEG = "多余的肢体, 畸形, 扭曲的脖子, 人体比例错误, 剑, 武器, 头饰"


def parse(path):
    src, prompt, lines = None, "", path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("图") and "=" in s and src is None:
            src = Path(s.split("=", 1)[1].strip())
        if s.startswith("提示词：") and i + 1 < len(lines):
            prompt = lines[i + 1].strip()
    return src, prompt


def upload(path):
    b = "----" + uuid.uuid4().hex
    body = f"--{b}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n" + path.read_bytes() + b"\r\n"
    for k, v in (("overwrite", "true"), ("type", "input")):
        body += f"--{b}\r\n".encode() + f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(SERVER + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    sub = r.get("subfolder") or ""
    return f"{sub}/{r['name']}" if sub else r["name"]


def build(img, prompt, w, h, seed, steps, denoise, cfg):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "10": {"class_type": "LoadImage", "inputs": {"image": img, "upload": "image"}},
        "18": {"class_type": "ImageResizeKJv2",
               "inputs": {"image": ["10", 0], "width": w, "height": h,
                          "upscale_method": "lanczos", "keep_proportion": "resize",
                          "pad_color": "0, 0, 0", "crop_position": "center",
                          "divisible_by": 8, "device": "cpu"}},
        "20": {"class_type": "VAEEncode", "inputs": {"pixels": ["18", 0], "vae": ["4", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": NEG if cfg > 1 else ""}},
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
                         "latent_image": ["20", 0], "denoise": denoise}}
    g["11"] = {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}}
    g["12"] = {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "K2I2I"}}
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--denoise", type=float, default=CFG.defv("img2img_denoise"))
    ap.add_argument("--w", type=int, default=CFG.defv("still_w"))
    ap.add_argument("--h", type=int, default=CFG.defv("still_h"))
    ap.add_argument("--steps", type=int, default=CFG.defv("krea2_steps"))
    ap.add_argument("--cfg", type=float, default=CFG.defv("krea2_cfg"))
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--identity", type=float, default=0.0,
                    help=">0 时在风格遍额外挂 Krea2 编辑身份 LoRA，用于保人物形象")
    a = ap.parse_args()
    if a.identity > 0:
        MJ_LORAS.insert(0, (CFG.model("krea2_identity_lora"), a.identity))
        print("已挂 identity LoRA 强度", a.identity)
    for name in a.names:
        pf = PROMPTS / f"{name}.txt"
        if not pf.exists():
            print(f"[skip] {name}: 无 {pf}"); continue
        srcp, prompt = parse(pf)
        if not srcp or not srcp.exists():
            print(f"[skip] {name}: 输入图不存在 {srcp}"); continue
        up = upload(srcp)
        seed = random.randint(1, 2**31 - 1) if a.seed < 0 else a.seed
        print(f"[{name}] src={srcp.name} denoise={a.denoise} seed={seed}")
        g = build(up, prompt, a.w, a.h, seed, a.steps, a.denoise, a.cfg)
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
                    print("  出错:", json.dumps(e["status"], ensure_ascii=False)[:600]); break
                imgs = []
                for o in e.get("outputs", {}).values():
                    imgs += o.get("images", [])
                if imgs:
                    f = COMFY_OUT / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                    OUT.mkdir(parents=True, exist_ok=True)
                    dst = OUT / f"{name}{a.tag}.png"
                    shutil.copyfile(f, dst)
                    print(f"  done {time.time()-t0:.0f}s -> {dst}")
                else:
                    print("  无输出")
                break
            if time.time() - t0 > 1800:
                print("  超时"); break


if __name__ == "__main__":
    main()
