"""
설정 로더

목표
- Python 3.9+에서도 문제 없이 돌아가게(= `str | None` 같은 3.10+ 문법 금지)
- .env가 좀 지저분해도, 깨지지 않게(extra ignore)
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env 사용 + 알 수 없는 키 무시
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- API Keys ---
    OPENAI_API_KEY: Optional[str] = Field(default=None)

    # --- Paths / Video ---
    OUTPUT_DIR: str = "outputs"
    VIDEO_SECONDS: int = 18
    VIDEO_SIZE: str = "1080x1920"  # 9:16
    # 기본 템포: 15초를 몇 구간으로 쪼갤지(= 자막/컷 템포)
    # 6이면 1컷당 2.5초라서 쇼츠 느낌이 꽤 살아납니다.
    VIDEO_SEGMENTS: int = 10

        # --- Caption (자막 UI) ---
    CAPTION_FONT_SIZE: int = 104      # 자막 글자 크기 (92~118 추천)
    CAPTION_BORDER_W: int = 12        # 글자 테두리 두께
    CAPTION_BOX_ALPHA: float = 0.35   # 자막 배경 박스 투명도(0~1)
    CAPTION_BOX_BORDER: int = 18      # 박스 여백(패딩 느낌)




    # --- TTS ---
    # (1) OpenAI TTS를 쓸 때의 voice
    OPENAI_TTS_VOICE: str = "shimmer"

    # (2) 로컬(macOS say)을 쓸 때의 voice
    TTS_VOICE: str = Field(default="Yuna", validation_alias="tts_voice")

    # 말하기 속도(1.0=기본). 예전 .env에서 tts_speed 로 쓰던 값도 받아줌
    TTS_SPEED: float = Field(default=1.0, validation_alias="tts_speed")


settings = Settings()
