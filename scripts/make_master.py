# -*- coding: utf-8 -*-
"""阶段 4：把 H3 分段视频拼成成片，换上母版音频，可选烧录字幕。

要点：
- H3 输出帧数按模型网格 17k+5 上取整（14s -> 345 帧 = 14.375s，13s -> 328 帧，10s -> 243 帧），
  每段实测都比 manifest 的整数秒长；直接 concat 会累积漂移、总长超过生产时长。
  所以先按 manifest 的 duration_seconds 逐段 trim，再 concat，总长正好等于生产时长。
- 各段自带模型生成的音频一律丢弃，整片改用工程根的 canonical_master.wav。
- 单趟 filter_complex，视频只编码一次。

用法（在 <project>/production 下）：
    python make_master.py
    python make_master.py --videos-dir h3_videos_cloud_0p6_8step
    python make_master.py --ass lyrics/master.ass --out ../delivery/master_lyrics.mp4

路径与 ffmpeg 都走 mvconfig，不硬编码。
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

import mvconfig

CFG = mvconfig.CFG
ROOT = CFG.project_root
PROD = ROOT / "production"
MANIFEST = PROD / "manifest.json"
MASTER_AUDIO = ROOT / "canonical_master.wav"
DEFAULT_VIDEOS = PROD / "h3_videos"
DEFAULT_OUT = ROOT / "delivery" / "master_v1_noLyrics.mp4"

FPS = 24


def find_ffmpeg(explicit=None):
    """按 显式参数 -> MV_FFMPEG -> ComfyUI 同级的 full build -> ComfyUI 自带 -> PATH 依次探测。"""
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        raise SystemExit(f"指定的 ffmpeg 不存在：{p}")
    import os
    env = os.environ.get("MV_FFMPEG")
    if env and Path(env).exists():
        return Path(env)
    base = CFG.comfy_root.parent
    for pat in ("ffmpeg*/bin/ffmpeg.exe", "python_embeded/Scripts/ffmpeg.exe"):
        hits = sorted(base.glob(pat))
        if hits:
            return hits[-1]
    hit = shutil.which("ffmpeg")
    if hit:
        return Path(hit)
    raise SystemExit("找不到 ffmpeg：请加 --ffmpeg，或设 MV_FFMPEG，或装到 ComfyUI 同级目录")


def load_tasks():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tasks = sorted(data["tasks"], key=lambda t: t["start_seconds"])
    return data, tasks


def probe_duration(ffprobe, path):
    out = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def build_cmd(ffmpeg, tasks, videos, out_path, ass=None):
    inputs = []
    for t in tasks:
        p = videos / f"{t['id']}.mp4"
        if not p.exists():
            raise SystemExit(f"缺少视频源：{p}")
        inputs += ["-i", str(p)]
    inputs += ["-i", str(MASTER_AUDIO)]
    audio_idx = len(tasks)

    parts = []
    labels = []
    for i, t in enumerate(tasks):
        d = t["duration_seconds"]
        parts.append(f"[{i}:v]trim=start=0:end={d},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(tasks)}:v=1:a=0[vcat]")

    total = sum(t["duration_seconds"] for t in tasks)

    if ass:
        # 只传文件名，配合 cwd 调用，避开 Windows 路径里的冒号/反斜杠转义与中文路径问题
        parts.append(f"[vcat]ass='{Path(ass).name}'[vout]")
        vmap = "[vout]"
    else:
        vmap = "[vcat]"

    cmd = [str(ffmpeg), "-y", "-hide_banner", *inputs,
           "-filter_complex", ";".join(parts),
           "-map", vmap, "-map", f"{audio_idx}:a",
           "-c:v", "libx264", "-crf", "16", "-preset", "medium",
           "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-t", str(total), "-movflags", "+faststart",
           str(out_path)]
    return cmd, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos-dir", default=None,
                    help="分段视频目录，默认 production/h3_videos，相对路径按 production 解析")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--ass", default=None, help="可选，烧录的 ASS 字幕")
    ap.add_argument("--ffmpeg", default=None)
    args = ap.parse_args()

    videos = Path(args.videos_dir) if args.videos_dir else DEFAULT_VIDEOS
    if not videos.is_absolute():
        videos = PROD / videos
    # 必须绝对化：烧字幕时 ffmpeg 的 cwd 会切到字幕目录，相对输出路径会写错地方
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg(args.ffmpeg)
    ffprobe = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    print(f"ffmpeg: {ffmpeg}")
    print(f"视频源: {videos}")

    data, tasks = load_tasks()
    timeline = data.get("production_timeline_seconds", sum(t["duration_seconds"] for t in tasks))
    print(f"段数={len(tasks)}  目标总长={timeline}s")
    for t in tasks:
        src = videos / f"{t['id']}.mp4"
        actual = probe_duration(ffprobe, src)
        flag = "" if abs(actual - t["duration_seconds"]) < 1e-3 else "  <- 需裁切"
        print(f"  {t['id']} 目标{t['duration_seconds']:>3}s  实测{actual:.3f}s{flag}")

    cmd, total = build_cmd(ffmpeg, tasks, videos, out_path, ass=args.ass)
    print(f"\n编码中 -> {out_path}  (目标 {total}s)")
    workdir = Path(args.ass).resolve().parent if args.ass else None
    subprocess.run(cmd, check=True, cwd=workdir)

    got = probe_duration(ffprobe, out_path)
    print(f"完成：{out_path}")
    print(f"成片时长 {got:.3f}s  (目标 {total}s, 偏差 {got - total:+.3f}s)")


if __name__ == "__main__":
    main()
