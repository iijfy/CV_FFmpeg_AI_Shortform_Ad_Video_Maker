"""
API 라우터

- 프론트(Streamlit)가 보내는 멀티파트(이미지 + 텍스트)를 받음
- LLM/TTS/Video 순서대로 실행
- 결과 URL 반환
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from backend.app.core.logger import get_logger
from backend.app.core.config import settings
from backend.app.schemas import GenerateResponse

from backend.app.services.storage import make_job_dir, public_video_path
from backend.app.services.llm import generate_copy
from backend.app.services.tts import synthesize_voice_lines
from backend.app.services.video import (
    build_slideshow,
    burn_text_overlays,
    mix_audio,
    get_audio_duration_sec,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["generator"])


def _project_root() -> Path:
    """
    routes.py 위치: backend/app/api/routes.py
    parents[0]=api, [1]=app, [2]=backend, [3]=PROJECT_ROOT
    """
    return Path(__file__).resolve().parents[3]


def _normalize_for_tts(s: str) -> str:
    """
    TTS가 또박또박 읽게끔 최소 보정
    - 너무 공격적으로 정리하면 감성(…/이모지)이 죽으니 최소만
    """
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("…", ".")
    s = s.replace("·", " ")
    return s.strip()


def _safe_segments() -> int:
    """
    settings.VIDEO_SEGMENTS가 없거나 이상한 값이면 6으로 안전하게 보정
    """
    try:
        v = int(getattr(settings, "VIDEO_SEGMENTS", 6))
    except Exception:
        v = 6
    return max(1, min(12, v))  # 너무 많으면 오히려 산만해져서 상한 12


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    images: list[UploadFile] = File(..., description="음식 사진들 (2~6장 권장)"),
    menu_name: str = Form(..., description="메뉴 이름"),

    store_name: str = Form("", description="가게 이름(선택)"),
    tone: str = Form("감성", description="광고 톤(힙/감성/고급/가성비)"),

    # 추가 입력(선택)
    price: str = Form("", description="가격(선택)"),
    location: str = Form("", description="위치(선택)"),
    benefit: str = Form("", description="혜택(선택)"),
    cta: str = Form("", description="콜투액션(선택)"),
):
   

    # 0) 입력 검증
    if len(images) < 1:
        raise HTTPException(400, "이미지를 1장 이상 업로드해주세요.")
    if not (menu_name or "").strip():
        raise HTTPException(400, "메뉴 이름은 필수입니다.")

    menu_name = menu_name.strip()
    store_name = (store_name or "").strip() or None
    tone = (tone or "감성").strip()

    price = (price or "").strip() or None
    location = (location or "").strip() or None
    benefit = (benefit or "").strip() or None
    cta = (cta or "").strip() or None


    # 1) 작업 디렉토리 생성
    job_dir = make_job_dir()
    inputs_dir = job_dir / "inputs"
    artifacts_dir = job_dir / "artifacts"

    
    # 2) 이미지 저장
    img_paths: list[Path] = []
    for i, uf in enumerate(images, start=1):
        suffix = Path(uf.filename).suffix.lower() or ".jpg"
        save_path = inputs_dir / f"img_{i}{suffix}"
        save_path.write_bytes(await uf.read())
        img_paths.append(save_path)


    # 3) 쇼츠 템포용 컷 수 확정
    target_cuts = _safe_segments()

    # 이미지가 적으면 반복해서 컷 수 맞춤 (템포 유지)
    image_paths_for_video = [img_paths[i % len(img_paths)] for i in range(target_cuts)]

 
    # 4) LLM 카피 생성 (컷 수 = 캡션 줄 수)
    llm_out = generate_copy(
        menu_name=menu_name,
        store_name=store_name,
        tone=tone,
        n_lines=target_cuts,
        price=price,
        location=location,
        benefit=benefit,
        cta=cta,
    )

    caption_lines = (llm_out.caption_lines or [])[:target_cuts]
    if len(caption_lines) < target_cuts:
        caption_lines += [""] * (target_cuts - len(caption_lines))

    # 빈 줄 제거 (자막/내레이션 둘 다 깔끔)
    caption_lines_clean = [_normalize_for_tts(s) for s in caption_lines if s and s.strip()]


    # 완전 빈 경우 대비
    if not caption_lines_clean:
        fallback = _normalize_for_tts(llm_out.promo_text) if getattr(llm_out, "promo_text", "") else ""
        caption_lines_clean = [fallback] if fallback else ["지금 바로 방문해보세요!"]

   # 프론트에 보여줄 전체 카피 텍스트(복사/공유용)
    tts_text = "\n".join(caption_lines_clean)


    # 5) TTS (줄별 생성 → 싱크 정확)
    voice_path = None
    timings = None


   
    # 6) 슬라이드쇼(무음) 생성: 항상 18초
    silent_video = build_slideshow(image_paths_for_video, artifacts_dir / "silent.mp4")



    # 8) drawtext로 자막 burn-in
    sub_video = burn_text_overlays(
        in_video=silent_video,
        image_paths=image_paths_for_video,
        lines=caption_lines_clean,
        out_video=artifacts_dir / "subtitled.mp4",
        timings=timings,  # video.py와 맞춤
    )

    # 9) BGM 선택: 실행 위치 상관없이 프로젝트 루트 기준
    bgm_dir = _project_root() / "assets" / "bgm"
    bgm_candidates = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
    bgm_path = bgm_candidates[0] if bgm_candidates else None


    logger.info(
    "AUDIO DEBUG | voice_path=%s exists=%s | bgm_path=%s exists=%s",
    str(voice_path) if voice_path else None,
    bool(voice_path and Path(voice_path).exists()),
    str(bgm_path) if bgm_path else None,
    bool(bgm_path and Path(bgm_path).exists()),
    )

 
    # 10) 오디오 믹스해서 최종 mp4
    final_path = mix_audio(sub_video, None, bgm_path, public_video_path(job_dir))



    # 11) 결과 반환
    job_id = job_dir.name
    video_url = f"/outputs/{job_id}/artifacts/final.mp4"

    return GenerateResponse(
        job_id=job_id,
        video_url=video_url,
        caption_text=tts_text,
        hashtags=llm_out.hashtags,
    )
