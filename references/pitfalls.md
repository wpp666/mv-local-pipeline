# Pitfalls and guards

Every entry below actually happened on this project. Check them before accepting output.

| # | Symptom | Root cause | Guard |
| --- | --- | --- | --- |
| 1 | Swords and hair ornaments appear from nowhere, output turns wuxia | `krea2_10000` stacked with the MJ style filter | Keep `krea2_10000` out of the LoRA stack; use only the four MJ LoRAs |
| 2 | Three or four hands, a twisted neck, wrong proportions | A back or side shot referenced with a front-view anchor | Use a back-view reference; generate the QuadView sheet first and split it into single views |
| 3 | Full body and close-up have different faces | Head close-up generated independently | Derive every head close-up from the front full-body anchor |
| 4 | An extra person appears in frame | Pass-1 prompt never fixed the head count | State the head count and add the no-duplicate clause, with `[图N]` labels and a keep list |
| 5 | Two separate runs return the same image | A fixed seed made ComfyUI reuse the cache | Leave seeds random across segments |
| 6 | Subject is redrawn and the style never lands | Krea 2 official Style Reference LoRA wired into image-to-image, which injects the style reference on top of the source latent | Route abandoned; use pass 1 plus a low-denoise pass 2 instead |
| 7 | An unwanted prop such as a sword gets sharper | Naming the prop in the positive prompt reinforces it | Remove props with neutral wording, never by naming them; a negative prompt does nothing at `cfg` 1 |
| 8 | A scene does not match its segment, a field segment has no field | Missing scene anchor | Add the scene anchor and reference it from that segment |
| 9 | Audio upload fails with HTTP 400 or 405 | Wrong endpoint and form field | Upload audio through `POST /upload/image` with the field name `image`, same as images |
| 10 | A batch stops partway with a ComfyUI connection error | Poll timeout with no retry | Keep the poll retry loop and `--resume`, which skips finished segments |
| 11 | A third reference cannot be attached to Krea 2 | The Krea 2 edit node has only two reference slots | For two people in one frame use the Qwen multi-image pass, not Krea 2 |
| 12 | Tried to lift one view out of a QuadView sheet | QuadView only goes single image to multi view, it is not reversible | Split the sheet into separate files by hand |
| 13 | The editor crashes while loading big weights | 8 GB card | Generate through the scripts; never load the H3 weights in the editor |
| 14 | Anchor rooms come out narrow and fake | No space scale in the prompt | State width, depth, and ceiling height |
| 15 | The finished cut runs long and every boundary drifts | H3 snaps frames up to the `17k+5` grid, so each segment file is longer than its integer `duration_seconds` | Trim every segment to `duration_seconds` before concatenating; never concat the raw files |
| 16 | Picture and music drift apart a few segments in | Concatenating raw segments drags their own model-generated audio along | Drop segment audio entirely and mux the master WAV over the whole cut |
| 17 | The `ass` filter errors out, or the subtitle silently never burns | A Windows drive colon, backslashes, and a non-ASCII folder all passed inside the filter string | Pass only the bare file name and run ffmpeg with `cwd` set to the subtitle folder |
| 18 | Subtitles render as empty boxes | libass cannot find a CJK family by that name | Use an installed family name such as `KaiTi`, then sample a frame to confirm |
| 19 | Chinese and English lines collide or drift apart | Both languages placed as two lines inside one event | Two events with the same in/out and separate `MarginV` |
| 20 | The title or credit lands on a face | Positioned by habit without looking at the frame | Sample that frame first, then choose the top or the bottom band |
| 21 | A character fills the frame as a giant, or vanishes and only the furniture is left | `<image1>` was a character anchor on a neutral background, so the edit model treated that person as the canvas | Put the scene anchor in `<image1>` and order the rest scene → character → prop |
| 22 | Character and environment are out of scale, props too big or too small | The pass-1 prompt restated the whole scene like a text-to-image prompt, so the model rebuilt scale freely | Write a short placement instruction with one explicit scale reference: head height against a chair back, prop length as a fraction of frame width |
| 23 | The frame comes back vertical, or visibly off the project aspect | References mixed aspect ratios and the output latent takes the first reference's own size | Keep every reference at one aspect (16:9) and put the scene anchor first |
| 24 | Exclusion words in the negative prompt do nothing | Every pass runs `cfg` 1, and at `cfg` 1 ComfyUI skips the negative conditioning (`uncond_ = None`); the official Qwen-Image-2.1 templates keep `cfg` 1, and the hosted `qwen-image-2.1-pro` is documented as not supporting `negative_prompt` at all | Express every exclusion in positive wording; do not rely on a negative prompt |
| 25 | Pose, facing, and scale come out wrong; the more conditions the prompt stacks the worse it gets | The pass-1 prompt restated the whole scene like a text-to-image prompt, so the model rebuilt pose and scale freely and the conditions fought each other | Write one short placement instruction. Measured on this project on the same key frame: a 46-character base beat a 106-character v1 and a 153-character v2 |
| 26 | A person faces away when they should face the room, or the neck looks twisted | Facing was written as front / back / left / right / side, which a still-image model reads ambiguously | Anchor facing to a thing that is visible in the frame: facing the blackboard on the left, facing the window on the right, facing the classroom door, back to camera |
| 27 | A person lands behind the desk, on the wrong side, or as a giant | A left/right layout was described with depth words such as behind the desk | For a left/right layout place by screen side: in the chair to the right of the desk. Keep the queryable anchors (blackboard, door, window) for facing and the screen side for position |
| 28 | Two identical runs for an A/B comparison, or the cache serves a stale image | The seed was pinned during a production run, or left random during a controlled comparison | Pin the seed to 42 only for controlled debug / A/B runs on one frame; leave the seed random per segment in production |
| 29 | A second copy of the same character shows up in one frame, though the prompt names only one person | Observed on one run, and treated as a seed artifact; the same frame then came out clean on seeds 42 / 123 / 456 / 789 and duplicated the subject again once production used random seeds | One clean seed is no evidence at all. Sample 2–3 seeds per frame; if a defect survives across seeds the prompt is at fault. Do not add a person-count clause, it did not help |
| 30 | The subject stands behind the lectern yet stretches to the blackboard, the figure is far too large, and extra arms appear | The prompt demanded an action spanning a distance (one hand wiping the blackboard while standing in front of it), so the model grew the person until the hand could reach and grew an extra limb | Write placement and facing only; drop actions that must span a distance. A limb action reaching a far object drags the scale along with it |
| 31 | Only a single disembodied hand floats in the frame, no person anywhere | The prompt asked the edit model to take the hand out of a full-body character anchor and place just that hand on a desk (hand close-up wanted), which is not something a multi-image edit does — it places whole subjects, not body parts | Never ask pass 1 for a limb-only or part-only shot. Put the whole person in the scene with a normal framing. A real hand close-up belongs to pass 2 or to a crop |
| 32 | A small prop comes out enormous, an eraser the size of a lunchbox | A small-object anchor was attached, and the multi-image edit inserts it at its own close-up scale. A size phrase in the prompt cannot shrink it: on one frame, anchor + 拇指大小 still came out oversized on every seed, while the same prompt without the anchor came out correct | Attach no prop anchors. Describe small props in text with a size cue (拇指大小的半块橡皮) and, where the era matters, an era cue (八十年代样式的旧课本) |
| 33 | Every lyric line lands a few seconds off the music, and the whole track shifts by the same amount | The title was counted as the first item in the timed lyric list, so its slot offset the entire lyric track | Keep the title out of the lyric list: give it its own `title_in` / `title_out` slot and time lyric lines independently from the master-audio grid, then check against the audio, not against list order |

