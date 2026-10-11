# -*- coding: utf-8 -*-
"""走本地 ComfyUI 的「MiniMaxH3-加速视频流整合」工作流的「多参视频」链路出 MV 分段视频。

链路（照抄工作流 黑鹤001的例子/▶▷MiniMaxH3-加速视频流整合.json 的 MiniMaxH3ReferenceToVideo 段）：
    UNETLoader(ref2va_pruned_int8) ─┬─> SagePatch -> Lora(turbo_4step 0.75) -> BasicGuider.model
                                    └─> BasicScheduler(simple, 4, 1).model
    CLIPLoader(qwen3vl_32b int8) / VAELoader(video fp16) / VAELoader(audio fp32)
    LoadImage×N -> MiniMaxH3ReferenceToVideo.ref_images.ref_image_k
    LoadAudio   -> MiniMaxH3ReferenceToVideo.ref_audios.ref_audio_0
    MiniMaxH3ReferenceToVideo(prompt,width,height,length,ref_image_size=match) -> positive / AV LATENT
    RandomNoise + KSamplerSelect(res_multistep) + SamplerCustomAdvanced -> LATENT
    VAEDecode -> IMAGE ; VAEDecodeAudio -> AUDIO ; VHS_VideoCombine -> mp4

用法：
    python run_h3_video.py S01 [S02 ...]
    python run_h3_video.py --all
参数默认 megapixels=0.2、16:9（对齐用户要求），带加速 LoRA 与 Sage 注意力加速节点。
"""
import argparse
import json
import math
import random
import shutil
import time
import urllib.request
import uuid
from pathlib import Path

import mvconfig

CFG = mvconfig.CFG
ROOT = CFG.project_root
WH = ROOT / "production"
PROMPTS = WH / "prompts_h3"
OUT = WH / "h3_videos"
MANIFEST = WH / "manifest.json"
SERVER = CFG.server
COMFY_OUT = CFG.comfy_output

# —— 模型 / LoRA（对齐加速视频流整合工作流）——
UNET = CFG.model("h3_unet")
CLIP = CFG.model("h3_clip")
VAE_VIDEO = CFG.model("h3_vae_video")
VAE_AUDIO = CFG.model("h3_vae_audio")
TURBO_LORA = CFG.model("h3_turbo_lora")
TURBO_STRENGTH = CFG.defv("h3_turbo_strength")

STEPS = CFG.defv("h3_steps")
SCHEDULER = CFG.defv("h3_scheduler")
SAMPLER = CFG.defv("h3_sampler")
FPS = 24


def snap_length(seconds):
    """秒 -> 24fps 帧数，向上吸附到模型 17k+5 网格。"""
    n = max(5, round(seconds * FPS))
    while n % 17 != 5:
        n += 1
    return n


def dims(megapixels, ar_w, ar_h, mult=32):
    w = round(math.sqrt(megapixels * 1e6 * ar_w / ar_h) / mult) * mult
    h = round(math.sqrt(megapixels * 1e6 * ar_h / ar_w) / mult) * mult
    return max(mult, w), max(mult, h)


def post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def upload(path):
    """上传图片到 input/。"""
    b = "----" + uuid.uuid4().hex
    body = f"--{b}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n" + path.read_bytes() + b"\r\n"
    for k, v in (("overwrite", "true"), ("type", "input")):
        body += f"--{b}\r\n".encode() + f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(SERVER + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    r = json.load(urllib.request.urlopen(req, timeout=600))
    sub = r.get("subfolder") or ""
    return f"{sub}/{r['name']}" if sub else r["name"]


def upload_audio(path):
    """上传音频到 input/（ComfyUI 统一走 /upload/image，字段名固定为 image）。"""
    b = "----" + uuid.uuid4().hex
    body = f"--{b}\r\n".encode()
    body += f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n" + path.read_bytes() + b"\r\n"
    for k, v in (("overwrite", "true"), ("type", "input")):
        body += f"--{b}\r\n".encode() + f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(SERVER + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    r = json.load(urllib.request.urlopen(req, timeout=600))
    sub = r.get("subfolder") or ""
    return f"{sub}/{r['name']}" if sub else r["name"]


def build(prompt, images, audio, w, h, length, seed, prefix):
    g = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "MiniMaxH3MemoryEfficientSageAttentionPatch",
              "inputs": {"model": ["1", 0]}},
        "3": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0], "lora_name": TURBO_LORA, "strength_model": TURBO_STRENGTH}},
        "4": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
        "50": {"class_type": "MiniMaxH3ReferenceToVideo",
               "inputs": {"clip": ["4", 0], "vae": ["5", 0], "audio_vae": ["6", 0],
                          "prompt": prompt, "width": w, "height": h, "length": length,
                          "ref_image_size": "match"}},
        "10": {"class_type": "BasicScheduler",
               "inputs": {"model": ["1", 0], "scheduler": SCHEDULER, "steps": STEPS, "denoise": 1.0}},
        "11": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": SAMPLER}},
        "12": {"class_type": "BasicGuider",
               "inputs": {"model": ["3", 0], "conditioning": ["50", 0]}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["13", 0], "guider": ["12", 0], "sampler": ["11", 0],
                          "sigmas": ["10", 0], "latent_image": ["50", 1]}},
        "60": {"class_type": "VAEDecode",
               "inputs": {"samples": ["14", 0], "vae": ["5", 0]}},
        "61": {"class_type": "VAEDecodeAudio",
               "inputs": {"samples": ["14", 0], "vae": ["6", 0]}},
        "70": {"class_type": "VHS_VideoCombine",
               "inputs": {"images": ["60", 0], "audio": ["61", 0], "frame_rate": FPS,
                          "loop_count": 0, "filename_prefix": prefix, "format": "video/h264-mp4",
                          "pix_fmt": "yuv420p", "crf": 19, "save_metadata": True,
                          "trim_to_audio": False, "pingpong": False, "save_output": True}},
    }
    for i, name in enumerate(images):
        nid = str(100 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name, "upload": "image"}}
        g["50"]["inputs"][f"ref_images.ref_image_{i}"] = [nid, 0]
    if audio:
        g["110"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}}
        g["50"]["inputs"]["ref_audios.ref_audio_0"] = ["110", 0]
    return g


