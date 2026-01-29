"""
자막(SRT) 생성

왜 따로 모듈로 분리?
- 자막 규격(SRT, VTT) 바꾸거나
- 타이밍 계산 로직 바꾸거나
- 언어/줄바꿈 정책 바꾸기 쉬움

MVP 타이밍 전략:
- 진짜 음성 alignment(whisper forced align 등)은 무겁습니다.
- 일단은 15초를 caption_lines 개수로 균등 분배해서 SRT를 만듭니다.
"""

from __future__ import annotations
from pathlib import Path
from backend.app.core.config import settings

def _fmt(t: float) -> str:
    # SRT 시간 포맷: HH:MM:SS,mmm
    ms = int(t * 1000)
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(lines: list[str], out_path: Path) -> Path:
    total = settings.VIDEO_SECONDS
    n = max(1, len(lines))
    seg = total / n

    parts = []
    for i, line in enumerate(lines, start=1):
        start = (i - 1) * seg
        end = i * seg
        parts.append(
            f"{i}\n{_fmt(start)} --> {_fmt(end)}\n{line}\n"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return out_path
