# -*- coding: utf-8 -*-
"""本地 MV 流水线的统一配置：路径 / 服务 / 模型 / LoRA / 出图参数。

取值优先级（高 -> 低）：
    环境变量 MV_ROOT / MV_COMFY / MV_SERVER  ->  pipeline_config.json  ->  内置默认值

脚本里这样用：
    import mvconfig
    CFG = mvconfig.CFG
    CFG.project_root        # Path，工程根
    CFG.comfy_root          # Path，ComfyUI 根目录
    CFG.comfy_input         # Path，ComfyUI input
    CFG.comfy_output        # Path，ComfyUI output
    CFG.server              # str，ComfyUI 地址
    CFG.model("h3_unet")    # 模型文件名
    CFG.mj_loras            # [(LoRA 名, 强度), ...]
    CFG.defv("krea2_steps") # 默认出图参数

换工程 / 换机器：工程根 = projects_dir / (project_name + "-mv")，改 pipeline_config.json 的
project_name / projects_dir 即可，或用环境变量 MV_PROJECT / MV_PROJECTS_DIR / MV_ROOT 覆盖。
配置文件不存在时会按默认值自动生成。
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("MV_CONFIG") or (HERE / "pipeline_config.json"))

_DEFAULTS = {
    "project_name": "归人",
    "projects_dir": "f:\\",
    "comfy_root": r"F:\comfyui\ComfyUI_windows_portable-G314\ComfyUI",
    "server": "http://127.0.0.1:8188",
    "models": {
        "krea2_unet": r"Krea2\krea2_turbo_int8_convrot.safetensors",
        "krea2_unet_fp8": r"Krea2\krea2_turbo_fp8_scaled.safetensors",
        "krea2_clip": "qwen3vl_4b_fp8_scaled.safetensors",
        "krea2_vae": "qwen_image_vae.safetensors",
        "krea2_identity_lora": r"Krea2-功能\Krea2-编辑identity_edit_v1_2.safetensors",
        "krea2_quadview_lora": r"Krea2-功能\Krea2-四视图QuadView_krea2_v1.safetensors",
        "krea2_style_lora": "krea2_style_reference.safetensors",
        "qwen_unet": r"Qwen\qwen_image_2.1_int8_convrot.safetensors",
        "qwen_clip": "qwen3vl_8b_int8_convrot.safetensors",
        "qwen_vae": "qwen_image_2.1_vae_bf16.safetensors",
        "h3_unet": r"Minimax_H3\minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "h3_clip": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
        "h3_vae_video": "minimax_h3_video_vae_fp16.safetensors",
        "h3_vae_audio": "minimax_h3_audio_vae_fp32.safetensors",
        "h3_turbo_lora": r"minimax_h3\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
    },
    "mj_loras": [
        [r"Krea2-功能\krea2小志_xm_k20_texture.safetensors", 0.6],
        [r"Krea2-功能\krea2-Cc-MJ-风格滤镜.safetensors", 0.7],
        [r"Krea2-功能\K2-MJ美学增强Afterlight_v1.safetensors", 0.5],
        [r"Krea2-功能\krea2-Cc-MJ-影视柔光.safetensors", 0.6],
    ],
    "defaults": {
        "still_w": 1376,
        "still_h": 768,
        "krea2_steps": 10,
        "krea2_cfg": 1.0,
        "edit_steps": 10,
        "img2img_denoise": 0.35,
        "sheet_steps": 10,
        "qwen_steps": 30,
        "qwen_resolution": 1024,
        "h3_megapixels": 0.2,
        "h3_aspect": "16:9",
        "h3_steps": 4,
        "h3_scheduler": "simple",
        "h3_sampler": "res_multistep",
        "h3_turbo_strength": 0.75,
    },
}


class Config:
    def __init__(self, data):
        self._data = data
        self.project_name = os.environ.get("MV_PROJECT") or data["project_name"]
        projects_dir = Path(os.environ.get("MV_PROJECTS_DIR") or data["projects_dir"])
        self.project_root = Path(os.environ.get("MV_ROOT") or (projects_dir / f"{self.project_name}-mv"))
        self.comfy_root = Path(os.environ.get("MV_COMFY") or data["comfy_root"])
        self.server = os.environ.get("MV_SERVER") or data["server"]

    @property
    def comfy_input(self):
        return self.comfy_root / "input"

    @property
    def comfy_output(self):
        return self.comfy_root / "output"

    def model(self, key):
        return self._data["models"][key]

    @property
    def mj_loras(self):
        return [(name, float(strength)) for name, strength in self._data["mj_loras"]]

    def defv(self, key):
        return self._data["defaults"][key]


def _load():
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        raw = {}
        try:
            CONFIG_PATH.write_text(json.dumps(_DEFAULTS, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        except OSError:
            pass
    merged = {**_DEFAULTS, **raw}
    merged["models"] = {**_DEFAULTS["models"], **raw.get("models", {})}
    merged["defaults"] = {**_DEFAULTS["defaults"], **raw.get("defaults", {})}
    merged["mj_loras"] = raw.get("mj_loras", _DEFAULTS["mj_loras"])
    return merged


CFG = Config(_load())
