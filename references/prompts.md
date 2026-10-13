# Prompt writing

Four prompt families, one per generation step. Keep each family in its own language and shape; do not blend them.

Global rules:

- Describe only what should be present, and express exclusions in positive wording. Every pass runs `cfg` 1, where ComfyUI skips the negative conditioning, so a negative prompt does nothing.
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

One short placement instruction. This is the pass that decides content, framing, how many people are in frame, and their facing.

**The first reference decides the edit base and the output size.** Give `<image1>` the scene anchor, never a character. The node emits an empty latent at the *first* reference's own size, so a person as `<image1>` turns that person into the canvas: the model blows them up into a giant or drops them outright, and the frame inherits that anchor's aspect ratio.

Rules:

- Label references `<image1>`, `<image2>`, … and order them scene → character full body → character head. The scene anchor is always `<image1>`.
- Attach no prop anchors. A small-object anchor is inserted at its own close-up scale (an eraser came out the size of a lunchbox) and a size phrase in the prompt cannot shrink it. Describe small props in text with a size cue (拇指大小的半块橡皮) and an era cue where the era matters.
- Prefer placing actions within reach of the subject's stated position. A limb action that must span a distance drags the whole scale with it.
- Keep the prompt to one short instruction, roughly 40–80 characters: where to put whom, one facing, one scale reference. Do not restate the whole scene the way a text-to-image prompt would. Measured on this project, a 46-character instruction beat 106- and 153-character versions of the same frame — the extra conditions fight each other.
- Fix facing with a visible anchor in the frame (the blackboard, the door, the window) or `back to camera`; never front / back / left / right / side.
- Give position by screen side for a left/right layout (in the chair to the right of the desk), not with depth words such as behind the desk.
- Keep pose and occlusion to the minimum needed, written positively; for a seated figure a long occlusion clause drags the facing off.
- State one scale reference against the environment (head height against a chair back, prop length as a fraction of frame width) so the model cannot rescale freely.
- Never write the aspect ratio into the prompt body. 16:9 comes from the reference images' own size; keep every reference at the same 16:9 aspect.
- Express exclusions only in positive wording (see the global rules).
- Do not pin the seed in production. For a controlled A/B run on a single frame, pin `--seed 42` so both candidates are comparable.

Person-frame template:

```text
参考图（按数组顺序传入，编号即提示词里的 <imageN>；<image1> 为该帧主场景、也是被编辑图）：
  <image1> = <场景锚图>
  <image2> = <人物正面全身锚图>
  <image3> = <人物头部锚图（如有）>

提示词：
把<image2>中的人物放进<image1>的<场景>，让他坐在<屏幕方位，如「靠窗那张桌子右面」>的椅子里、面向<画面里可见的锚点，如「左边的黑板」>；其余画面保持不变。
```

Empty-scene frame: describe only what the space should show. With `cfg` 1 there is no functioning negative line, so a human-free frame is written purely from what the space contains — nothing about people at all.

```text
提示词：
保持<image1>的<空间结构/陈设>，<光落在哪、有什么物件>；其余画面保持不变。
```

The runner takes the single line below `提示词：` as the prompt. It reads no negative list: at `cfg` 1 a negative prompt has no effect.

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
