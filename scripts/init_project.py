# -*- coding: utf-8 -*-
"""新建一个 MV 工程：建目录骨架、复制流水线脚本、写入配置与空 manifest。

用法：
    python init_project.py --name 归人
    python init_project.py --name 试片 --dir d:/mv --force

工程根 = <projects_dir>/<name>-mv。projects_dir 取值顺序：--dir > MV_PROJECTS_DIR > 模板 json。
已存在的工程根默认拒绝覆盖，需显式 --force。
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = SKILL_DIR / "scripts"
TEMPLATE = SKILL_DIR / "assets" / "pipeline_config.template.json"

SUBDIRS = [
    "assets/references",
    "production/anchor_prompts",
    "production/storyboard_prompts",
    "production/krea2_edit_prompts",
    "production/prompts_h3",
    "production/audio_segments",
    "production/storyboards",
    "production/storyboards_2pass",
    "production/storyboards_grid",
    "production/h3_videos",
    "production/lyrics",
    "delivery",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="项目名，工程根 = <name>-mv")
    ap.add_argument("--dir", default=None, help="项目存放目录，默认取 MV_PROJECTS_DIR 或模板值")
    ap.add_argument("--force", action="store_true", help="工程根已存在时覆盖")
    a = ap.parse_args()

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    projects_dir = Path(a.dir or os.environ.get("MV_PROJECTS_DIR") or template["projects_dir"])
    root = projects_dir / f"{a.name}-mv"

    if root.exists() and not a.force:
        sys.exit(f"已存在：{root}\n如需覆盖请加 --force")
    root.mkdir(parents=True, exist_ok=True)

    for rel in SUBDIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)

    prod = root / "production"
    copied = 0
    for src in sorted(SCRIPT_DIR.glob("*.py")):
        if src.name == Path(__file__).name:
            continue
        shutil.copyfile(src, prod / src.name)
        copied += 1

    cfg = dict(template)
    cfg["project_name"] = a.name
    cfg["projects_dir"] = str(projects_dir)
    (prod / "pipeline_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "project": a.name,
        "revision": "r01",
        "aspect_ratio": "16:9",
        "resolution_label": "720P",
        "megapixels": 0.2,
        "tasks": [],
    }
    (prod / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lyric_tpl = SKILL_DIR / "assets" / "lyrics.template.json"
    shutil.copyfile(lyric_tpl, prod / "lyrics" / "lyrics.json")

    print(f"工程根：{root}")
    print(f"已复制脚本 {copied} 个 -> {prod}")
    print("下一步：")
    print(f"  cd {prod}")
    print("  1) 往 anchor_prompts/ 写锚图提示词，再 run_krea2_t2i.py <name>")
    print("  2) 写 manifest.json 的 tasks（id/duration_seconds/images_in_order/audio/prompt）")
    print("  3) 分镜两遍：run_qwen21_edit.py --all → run_krea2_img2img.py --denoise 0.35 <ids>")
    print("  4) 出视频：run_h3_video.py <ids> --megapixels 0.2 --aspect 16:9 --resume")
    print("  5) 拼成片：make_master.py --out ../delivery/master_noLyrics.mp4")
    print("  6) 字幕：改 lyrics/lyrics.json → make_lyrics_ass.py → make_master.py --ass lyrics/master.ass")


if __name__ == "__main__":
    main()
