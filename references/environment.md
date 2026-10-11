# Environment baseline

Machine facts this pipeline is tuned for. Reload this file whenever ComfyUI, a model, or a LoRA changes.

## Host

| Item | Value |
| --- | --- |
| GPU | RTX 3070 Ti, 8 GB VRAM |
| CPU / RAM | i5-12400F / 32 GB |
| ComfyUI | `F:\comfyui\ComfyUI_windows_portable-G314\ComfyUI`, served at `http://127.0.0.1:8188` |
| Python | `F:\comfyui\ComfyUI_windows_portable-G314\python_embeded\python.exe` — the system `python` does not respond, never use it |
| Acceleration | `triton 3.7.1` and `sageattention` are installed |

Verify the server before a batch:

```powershell
Invoke-RestMethod http://127.0.0.1:8188/system_stats
```

Confirm the served `argv` includes the usual flags: `--preview-method auto --fast fp16_accumulation --cuda-malloc`.

## Low-VRAM constraints

- 20 GB int8 weights run only because ComfyUI offloads to system RAM. Free RAM can drop to about 3 GB during a run; do not start heavy work in parallel.
- Prefer the scripts over the editor. Loading the H3 weights inside the editor crashes on this card.
- A single 608x320 / 345-frame H3 segment takes roughly 160-180 s including load.

## Models

Paths are relative to `ComfyUI/models/`.

Krea 2 — anchors, style pass, QuadView sheet:

```text
unet   Krea2\krea2_turbo_int8_convrot.safetensors
unet   Krea2\krea2_turbo_fp8_scaled.safetensors     (QuadView sheet)
clip   qwen3vl_4b_fp8_scaled.safetensors            type = krea2
vae    qwen_image_vae.safetensors
```

Qwen-Image 2.1 — storyboard pass 1:

```text
unet   Qwen\qwen_image_2.1_int8_convrot.safetensors
clip   qwen3vl_8b_int8_convrot.safetensors
vae    qwen_image_2.1_vae_bf16.safetensors
```

MiniMax H3 — video:

```text
unet   Minimax_H3\minimax_h3_ref2va_pruned_int8_convrot.safetensors
clip   qwen3vl_32b_minimax_h3_int8_convrot.safetensors   type = minimax
vae    minimax_h3_video_vae_fp16.safetensors
vae    minimax_h3_audio_vae_fp32.safetensors
lora   minimax_h3\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors
```

## MJ style LoRA stack

Applied to every Krea 2 pass so anchors and storyboards share one look.

```text
Krea2-功能\krea2小志_xm_k20_texture.safetensors            0.60
Krea2-功能\krea2-Cc-MJ-风格滤镜.safetensors                  0.70
Krea2-功能\K2-MJ美学增强Afterlight_v1.safetensors            0.50
Krea2-功能\krea2-Cc-MJ-影视柔光.safetensors                  0.60
```

`krea2_10000` must stay out of the stack. Combined with the MJ style filter it biases output toward wuxia and invents swords and hair ornaments.

Other Krea 2 LoRAs:

```text
Krea2-功能\Krea2-四视图QuadView_krea2_v1.safetensors         sheet generation
Krea2-功能\Krea2-编辑identity_edit_v1_2.safetensors          optional, identity keep
```

Do not attach the identity LoRA during the style pass; it drifts the face.

## H3 acceleration chain

The graph in `run_h3_video.py` mirrors the local workflow `黑鹤001的例子/▶▷MiniMaxH3-加速视频流整合.json`, multi-reference section.

```text
UNETLoader(ref2va_pruned_int8)
  ├─ MiniMaxH3MemoryEfficientSageAttentionPatch      Sage acceleration, node level
  │    └─ LoraLoaderModelOnly(turbo 4step, 0.75)     acceleration LoRA
  │         └─ BasicGuider.model
  └─ BasicScheduler(simple, steps 4, denoise 1).model
```

Sage here is a KJNodes patch node, so no ComfyUI restart and no `--use-sage-attention` flag is required.

Related workflows kept for reference:

- `▶▷MiniMaxH3-加速视频流整合.json` — multi-reference video, the one used here.
- `▶▷MiniMaxH3辅助四视图生成流-k2.json` — QuadView character sheet.
- `mj风格工作流.json` — Krea 2 MJ LoRA stack reference.
- `视频工作流.json` — alternate H3 chain, `comfy kitchen attention` int8, no Sage node.

## Configuration

All machine paths live in `production/pipeline_config.json`. `mvconfig.py` resolves them in this order: environment variable, then JSON, then the built-in default.

```text
MV_ROOT            full project root, highest priority
MV_PROJECT         project name, project root becomes projects_dir/<name>-mv
MV_PROJECTS_DIR    directory holding every project
MV_COMFY           ComfyUI root
MV_SERVER          ComfyUI base URL
```
