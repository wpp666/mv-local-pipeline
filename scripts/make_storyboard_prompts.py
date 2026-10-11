# -*- coding: utf-8 -*-
"""从 krea2-prompts.md 解析分镜编辑指令，生成逐段/逐帧独立文件 + 参考图对应表（Krea 2 双图编辑）。

支持两种模式：
- 单图运镜段：每段 1 张关键帧，输出 Sxx.txt
- 多帧段：每段 4 帧，输出 Sxx-1.txt ... Sxx-4.txt
"""
import re
import shutil
from pathlib import Path

import mvconfig

ROOT = mvconfig.CFG.project_root
DOC = ROOT / "production" / "krea2-prompts.md"
OUT = ROOT / "production" / "krea2_edit_prompts"
REFS = ROOT / "assets" / "references"

REF_MAP = {
    "A1": "char-guardian.png",
    "A2": "char-guardian-head.png",
    "B1": "char-returnee.png",
    "B2": "char-returnee-head.png",
    "C": "loc-house.png",
    "D": "loc-field.png",
}

lines = DOC.read_text(encoding="utf-8").splitlines()

# 提取「统一风格块」（两版：有人物 / 空镜），自动追加到每条分镜提示词末尾
def extract_block(name):
    key = f"<!-- STYLE_BLOCK_{name}_START -->"
    end = f"<!-- STYLE_BLOCK_{name}_END -->"
    in_block, buf = False, []
    for ln in lines:
        t = ln.strip()
        if t == key:
            in_block = True
            continue
        if t == end:
            break
        if in_block and t:
            buf.append(t)
    return "".join(buf)

STYLE_PEOPLE = extract_block("PEOPLE")
STYLE_EMPTY = extract_block("EMPTY")

PERSON_WORDS = ("她", "他", "女子", "男子", "两人", "归人", "守候者")


def style_for(prompt):
    """画面含人物用有人物版，纯空镜用空镜版，避免在空镜里凭空加人。"""
    return STYLE_PEOPLE if any(w in prompt for w in PERSON_WORDS) else STYLE_EMPTY

seg_re = re.compile(r"^### (S\d{2}) · .*$")
frame_re = re.compile(r"^\*\*(S\d{2}-\d)\*\*$")

segments = []  # dict(id, mode, ref_line, camera, prompt, frames=[(fid, ref_line, prompt)])
i = 0
while i < len(lines):
    m = seg_re.match(lines[i].strip())
    if m:
        sid = m.group(1)
        mode = "single" if "单图运镜" in lines[i] else "multi"
        seg = {"id": sid, "mode": mode, "ref_line": "", "camera": "", "prompt": "", "frames": []}
        i += 1
        while i < len(lines) and not seg_re.match(lines[i].strip()):
            s = lines[i].strip()
            if mode == "single":
                if s.startswith("- **参考图**："):
                    seg["ref_line"] = s.split("：", 1)[1]
                elif s.startswith("- **段内运镜**："):
                    seg["camera"] = s.split("：", 1)[1]
                elif s.startswith("- **提示词**："):
                    rest = s.split("：", 1)[1].strip()
                    if not rest and i + 1 < len(lines):
                        rest = lines[i + 1].strip()
                        i += 1
                    seg["prompt"] = rest
            else:
                fm = frame_re.match(s)
                if fm:
                    fid = fm.group(1)
                    fl, fp = "", ""
                    j = i + 1
                    while j < len(lines) and not frame_re.match(lines[j].strip()) and not seg_re.match(lines[j].strip()):
                        t = lines[j].strip()
                        if t.startswith("参考图：") and not fl:
                            fl = t[len("参考图："):]
                        elif t.startswith("提示词：") and not fp:
                            fp = t[len("提示词："):]
                        j += 1
                    seg["frames"].append((fid, fl, fp))
                    i = j
                    continue
            i += 1
        segments.append(seg)
    else:
        i += 1

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

code_re = re.compile(r"图\d+\s*=\s*([ABCD][12]?)")


def ref_block(ref_line):
    codes = code_re.findall(ref_line)
    files = [REF_MAP[c] for c in codes if c in REF_MAP]
    out = ["参考图（图1 = 场景，图2 = 人物；按此顺序传入 Krea-2 双图编辑）："]
    if files:
        for n, f in enumerate(files, 1):
            out.append(f"  图{n} = {REFS / f}")
    else:
        out.append("  （无参考图，纯文生图）")
    return codes, files, out


index_rows = []
for seg in segments:
    sid = seg["id"]
    if seg["mode"] == "single":
        codes, files, block = ref_block(seg["ref_line"])
        body = [f"# {sid} · 单图运镜", ""] + block + [""]
        if seg["camera"]:
            body += [f"段内运镜：{seg['camera']}", ""]
        body += ["提示词：", seg["prompt"] + style_for(seg["prompt"])]
        (OUT / f"{sid}.txt").write_text("\n".join(body) + "\n", encoding="utf-8")
        index_rows.append((sid, "单图", codes, files, f"{sid}.txt"))
    else:
        for fid, fl, fp in seg["frames"]:
            codes, files, block = ref_block(fl)
            body = [f"# {fid}", ""] + block + ["", "提示词：", fp + style_for(fp)]
            (OUT / f"{fid}.txt").write_text("\n".join(body) + "\n", encoding="utf-8")
            index_rows.append((fid, "四帧", codes, files, f"{fid}.txt"))

idx = ["# 分镜 · 参考图对应表（9 段单图运镜 + 4 段多帧）", "",
       "| 段/帧 | 模式 | 参考图顺序 | 对应文件 | 提示词文件 |", "|---|---|---|---|---|"]
for fid, mode, codes, files, fn in index_rows:
    idx.append(
        f"| {fid} | {mode} | {' / '.join(codes) if codes else '无'} | "
        f"{' / '.join('`'+f+'`' for f in files) if files else '—'} | `{fn}` |"
    )
(OUT / "_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

singles = sum(1 for s in segments if s["mode"] == "single")
multis = sum(1 for s in segments if s["mode"] == "multi")
print(f"segments: {len(segments)} (single={singles}, multi={multis})")
print(f"style people/empty chars: {len(STYLE_PEOPLE)} / {len(STYLE_EMPTY)}")
print(f"files written: {len(index_rows)}")
print(f"out: {OUT}")
