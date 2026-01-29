"""
사진을 보고 자막을 어디에 두면 덜 가릴지 선택하는 휴리스틱.

아이디어:
- 사진을 위/중/아래 3개 밴드로 나눔
- 각 밴드의 "복잡도"를 계산
- 엣지(윤곽) 많으면 복잡도 높음
- 가장 덜 복잡한 밴드를 자막 위치로 선택

왜 이렇게 하나?
- 음식/인물 등 피사체는 보통 엣지/디테일이 많음
- 여백/배경은 엣지가 상대적으로 적음
- 딥러닝 세그멘테이션까지 가면 무겁고 리스크가 커서,
  프로젝트 MVP에서는 이 방식이 "가성비"가 좋다고 함
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class Anchor:
    name: str            # "top" | "mid" | "bottom"
    ass_an: int          # ASS alignment override (8=상단, 5=중앙, 2=하단)
    x: int               # 자막 중심 x (1080 기준 540)
    y: int               # 자막 y


ANCHORS = {
    "top": Anchor("top", ass_an=8, x=540, y=220),
    "mid": Anchor("mid", ass_an=5, x=540, y=960),
    "bottom": Anchor("bottom", ass_an=2, x=540, y=1700),
}


def _band_complexity(gray: np.ndarray) -> float:
    """
    복잡도 측정:
    - Canny edge 결과의 평균(엣지 픽셀 비율)로 간단히 측정
    값이 낮을수록 '덜 복잡' = 자막 올리기 좋음
    """
    edges = cv2.Canny(gray, 80, 160)
    return float(edges.mean())  # 0~255 평균


def pick_anchor_for_image(image_path: Path) -> Anchor:
    img = cv2.imread(str(image_path))
    if img is None:
        # 파일 읽기 실패 시 기본값: 상단
        return ANCHORS["top"]

    # 세로 쇼츠 기준이므로 일단 작은 사이즈로 줄여서 빠르게 계산
    img = cv2.resize(img, (540, 960))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h = gray.shape[0]
    # 위/중/아래 밴드 분할 (너무 극단적으로 나누면 오판 가능 -> 적당한 비율)
    top = gray[0:int(h*0.28), :]
    mid = gray[int(h*0.36):int(h*0.64), :]
    bot = gray[int(h*0.72):h, :]

    scores = {
        "top": _band_complexity(top),
        "mid": _band_complexity(mid),
        "bottom": _band_complexity(bot),
    }

    # 가장 덜 복잡한 곳 선택
    best = min(scores, key=scores.get)
    return ANCHORS[best]


def pick_anchors_for_images(image_paths: list[Path]) -> list[Anchor]:
    """
    슬라이드쇼는 이미지 1장당 caption 1줄로 대응시키는 게 가장 자연스러움.
    (이미지 N장 -> 문구 N줄 권장)
    """
    return [pick_anchor_for_image(p) for p in image_paths]