def load_task(sid):
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for t in m["tasks"]:
        if t["id"] == sid:
            return t
    return None


def run_one(sid, megapixels, ar_w, ar_h, seed, dry=False):
    t = load_task(sid)
    if t is None:
        print(f"[skip] {sid}: manifest 无此段")
        return False
    if SKIP_EXISTING and (OUT / f"{sid}.mp4").exists():
        print(f"[skip] {sid}: 已有输出")
        return True
    pf = PROMPTS / f"{sid}.txt"
    if not pf.exists():
        print(f"[skip] {sid}: 无提示词 {pf}")
        return False
    prompt = pf.read_text(encoding="utf-8").strip()

    imgs = [ROOT / p for p in t["images_in_order"]]
    missing = [str(p) for p in imgs if not p.exists()]
    if missing:
        print(f"[skip] {sid}: 缺图 {missing}")
        return False
    au = ROOT / t["audio"] if t.get("audio") else None

    w, h = dims(megapixels, ar_w, ar_h)
    length = snap_length(t["duration_seconds"])
    use_seed = random.randint(1, 2**31 - 1) if seed < 0 else seed
    print(f"[{sid}] {w}x{h} length={length}({length/FPS:.2f}s) dur={t['duration_seconds']}s "
          f"imgs={len(imgs)} audio={au.name if au else '-'} seed={use_seed}")

    if dry:
        print("  dry-run：图序 ->", [p.name for p in imgs])
        return True

    up_imgs = [upload(p) for p in imgs]
    up_audio = upload_audio(au) if au and au.exists() else None
    if up_audio:
        print(f"  audio-> {up_audio}")
    g = build(prompt, up_imgs, up_audio, w, h, length, use_seed, f"h3/onlylantern_{sid}")
    r = post_json(SERVER + "/prompt", {"prompt": g, "client_id": uuid.uuid4().hex})
    pid = r.get("prompt_id")
    if not pid:
        print("  POST 失败:", json.dumps(r, ensure_ascii=False)[:1200])
        return False
    print(f"  queued {pid}")
    t0 = time.time()
    fails = 0
    while True:
        time.sleep(5)
        try:
            hist = json.load(urllib.request.urlopen(f"{SERVER}/history/{pid}", timeout=30))
            fails = 0
        except Exception as e:
            fails += 1
            if fails % 10 == 1:
                print(f"  poll retry x{fails}: {type(e).__name__}")
            if time.time() - t0 > 10800:
                print("  超时(3h)"); return False
            continue
        if pid in hist:
            e = hist[pid]
            st = e.get("status", {})
            if st.get("status_str") == "error":
                print("  出错:", json.dumps(st, ensure_ascii=False)[:1500])
                return False
            vids = []
            for o in e.get("outputs", {}).values():
                for key in ("gifs", "videos", "images"):
                    for it in o.get(key, []):
                        if str(it.get("filename", "")).endswith(".mp4"):
                            vids.append(it)
            if vids:
                v = vids[0]
                src = COMFY_OUT / v.get("subfolder", "") / v["filename"]
                OUT.mkdir(parents=True, exist_ok=True)
                dst = OUT / f"{sid}.mp4"
                shutil.copyfile(src, dst)
                print(f"  done {time.time()-t0:.0f}s -> {dst}")
                return True
            print("  无视频输出:", json.dumps(e.get("outputs", {}), ensure_ascii=False)[:600])
            return False
        if time.time() - t0 > 10800:
            print("  超时(3h)"); return False


SKIP_EXISTING = False


def main():
    global SKIP_EXISTING, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--megapixels", type=float, default=CFG.defv("h3_megapixels"))
    ap.add_argument("--aspect", default=CFG.defv("h3_aspect"))
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args()
    SKIP_EXISTING = a.resume
    if a.out_dir:
        OUT = Path(a.out_dir)
    aw, ah = (float(x) for x in a.aspect.split(":"))
    if a.all:
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ids = [t["id"] for t in m["tasks"]]
    else:
        ids = a.ids
    if not ids:
        print("用法: run_h3_video.py S01 [S02 ...] | --all [--megapixels 0.2] [--aspect 16:9] [--resume]")
        return
    ok = sum(1 for sid in ids if run_one(sid, a.megapixels, aw, ah, a.seed, a.dry))
    print(f"完成 {ok}/{len(ids)}")


if __name__ == "__main__":
    main()
