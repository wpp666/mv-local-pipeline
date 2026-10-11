# -*- coding: utf-8 -*-
"""走本地 Krea 2 双图编辑链路（图1=场景，图2=人物）出分镜图，保住 MV 的 Krea/MJ 风格。

用法：
    python run_krea2_edit.py S03 [S04 ...]
    python run_krea2_edit.py --all

提示词文件格式（production/krea2_edit_prompts/Sxx.txt）：
    图1 = <场景锚图路径>
    图2 = <人物锚图路径>
    提示词：
    <一句编辑指令>
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
PROMPTS = ROOT / "production" / "krea2_edit_prompts"
OUT = ROOT / "production" / "storyboards_krea2"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

UNET = CFG.model("krea2_unet")
IDENTITY_LORA = CFG.model("krea2_identity_lora")
# MJ 风格 LoRA 栈。注意：原先还挂了 krea2_10000，实测会与风格滤镜叠加出「武侠/佩剑」偏置，
# 导致人物凭空多出剑与头饰，故移除；现保留 MJ 品牌 LoRA，风格足够且画面干净。
MJ_LORAS = list(CFG.mj_loras)
CLIP = CFG.model("krea2_clip")
VAE = CFG.model("krea2_vae")


def parse(path):
    refs, prompt, lines = [], "", path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("图") and "=" in s:
            p = s.split("=", 1)[1].strip()
            if p:
                refs.append(Path(p))
        if s.startswith("提示词：") and i + 1 < len(lines):
            prompt = lines[i + 1].strip()
    return refs, prompt


def post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


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


NEG = ("剑, 刀, 匕首, 武器, 兵器, 佩剑, 头饰, 发簪, 珠宝, 华丽配饰, "
       "多余的手, 多余的手臂, 多余的手指, 六指, 畸形, 融合的手, 扭曲的脖子, "
       "人体比例错误, 多余人物, 现代物件")


def build(prompt, scene, person, w, h, seed, steps, mj_scale, cfg=1.0, neg=""):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": IDENTITY_LORA, "strength_model": 1.0}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "10": {"class_type": "LoadImage", "inputs": {"image": scene, "upload": "image"}},
        "20": {"class_type": "ImageScaleToTotalPixels",
               "inputs": {"image": ["10", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 8}},
        "30": {"class_type": "VAEEncode", "inputs": {"pixels": ["20", 0], "vae": ["4", 0]}},
        "40": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
    }
    # 人物图（可选）
    patch_in = {"model": ["2", 0], "source_latent": ["30", 0], "vae": ["4", 0],
                "source_image": ["20", 0], "target_latent": ["40", 0],
                "ref_boost": 4.0, "ref_boost_a": 1.0, "fit_mode": "fit"}
    enc_in = {"clip": ["3", 0], "prompt": prompt, "image": ["20", 0],
              "grounding_px": 768, "system_prompt": ""}
    neg_in = {"clip": ["3", 0], "prompt": neg, "image": ["20", 0],
              "grounding_px": 768, "system_prompt": ""}
    if person:
        g["11"] = {"class_type": "LoadImage", "inputs": {"image": person, "upload": "image"}}
        g["21"] = {"class_type": "ImageScaleToTotalPixels",
                   "inputs": {"image": ["11", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 8}}
        g["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["4", 0]}}
        patch_in["source_latent_b"] = ["31", 0]
        patch_in["source_image_b"] = ["21", 0]
        enc_in["image_b"] = ["21", 0]
        neg_in["image_b"] = ["21", 0]

    model_src = ["2", 0]
    if mj_scale > 0:
        for i, (name, st) in enumerate(MJ_LORAS):
            nid = str(200 + i)
            g[nid] = {"class_type": "LoraLoaderModelOnly",
                      "inputs": {"model": model_src, "lora_name": name, "strength_model": round(st * mj_scale, 3)}}
            model_src = [nid, 0]
    patch_in["model"] = model_src

    g["50"] = {"class_type": "Krea2EditModelPatch", "inputs": patch_in}
    g["60"] = {"class_type": "Krea2EditGroundedEncode", "inputs": enc_in}
    g["61"] = {"class_type": "Krea2EditGroundedEncode", "inputs": neg_in}
    g["70"] = {"class_type": "KSampler",
               "inputs": {"model": ["50", 0], "seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["60", 0], "negative": ["61", 0],
                          "latent_image": ["40", 0], "denoise": 1.0}}
    g["80"] = {"class_type": "VAEDecode", "inputs": {"samples": ["70", 0], "vae": ["4", 0]}}
    g["90"] = {"class_type": "SaveImage", "inputs": {"images": ["80", 0], "filename_prefix": "K2EDIT"}}
    return g


def run_one(sid, w, h, seed, steps, mj_scale, cfg=1.0, neg=""):
    pf = PROMPTS / f"{sid}.txt"
    if SKIP_EXISTING and (OUT / f"{sid}.png").exists():
        print(f"[skip] {sid}: 已有输出")
        return True
    if not pf.exists():
        print(f"[skip] {sid}: 无编辑提示词")
        return False
    refs, prompt = parse(pf)
    scene = upload(refs[0])
    person = upload(refs[1]) if len(refs) > 1 else None
    use_seed = random.randint(1, 2**31 - 1) if seed < 0 else seed
    print(f"[{sid}] scene={refs[0].name} person={refs[1].name if person else '—'} seed={use_seed} cfg={cfg}")
    g = build(prompt, scene, person, w, h, use_seed, steps, mj_scale, cfg, neg)
    r = post_json(SERVER + "/prompt", {"prompt": g, "client_id": uuid.uuid4().hex})
    pid = r.get("prompt_id")
    if not pid:
        print("  POST 失败:", json.dumps(r, ensure_ascii=False)[:600])
        return False
    print(f"  queued {pid}")
    t0 = time.time()
    fails = 0
    while True:
        time.sleep(3)
        try:
            hist = json.load(urllib.request.urlopen(f"{SERVER}/history/{pid}", timeout=20))
            fails = 0
        except Exception as e:
            fails += 1
            if fails % 10 == 1:
                print(f"  poll retry x{fails}: {type(e).__name__}")
            if time.time() - t0 > 5400:
                print("  超时(90min)"); return False
            continue
        if pid in hist:
            e = hist[pid]
            if e.get("status", {}).get("status_str") == "error":
                print("  出错:", json.dumps(e["status"], ensure_ascii=False)[:800])
                return False
            imgs = []
            for o in e.get("outputs", {}).values():
                imgs += o.get("images", [])
            if imgs:
                src = COMFY_OUT / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                OUT.mkdir(parents=True, exist_ok=True)
                dst = OUT / f"{sid}.png"
                shutil.copyfile(src, dst)
                print(f"  done {time.time()-t0:.0f}s -> {dst}")
                return True
            print("  无输出:", json.dumps(e.get("outputs", {}), ensure_ascii=False)[:400])
            return False
        if time.time() - t0 > 5400:
            print("  超时(90min)"); return False


SKIP_EXISTING = False


def main():
    global SKIP_EXISTING, PROMPTS, OUT, MJ_LORAS
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--w", type=int, default=CFG.defv("still_w"))
    ap.add_argument("--h", type=int, default=CFG.defv("still_h"))
    ap.add_argument("--steps", type=int, default=CFG.defv("edit_steps"))
    ap.add_argument("--mj-scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=-1, help="负数表示每段随机种子")
    ap.add_argument("--cfg", type=float, default=1.0, help=">1 时负向提示词才生效")
    ap.add_argument("--no-neg", action="store_true", help="不用默认负向提示词")
    ap.add_argument("--resume", action="store_true", help="跳过已有输出的段")
    ap.add_argument("--drop-loras", default="", help="逗号分隔的 LoRA 名关键词，命中的不挂")
    ap.add_argument("--prompts-dir", default=None)
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    SKIP_EXISTING = a.resume
    if a.prompts_dir:
        PROMPTS = Path(a.prompts_dir)
    if a.out_dir:
        OUT = Path(a.out_dir)
    if a.drop_loras:
        keys = [k.strip() for k in a.drop_loras.split(",") if k.strip()]
        MJ_LORAS = [(n, s) for (n, s) in MJ_LORAS if not any(k in n for k in keys)]
        print("LoRA 栈:", [n.split("\\")[-1] for n, _ in MJ_LORAS])
    neg = "" if (a.no_neg or a.cfg <= 1.0) else NEG
    ids = sorted(p.stem for p in PROMPTS.glob("*.txt")) if a.all else a.ids
    if not ids:
        print("用法: run_krea2_edit.py S03 | --all [--seed -1] [--cfg 2.0]")
        return
    ok = sum(1 for sid in ids if run_one(sid, a.w, a.h, a.seed, a.steps, a.mj_scale, a.cfg, neg))
    print(f"完成 {ok}/{len(ids)}")


if __name__ == "__main__":
    main()