## Standing checks

- One identity source per character. Head close-ups derived, never generated fresh.
- Empty-scene anchors must contain no people.
- Every pass-1 reference file shares one aspect ratio (16:9), and `<image1>` is always that frame's scene anchor.
- Pass-1 prompts are one short placement instruction: where to put whom, one facing, one scale reference. No whole-scene restatement.
- Facing is anchored to a visible object (blackboard, door, window) or `back to camera`; position is given as a screen side (left / right).
- Never write the aspect ratio into the prompt body; 16:9 comes from the reference images' own size.
- Do not pin a seed in production; pin `--seed 42` only for controlled A/B runs on a single frame.
- If a frame duplicates a subject, sample 2–3 seeds before editing the prompt; a defect that survives across seeds is a prompt defect. A clean seed is not evidence that the prompt is fine.
- Small props are text-only, with a size cue and an era cue; pass 1 attaches no prop anchors.
- Every pass runs `cfg` 1, so a negative prompt has no effect: write exclusions in the positive wording.
- Pass 1 decides the people count; count the people before spending a pass 2.
- Multi-person frames go through the Qwen multi-image pass.
- After any asset change, re-run `fix_manifest_refs.py` and confirm `images_in_order` still matches the `<Picture N>` tags.
- Trim to integer seconds before concat; never concat raw H3 segments.
- After burning subtitles, sample frames at the title, a lyric line, and the credit, and look at them.
- The title is not a lyric line: it owns its own `title_in` / `title_out` and must never shift the lyric timebase.
- Report file paths as clickable links and let the user judge; do not rank candidates.
