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
| 7 | An unwanted prop such as a sword gets sharper | Naming the prop in the positive prompt reinforces it | Remove props with neutral wording and the negative prompt, never by naming them |
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

## Standing checks

- One identity source per character. Head close-ups derived, never generated fresh.
- Empty-scene anchors must contain no people.
- Pass 1 decides the people count; count the people before spending a pass 2.
- Multi-person frames go through the Qwen multi-image pass.
- After any asset change, re-run `fix_manifest_refs.py` and confirm `images_in_order` still matches the `<Picture N>` tags.
- Trim to integer seconds before concat; never concat raw H3 segments.
- After burning subtitles, sample frames at the title, a lyric line, and the credit, and look at them.
- Report file paths as clickable links and let the user judge; do not rank candidates.
