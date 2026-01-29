"""
ASS 자막 생성기

왜 ASS를 쓰나?
- SRT는 "글자 스타일(색/테두리/강조/애니메이션)" 표현이 약함
- 쇼츠 느낌(굵은 폰트+외곽선+키워드 컬러) 내려면 ASS가 훨씬 좋음

이 파일은:
- caption_lines (리스트[str])를 받아서
- 15초 안에서 균등 분배 타임라인으로
- .ass 자막 파일을 만들어준다.

고도화 포인트:
- 나중에 TTS 음성 길이/구간을 기준으로 타임라인 자동 조정 가능
"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class AssStyle:
    font_name: str = "Apple SD Gothic Neo"  # mac 기본
    font_size: int = 64
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00000000"
    shadow_color: str = "&H64000000"
    outline: int = 4
    shadow: int = 2

def _sec_to_ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _apply_highlight(text: str) -> str:
    import re
    yellow = r"{\c&H0000FFFF&}"
    white = r"{\c&H00FFFFFF&}"

    def repl_num(m):
        return f"{yellow}{m.group(0)}{white}"

    text = re.sub(r"\b\d+[,.]?\d*\b", repl_num, text)
    for kw in ["무한", "무료", "가성비", "역대급", "혜자"]:
        text = text.replace(kw, f"{yellow}{kw}{white}")
    return text

def write_ass_with_anchors(
    caption_lines: list[str],
    anchors: list[dict],   # [{"an":8, "x":540, "y":220}, ...]
    out_path: Path,
    video_seconds: float = 15.0,
    style: Optional[AssStyle] = None,
) -> Path:
    """
    anchors 길이는 caption_lines 길이와 같게.
    각 줄마다 \an + \pos로 위치를 바꾼다.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    style = style or AssStyle()

    n = max(1, len(caption_lines))
    per = video_seconds / n

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{style.font_name},{style.font_size},{style.primary_color},{style.outline_color},{style.shadow_color},1,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,60,60,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for i, raw in enumerate(caption_lines):
        start = i * per
        end = (i + 1) * per

        text = _apply_highlight(raw.strip())

        a = anchors[i] if i < len(anchors) else {"an": 8, "x": 540, "y": 220}
        an = a.get("an", 8)
        x = a.get("x", 540)
        y = a.get("y", 220)

        # 아주 짧은 fade로 '팝' 느낌
        # \an : 정렬(앵커), \pos : 위치 고정
        tag = rf"{{\an{an}\pos({x},{y})\fad(60,120)}}"
        events.append(
            f"Dialogue: 0,{_sec_to_ass_time(start)},{_sec_to_ass_time(end)},Base,,0,0,0,,{tag}{text}"
        )

    out_path.write_text(header + "\n".join(events), encoding="utf-8")
    return out_path
