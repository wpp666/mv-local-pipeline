---
name: mv-local-pipeline
description: Run the local five-stage MV pipeline here, from Krea 2 anchors through Qwen 2.1 plus Krea 2 storyboards to MiniMax H3 video, then stitch the segments against the master audio and burn in the bilingual lyric sheet. Use when generating or resuming local MV anchor, storyboard, video, assembly, or subtitle work. Do not use for cloud submission.
---

# Local MV Pipeline

Run the MV production flow tuned for this machine: anchors from Krea 2, storyboards from a Qwen-Image 2.1 multi-image edit pass followed by a Krea 2 style pass, video from MiniMax H3 with the turbo LoRA and the Sage attention patch, then assembly of the segments against the master audio and burn-in of the lyric sheet. Everything executes on the local ComfyUI; nothing is submitted to a hosted service.

Before the first run in a session read [references/environment.md](references/environment.md) (ComfyUI path, launch flags, model and LoRA file names, low-VRAM constraints). Before writing any prompt read [references/prompts.md](references/prompts.md). Before accepting a generated image or video read [references/pitfalls.md](references/pitfalls.md).

To run this same pipeline on a rented GPU cloud box instead of this machine, use the `cloud-comfyui-ops` skill: it holds the cross-provider deployment procedure and the per-provider profiles.

## Hard rules

- Local ComfyUI only. Do not route any stage to RunningHub or another hosted API.
- Scripts read `<project>/production/pipeline_config.json` through `mvconfig.py`. Never hardcode a path, model name, or default size back into a script; change the config or set `MV_ROOT`, `MV_COMFY`, `MV_SERVER`.
- Lyric text and timings live only in `production/lyrics/lyrics.json`. Never hardcode a lyric line, a title, or a credit into a script.
- Burn subtitles with the full-build `ffmpeg` found next to the ComfyUI root; route the `ass` filter through the script's cwd plus a bare file name so Windows colons, backslashes, and non-ASCII paths cannot break the filter string.
- Report generated files as clickable `computer://` links and let the user judge quality. Never declare which candidate is better.
- Describe only what should appear. Put exclusions in the negative prompt, not in the positive text.
- Run generation through the scripts, not the ComfyUI editor. Loading the 20 GB H3 weights inside the editor crashes an 8 GB card.

## Project layout

```text
<projects_dir>/<project_name>-mv/
├─ canonical_master.wav
├─ assets/references/            anchors: characters, locations, props
├─ delivery/                     finished cuts
└─ production/
   ├─ pipeline_config.json       the only place with machine paths
   ├─ manifest.json              segment schedule, reference order, audio, prompt path
   ├─ anchor_prompts/            anchor prompt per file, one 提示词 line
   ├─ storyboard_prompts/        stage-2 pass-1 prompts
   ├─ krea2_edit_prompts/        stage-2 pass-2 prompts
   ├─ prompts_h3/                stage-3 six-section prompts
   ├─ audio_segments/            segment WAV, one per segment
   ├─ storyboards/               pass-1 output
   ├─ storyboards_2pass/         pass-2 output, the H3 key frame for single-shot segments
   ├─ storyboards_grid/          2x2 grid, the H3 key frame for multi-frame segments
   ├─ h3_videos/                 final segment MP4
   └─ lyrics/                    lyrics.json plus the generated master.ass
```

Create the skeleton with [scripts/init_project.py](scripts/init_project.py):

```powershell
python <skill-dir>/scripts/init_project.py --name <项目名>
```

It writes `<projects_dir>/<name>-mv/`, copies every runner into `production/`, and writes the config.

## Data contract

`production/manifest.json` drives stage 3. Read it, never re-derive it by hand.

- `tasks[].id`, `title`, `duration_seconds` — integer seconds, the H3 duration source.
- `tasks[].images_in_order` — the exact `<Picture N>` order; `<Picture 1>` is always the segment key frame.
- `tasks[].audio` — the segment WAV that becomes `<Audio 1>`.
- `tasks[].prompt` — the H3 prompt file.
- `tasks[].shot_mode` — `single_keyframe_camera` or `four_panel_multiframe`.
- `tasks[].panel_cuts_seconds` — cut times for multi-frame segments, already mirrored into `[Shot k]`.

After touching any asset run `fix_manifest_refs.py` to re-derive `images_in_order` from the `<Picture N>` tags and confirm nothing is missing.

`production/lyrics/lyrics.json` drives stage 5 and is the only source of on-screen text. Start from `assets/lyrics.template.json`.

- `title` / `title_en` / `credit` / `director` / `year` — any empty field drops that line.
- `timing` — in / out seconds per block; `credit_in` / `credit_out` default off the last line.
- `lines[]` — `{start, end, cn, en}`; `en` may be empty.
- Line times must come from master-audio facts: the bar grid `bar_seconds = 4 * 60 / bpm`, or breath dips already recorded in the director sheet. Never eyeball them.

