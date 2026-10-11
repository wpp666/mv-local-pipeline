# -*- coding: utf-8 -*-
"""Krea 2 风格参考遍：内容来自我们的图（latent），风格来自参考图（image1/2/3）。

机制来自官方模板 image_krea2_turbo_int8_image_style_reference.json：
  LoraLoaderModelOnly(krea2_style_reference) + TextEncodeQwenImageEditPlus(image1..3)
  + FluxKontextMultiReferenceLatentMethod + CFGGuider + SamplerCustomAdvanced

用法：
    python run_krea2_styleref.py S13 --denoise 0.60
    python run_krea2_styleref.py S13 --denoise 0.60 --ref <风格参考图路径>

默认参考图取 style_prompts 文件里的「图2 = ...」行（若有），否则用 图1 同目录的 loc-house.png。
输出：production/storyboards_styleref/{name}.png
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
OUT = ROOT / "production" / "storyboards_styleref"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

UNET = CFG.model("krea2_unet")
STYLE_LORA = CFG.model("krea2_style_lora")
CLIP = CFG.model("krea2_clip")
VAE = CFG.model("krea2_vae")


def parse(path):
    src, prompt, lines = None, "", path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("图1") and "=" in s and src is None:
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


def build(img, ref, prompt, w, h, seed, steps, denoise, cfg):
    """img=None 时走官方纯文生图接线（空 latent）；img 有值时才走图生图。"""
    g = {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "15": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["10", 0], "lora_name": STYLE_LORA, "strength_model": 1.0}},
        "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "50": {"class_type": "LoadImage", "inputs": {"image": ref, "upload": "image"}},
        "52": {"class_type": "TextEncodeQwenImageEditPlus",
               "inputs": {"clip": ["11", 0], "vae": ["12", 0], "prompt": prompt, "image1": ["50", 0]}},
        "53": {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["52", 0], "reference_latents_method": "index_timestep_zero"}},
        "13": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["52", 0]}},
        "57": {"class_type": "CFGGuider",
               "inputs": {"model": ["15", 0], "positive": ["53", 0], "negative": ["13", 0], "cfg": cfg}},
        "60": {"class_type": "BasicScheduler",
               "inputs": {"model": ["15", 0], "scheduler": "simple", "steps": steps, "denoise": denoise}},
        "59": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "56": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "58": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["56", 0], "guider": ["57", 0], "sampler": ["59", 0],
                          "sigmas": ["60", 0], "latent_image": None}},
        "80": {"class_type": "VAEDecode", "inputs": {"samples": ["58", 0], "vae": ["12", 0]}},
        "90": {"class_type": "SaveImage", "inputs": {"images": ["80", 0], "filename_prefix": "K2SREF"}},
    }
    if img:
        g["40"] = {"class_type": "LoadImage", "inputs": {"image": img, "upload": "image"}}
        g["41"] = {"class_type": "ImageResizeKJv2",
                   "inputs": {"image": ["40", 0], "width": w, "height": h, "upscale_method": "lanczos",
                              "keep_proportion": "resize", "pad_color": "0, 0, 0",
                              "crop_position": "center", "divisible_by": 8, "device": "cpu"}}
        g["42"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["41", 0], "vae": ["12", 0]}}
        g["58"]["inputs"]["latent_image"] = ["42", 0]
    else:
        g["45"] = {"class_type": "EmptySD3LatentImage",
                   "inputs": {"width": w, "height": h, "batch_size": 1}}
        g["58"]["inputs"]["latent_image"] = ["45", 0]
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--t2i", action="store_true",
                    help="官方接线：纯文生图（空 latent），内容由提示词描述，参考图只做风格")
    ap.add_argument("--denoise", type=float, default=None)
    ap.add_argument("--ref", default=str(ROOT / "assets" / "references" / "loc-house.png"))
    ap.add_argument("--w", type=int, default=1376)
    ap.add_argument("--h", type=int, default=768)
    ap.add_argument("--steps", type=int, default=8)
    ap.add_argument("--cfg", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=-1)
    a = ap.parse_args()
    denoise = a.denoise if a.denoise is not None else (1.0 if a.t2i else 0.60)
    refp = Path(a.ref)
    if not refp.exists():
        print("风格参考图不存在:", refp); return
    for name in a.names:
        pf = PROMPTS / f"{name}.txt"
        if not pf.exists():
            print(f"[skip] {name}: 无 {pf}"); continue
        srcp, prompt = parse(pf)
        if not a.t2i and (not srcp or not srcp.exists()):
            print(f"[skip] {name}: 输入图不存在 {srcp}"); continue
        img = None if a.t2i else upload(srcp)
        ref = upload(refp)
        seed = random.randint(1, 2**31 - 1) if a.seed < 0 else a.seed
        print(f"[{name}] 模式={'T2I(官方)' if a.t2i else 'img2img'} "
              f"内容={'(提示词描述)' if a.t2i else srcp.name} 风格={refp.name} denoise={denoise} seed={seed}")
        g = build(img, ref, prompt, a.w, a.h, seed, a.steps, denoise, a.cfg)
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
                    print("  出错:", json.dumps(e["status"], ensure_ascii=False)[:700]); break
                imgs = []
                for o in e.get("outputs", {}).values():
                    imgs += o.get("images", [])
                if imgs:
                    f = COMFY_OUT / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                    OUT.mkdir(parents=True, exist_ok=True)
                    dst = OUT / f"{name}.png"
                    shutil.copyfile(f, dst)
                    print(f"  done {time.time()-t0:.0f}s -> {dst}")
                else:
                    print("  无输出")
                break
            if time.time() - t0 > 1800:
                print("  超时"); break


if __name__ == "__main__":
    main()
