# -*- coding: utf-8 -*-
"""把 storyboard_prompts/Sxx.txt 提交到本地 ComfyUI（Qwen-Image 2.1 图像编辑）出图。

用法：
    python run_qwen21_edit.py S01 [S02 ...]      # 指定段/帧
    python run_qwen21_edit.py --all              # 全部 25 条
    python run_qwen21_edit.py S01 --steps 30 --resolution 1024

脚本做的事：读提示词文件 → 上传参考图 → 组最小 Qwen-Image-2.1 编辑图 → POST /prompt
→ 轮询 /history → 把结果图复制到 production/storyboards/{id}.png
"""
import argparse
import json
import mimetypes
import random
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

import mvconfig

CFG = mvconfig.CFG
ROOT = CFG.project_root
PROMPTS = ROOT / "production" / "storyboard_prompts"
OUT = ROOT / "production" / "storyboards"
SERVER = CFG.server

UNET = CFG.model("qwen_unet")
CLIP = CFG.model("qwen_clip")
VAE = CFG.model("qwen_vae")


def parse_prompt_file(path):
    """返回 (refs[list[Path]], prompt[str])。"""
    refs, prompt, lines = [], "", path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("图") and "=" in s and s.split("=")[0].strip().rstrip(" =").startswith("图"):
            p = s.split("=", 1)[1].strip()
            if p:
                refs.append(Path(p))
        if s.startswith("提示词：") and i + 1 < len(lines):
            prompt = lines[i + 1].strip()
    return refs, prompt


def http_post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def http_get_json(url):
    return json.load(urllib.request.urlopen(url, timeout=60))


def upload_image(path):
    """multipart 上传到 /upload/image，返回 ComfyUI 内的文件名。"""
    boundary = "----" + uuid.uuid4().hex
    name = path.name
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += path.read_bytes() + b"\r\n"
    for k, v in (("overwrite", "true"), ("type", "input")):
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        SERVER + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    res = json.load(urllib.request.urlopen(req, timeout=300))
    sub = res.get("subfolder") or ""
    return f"{sub}/{res['name']}" if sub else res["name"]


def build_graph(prompt, ref_names, steps, resolution, seed):
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
    }
    images = {}
    for i, nm in enumerate(ref_names, 1):
        nid = str(100 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": nm, "upload": "image"}}
        images[f"images.image_{i}"] = [nid, 0]
    g["6"] = {
        "class_type": "TextEncodeQwenImage21",
        "inputs": {
            "clip": ["2", 0], "vae": ["3", 0],
            "prompt": prompt, "negative_prompt": "",
            "resolution": resolution, **images,
        },
    }
    g["7"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["1", 0], "seed": seed, "steps": steps, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["6", 0], "negative": ["6", 1], "latent_image": ["6", 2], "denoise": 1.0,
        },
    }
    g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}}
    g["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "QW21"}}
    return g


def run_one(sid, steps, resolution, seed, prompts_dir=PROMPTS, out_dir=OUT):
    pf = prompts_dir / f"{sid}.txt"
    if not pf.exists():
        print(f"[skip] {sid}: 无提示词文件")
        return False
    refs, prompt = parse_prompt_file(pf)
    if not refs or not prompt:
        print(f"[skip] {sid}: 参考图或提示词缺失 (refs={len(refs)})")
        return False
    print(f"[{sid}] refs={[r.name for r in refs]} prompt={len(prompt)}字")
    names = [upload_image(r) for r in refs]
    if seed < 0:
        seed = random.randint(1, 2**31 - 1)
    print(f"  seed={seed}")
    graph = build_graph(prompt, names, steps, resolution, seed)
    client_id = uuid.uuid4().hex
    resp = http_post_json(SERVER + "/prompt", {"prompt": graph, "client_id": client_id})
    pid = resp.get("prompt_id")
    if not pid:
        print("  POST 失败:", resp)
        return False
    print(f"  queued prompt_id={pid}")
    t0 = time.time()
    while True:
        time.sleep(3)
        hist = http_get_json(f"{SERVER}/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                print("  执行出错:", json.dumps(status, ensure_ascii=False)[:600])
                return False
            outs = entry.get("outputs", {})
            imgs = []
            for node_out in outs.values():
                imgs += node_out.get("images", [])
            if imgs:
                src = CFG.comfy_output / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                out_dir.mkdir(parents=True, exist_ok=True)
                dst = out_dir / f"{sid}.png"
                shutil.copyfile(src, dst)
                print(f"  done in {time.time()-t0:.0f}s -> {dst}")
                return True
            print("  无输出图:", json.dumps(outs, ensure_ascii=False)[:400])
            return False
        if time.time() - t0 > 1800:
            print("  超时(30min)")
            return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--steps", type=int, default=CFG.defv("qwen_steps"))
    ap.add_argument("--resolution", type=int, default=CFG.defv("qwen_resolution"))
    ap.add_argument("--seed", type=int, default=-1, help="负数表示每段随机种子")
    ap.add_argument("--prompts-dir", default=str(PROMPTS))
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()

    pdir, odir = Path(a.prompts_dir), Path(a.out_dir)
    if a.all:
        ids = sorted(p.stem for p in pdir.glob("*.txt"))
    else:
        ids = a.ids
    if not ids:
        print("用法: run_qwen21_edit.py S01 [S02 ...] | --all [--prompts-dir D --out-dir D]")
        return
    ok = 0
    for sid in ids:
        if run_one(sid, a.steps, a.resolution, a.seed, pdir, odir):
            ok += 1
    print(f"完成 {ok}/{len(ids)}")


if __name__ == "__main__":
    main()