## Stage 1 — anchors

```powershell
cd <project>/production
python run_krea2_t2i.py char-guardian
python run_krea2_t2i.py loc-house
python run_krea2_sheet.py char-guardian char-returnee   # QuadView sheet, then split by hand
```

One identity source per character. Derive a head close-up from the front full-body anchor; never generate it independently. For back-facing shots use a separate back-view reference cut out of the sheet.

## Stage 2 — storyboards, two passes

Pass 1 gives correct content; pass 2 gives the Krea and MJ look. Qwen-Image 2.1 cannot inherit that look, so both passes are required.

```powershell
python make_storyboard_prompts.py            # rebuild per-segment prompt files
python run_qwen21_edit.py --all              # pass 1, multi-image edit
python run_krea2_img2img.py --denoise 0.35 <ids>   # pass 2, style
python make_grids.py                         # 2x2 grid for multi-frame segments
```

Pass 1 prompts must use `[图N]` labels, state the people count explicitly with a no-duplicate clause, list the features to keep, and ask for a 16:9 frame. Never pin a seed across segments.

`make_grids.py` holds the multi-frame segment list for the current project; edit that list in the project copy, not in the skill copy.

## Stage 3 — video

```powershell
python run_h3_video.py S01 S02 --megapixels 0.2 --aspect 16:9 --resume
```

The graph is built in the script: UNET `ref2va_pruned_int8` into `MiniMaxH3MemoryEfficientSageAttentionPatch` into the turbo LoRA into `BasicGuider`, `MiniMaxH3ReferenceToVideo` fed by `LoadImage` and `LoadAudio`, `SamplerCustomAdvanced` with `res_multistep`, then `VAEDecode` plus `VAEDecodeAudio` into `VHS_VideoCombine`.

- Frame count must land on the model grid `17k+5` at 24 fps; `snap_length()` does this from `duration_seconds`.
- 0.2 megapixels at 16:9 resolves to 608x320.
- `--resume` skips segments that already have output.

## Stage 4 — assembly

```powershell
cd <project>/production
python make_master.py --videos-dir h3_videos_cloud_0p6_8step --out ../delivery/master_v1_noLyrics.mp4
```

Every segment comes back longer than its integer `duration_seconds`, because the frame count snaps up to the `17k+5` grid (14s -> 345 frames = 14.375s, 13s -> 328, 10s -> 243). So the segments are trimmed to `duration_seconds` first and only then concatenated; concatenating the raw files accumulates drift and overshoots the production timeline.

- Segment audio is discarded wholesale: the cut uses the project-root `canonical_master.wav` as its only track.
- One `filter_complex` pass, so the video is encoded exactly once: H.264 / yuv420p / 24 fps / AAC 48 kHz stereo.
- Output length is pinned to `production_timeline_seconds` with `-t`, which also drops the master's discarded tail.
- Run it twice: once without subtitles to check picture and sync, then again with `--ass` once the subtitle file exists.
- `ffmpeg` resolves in this order: `--ffmpeg`, `MV_FFMPEG`, a full build next to the ComfyUI root, then `PATH`.

## Stage 5 — subtitles

```powershell
python make_lyrics_ass.py --lyrics lyrics/lyrics.json        # -> lyrics/master.ass
python make_master.py --ass lyrics/master.ass --out ../delivery/master_lyrics.mp4
```

The script owns the layout; `lyrics.json` owns every piece of text.

- Title block rides the instrumental intro, so the cut length never changes. Pull it out before the first vocal bar.
- Chinese lyric in KaiTi on top, a smaller Georgia line underneath; the two are separate events so line spacing stays fixed.
- On-screen text is a spatial layer, not a subtitle bar: keep it off faces and off the main expression, and hold the whole layer in the lower band.
- Opening title, closing credit, and lyric use three distinct size tiers.
- Always sample a few frames at title, lyric, and credit moments and look at them before reporting the file.

## Quality gates

Stop and fix before moving on.

1. Anchors: exactly one identity source per character; head close-ups derived; empty-scene anchors contain no people.
2. Storyboards: correct people count, no duplicated figure, no extra hands or fingers, no twisted neck, no leftover prop such as a sword, style consistent with the anchors.
3. Manifest: `images_in_order` matches the `<Picture N>` tags one to one, nothing missing.
4. Video: frame count on the `17k+5` grid, `<Audio 1>` matches the segment WAV, `[Shot k]` times match `panel_cuts_seconds`.
5. Assembly: finished length equals `production_timeline_seconds`, the only audio track is the master WAV, and each segment change lands on a manifest segment boundary.
6. Subtitles: every line time sits on a bar boundary or a recorded breath dip; no line covers a face; title, lyric, and credit stay in three size tiers.
