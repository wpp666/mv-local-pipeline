# Prompt writing

Four prompt families, one per generation step. Keep each family in its own language and shape; do not blend them.

Global rules:

- Describe only what should be present. Exclusions belong in the negative prompt.
- State light direction and quality explicitly, and name the space scale (width, depth, ceiling height) when the prompt builds a room.
- One action per shot.
- No `(word:1.2)` weighting syntax and no keyword soup in Krea 2 prompts; repeat the subject at the head of the sentence instead.

## 1. Anchors — Krea 2 text-to-image

Structure is three layers: content skeleton, visual organisation, imaging layer.

1. **Content skeleton** — one subject with age, region, and temperament; the scene elements that carry them; one pose.
2. **Visual organisation** — shot size and camera height, foreground occlusion that frames without covering the subject, first and second focus.
3. **Imaging layer** — light, palette, lens, and finish.

Template:

```text
生成一幅中国古典化田园生活叙事影像，主体为 <年龄 + 地域 + 气质>，位于 <场景>，<一个动作/姿态>。
人物气质 <面部/肤质/发型/服装>。
构图采用 <景别 + 机位>，画面边缘加入 <虚化的前景元素> 建立空间包裹感而完全不遮挡人物；
第一焦点落在 <…>，第二焦点落在 <…>。
光线采用 <方向 + 性质>，暖高光落在 <…>，阴影区保留 <冷色反射>。
整体色彩以 <核心色系> 为核心，成像呈现 <清晰度/虚化/空气感/辉光> 的电影静帧气质。16:9 横幅。
```

Also write an English direct-use version from the same content, since the local Krea 2 stack takes natural-language English well.

Derived views (head close-up, back view) are image-to-image from the front full-body anchor, with the anchor as the only reference. Write only what changes; do not restate the style layer.

## 2. Storyboard pass 1 — Qwen-Image 2.1 multi-image edit

Editing-instruction phrasing. This is the pass that decides content, framing, and how many people are in frame.

- Label references as `[图1]`, `[图2]`, `[图3]`; state what each one supplies (scene anchor, character anchor, key frame).
- State the head count explicitly and forbid duplication, for example 画面中只有一位人物，各人物只出现一次、不得重复.
- List the features that must be preserved: face shape, hair, wardrobe, and the spatial relation between props.
- Ask for a 16:9 horizontal frame.
- Do not pin a seed; a fixed seed makes ComfyUI reuse a cached image.

Template:

```text
[图1] 提供 <场景> 的空间与陈设，[图2] 提供 <人物> 的外观，[图3] 为构图关键帧。
保持 <人物> 的脸型、发型、服装与 <道具> 的位置关系不变，画面中只有 <N> 位人物，各人物只出现一次、不得重复。
<一句话编辑指令：要画面发生什么>。16:9 横构图。
```

## 3. Storyboard pass 2 — Krea 2 image-to-image style pass

Single reference image, low denoise, style carried by the LoRA stack rather than by words.

- Reference: `图1 = <pass-1 output>`.
- Prompt: the scene content in a sentence plus a short style phrase. No long style essay; the LoRA stack already supplies the look.
- Fixed `denoise 0.35`, steps 10, cfg 1.0, no identity LoRA.

Prompt file shape:

```text
图1 = <path to pass-1 image>
提示词：
<画面内容一句话 + 简洁风格描述>
```

## 4. Video — MiniMax H3 six-section prompt

Fixed six sections, in this order.

```text
subject_definitions:
<Subject 1> is <…>, shown in <Picture 2>.
<Picture 1> is the single key frame for [Shot 1], showing <…>.
<Audio 1> is the exact soundtrack of this segment.

summary:
[<mode>] <one paragraph: what the target video is, which reference supplies what, and that the audio is reused.>

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - <what is kept>.
<Picture 1> ([Shot 1] key frame): fully_preserved - <what is kept>.
<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the complete soundtrack of this segment.

detailed_description:
The target video is in <style>.
[Shot 1] <camera move, timed beats with 00:0x.x marks, what changes.>

overall_soundscape: <room tone and diegetic sound only.>

non_diegetic_music: <Audio 1> is directly reused as the complete audience-only score: <description>.
```

Rules:

- `<Picture i>` / `<Video k>` / `<Audio j>` map one to one onto `images_in_order` and the segment WAV. Reference presentation order is fixed: images, then videos with their soundtrack, then standalone audio.
- Cut marks in `[Shot k]` must equal `panel_cuts_seconds` for multi-frame segments. Single-keyframe segments carry one `[Shot 1]` over the whole duration and express rhythm through continuous camera motion.
- A segment built from one key frame keeps one continuous move (slow slide, slow push, slow pan). Do not invent cuts it has no frames for.
- `<d>` lyric blocks and lip-sync lines are only for the actual singer's voice. For a male-vocal song the female character never sings and never speaks; leave her mouth out of the description entirely.
