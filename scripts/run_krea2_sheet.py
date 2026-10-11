# -*- coding: utf-8 -*-
"""把一张角色锚图转成「角色设定四视图」（正面/侧面/背面全身 + 面部特写），用于补全背身、侧身镜头的参考。

配方来自本地工作流 `▶▷MiniMaxH3辅助四视图生成流-k2.json`：
Krea2 turbo fp8 + Krea2-四视图QuadView LoRA + Krea2EditModelPatch/GroundedEncode。

用法：
    python run_krea2_sheet.py char-guardian char-returnee        # 输入 assets/references/{name}.png
    python run_krea2_sheet.py char-returnee --out storyboards_krea2

输出：{out_dir}/{name}-sheet.png（1536×1024）
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
REFS = ROOT / "assets" / "references"
OUT_DEFAULT = ROOT / "production" / "storyboards_krea2"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

UNET = CFG.model("krea2_unet_fp8")
QUADVIEW_LORA = CFG.model("krea2_quadview_lora")
CLIP = CFG.model("krea2_clip")
VAE = CFG.model("krea2_vae")
SHEET_PROMPT = ("Convert the character in the image to a Character Sheet showing "
                "a face close-up, front full body, side full body and back full body views")


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


def build(img, seed, steps, w=1536, h=1024):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": QUADVIEW_LORA, "strength_model": 1.0}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "10": {"class_type": "LoadImage", "inputs": {"image": img, "upload": "image"}},
        "18": {"class_type": "ImageResizeKJv2",
               "inputs": {"image": ["10", 0], "width": 1024, "height": 1536,
                          "upscale_method": "lanczos", "keep_proportion": "resize",
                          "pad_color": "0, 0, 0", "crop_position": "center",
                          "divisible_by": 2, "device": "cpu"}},
        "20": {"class_type": "VAEEncode", "inputs": {"pixels": ["18", 0], "vae": ["4", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "23": {"class_type": "Krea2EditModelPatch",
               "inputs": {"model": ["2", 0], "source_latent": ["20", 0], "vae": ["4", 0],
                          "source_image": ["18", 0], "target_latent": ["7", 0],
                          "ref_boost": 1.0, "ref_boost_a": 1.0, "fit_mode": "fit"}},
        "24": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["3", 0], "prompt": SHEET_PROMPT, "image": ["18", 0],
                          "grounding_px": 0, "system_prompt": ""}},
        "22": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["3", 0], "prompt": "", "image": ["18", 0],
                          "grounding_px": 768, "system_prompt": ""}},
        "14": {"class_type": "KSampler",
               "inputs": {"model": ["23", 0], "seed": seed, "steps": steps, "cfg": 1.0,
                          "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["24", 0], "negative": ["22", 0],
                          "latent_image": ["7", 0], "denoise": 1.0}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["4", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": "K2SHEET"}},
    }
    return g


def run_one(name, out_dir, steps, seed):
    src = REFS / f"{name}.png"
    if not src.exists():
        print(f"[skip] {name}: 找不到 {src}")
        return False
    up = upload(src)
    s = random.randint(1, 2**31 - 1) if seed < 0 else seed
    print(f"[{name}] sheet seed={s}")
    req = urllib.request.Request(SERVER + "/prompt",
                                 data=json.dumps({"prompt": build(up, s, steps),
                                                  "client_id": uuid.uuid4().hex}).encode(),
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
                print("  出错:", json.dumps(e["status"], ensure_ascii=False)[:600]); return False
            imgs = []
            for o in e.get("outputs", {}).values():
                imgs += o.get("images", [])
            if imgs:
                f = COMFY_OUT / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                out_dir.mkdir(parents=True, exist_ok=True)
                dst = out_dir / f"{name}-sheet.png"
                shutil.copyfile(f, dst)
                print(f"  done {time.time()-t0:.0f}s -> {dst}")
                return True
            print("  无输出"); return False
        if time.time() - t0 > 1800:
            print("  超时"); return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--steps", type=int, default=CFG.defv("sheet_steps"))
    ap.add_argument("--seed", type=int, default=-1)
    a = ap.parse_args()
    ok = sum(1 for n in a.names if run_one(n, Path(a.out), a.steps, a.seed))
    print(f"完成 {ok}/{len(a.names)}")


if __name__ == "__main__":
    main()
