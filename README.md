# mv-local-pipeline

An agent skill for running a five-stage local music-video pipeline: **Krea 2 anchors → Qwen-Image 2.1 + Krea 2 storyboards → MiniMax H3 video → segment assembly against the master audio → bilingual lyric subtitles**, entirely on a local ComfyUI.

Everything executes on your own machine. Nothing is submitted to a hosted service.

## Stages

| Stage | What runs | Output |
| --- | --- | --- |
| 1. Anchors | Krea 2 text-to-image, plus a QuadView character sheet | `assets/references/` |
| 2. Storyboards | Qwen-Image 2.1 multi-image edit, then a Krea 2 low-denoise style pass | `production/storyboards_2pass/`, `production/storyboards_grid/` |
| 3. Video | MiniMax H3 `ref2va` with a turbo accelerator LoRA and a Sage attention patch | `production/h3_videos/` |
| 4. Assembly | Trim every segment to its integer seconds, concat, mux the master WAV over the whole cut | `delivery/master_noLyrics.mp4` |
| 5. Subtitles | Build an ASS sheet from `lyrics.json` (title + CN/EN lyric + credit) and burn it in | `production/lyrics/master.ass`, `delivery/master_lyrics.mp4` |

Stage 2 is deliberately two passes: the Qwen pass decides content, framing and head count, the Krea pass carries the look. Neither model does both well.

Stage 4 exists because H3 returns frame counts snapped up to the `17k+5` grid, so each segment file is longer than the integer duration the manifest declares. Trimming first is what keeps the cut on the master audio.

## Layout

```text
SKILL.md                          stages, hard rules, data contract, quality gates
references/environment.md         machine baseline, model and LoRA file names, constraints
references/prompts.md             four prompt families, one per generation step
references/pitfalls.md            pitfalls that actually happened, with guards
assets/pipeline_config.template.json   the config every script reads
assets/lyrics.template.json       starting point for a project's lyric sheet
scripts/mvconfig.py               config loader (env overrides, JSON, defaults)
scripts/init_project.py           scaffold a new <project>-mv/ with the runners
scripts/run_krea2_t2i.py          stage 1, anchors
scripts/run_krea2_sheet.py        stage 1, QuadView character sheet
scripts/run_qwen21_edit.py        stage 2 pass 1
scripts/run_krea2_img2img.py      stage 2 pass 2
scripts/make_storyboard_prompts.py   rebuild per-segment prompt files
scripts/make_grids.py             compose 2x2 grids for multi-frame segments
scripts/fix_manifest_refs.py      re-derive images_in_order from the prompt tags
scripts/run_h3_video.py           stage 3, video
scripts/make_master.py            stage 4, assembly (optional subtitle burn-in)
scripts/make_lyrics_ass.py        stage 5, lyrics.json -> ASS
scripts/run_krea2_edit.py         Krea 2 two-image edit (single-character shots)
scripts/run_krea2_styleref.py     abandoned route, kept for reference
```

## Assembly and subtitles

```powershell
cd <project>/production
python make_master.py --out ../delivery/master_noLyrics.mp4
python make_lyrics_ass.py --lyrics lyrics/lyrics.json
python make_master.py --ass lyrics/master.ass --out ../delivery/master_lyrics.mp4
```

All on-screen text lives in `production/lyrics/lyrics.json` — title, title translation, credit, director, year, and one entry per lyric line with `{start, end, cn, en}`. Line times are taken from master-audio facts (the bar grid, or the breath dips already recorded in the director sheet), never guessed. The script owns the layout: KaiTi for Chinese, Georgia for the smaller Latin line, title and credit in separate size tiers, everything held off faces.

`ffmpeg` is resolved by the script as `--ffmpeg` → `MV_FFMPEG` → a full build next to the ComfyUI root → `PATH`.

## Install

Copy this directory into your agent's skills folder:

```text
~/.trae-cn/skills/mv-local-pipeline/
```

## Configuration

No script hardcodes a machine path. Everything resolves through `mvconfig.py`:

```text
MV_ROOT           full project root, highest priority
MV_PROJECT        project name; root becomes projects_dir/<name>-mv
MV_PROJECTS_DIR   directory holding every project
MV_COMFY          ComfyUI root
MV_SERVER         ComfyUI base URL
```

Resolution order is environment variable → `production/pipeline_config.json` → built-in default. Model names, the MJ style LoRA stack, and default sizes all live in `pipeline_config.json`.

## Starting a new project

```powershell
python scripts/init_project.py --name <project name>
```

Creates `<projects_dir>/<name>-mv/` with the full directory skeleton, copies every runner into `production/`, and writes a config plus an empty manifest.

## Adapting to your machine

`references/environment.md` and `assets/pipeline_config.template.json` ship with the author's paths and model names as a worked example. Point them at your own ComfyUI, verify the model names against `GET /object_info` on your server, and confirm which attention/sage node your node pack actually provides.

## Running it on a cloud GPU instead

See the companion skill `cloud-comfyui-ops` for the cross-provider procedure and per-provider profiles.
