"""
스토리지 유틸

MVP에서는 로컬 디스크에 저장하지만,
나중에 GCS/S3로 바꾸기 쉬우라고 '한 곳'에 모아둡니다.
"""

from __future__ import annotations
import os
import uuid
from pathlib import Path
from backend.app.core.config import settings

def make_job_dir() -> Path:
    job_id = uuid.uuid4().hex[:12]
    out_root = Path(settings.OUTPUT_DIR)
    job_dir = out_root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "inputs").mkdir(exist_ok=True)
    (job_dir / "artifacts").mkdir(exist_ok=True)
    return job_dir

def public_video_path(job_dir: Path) -> Path:
    # 결과 영상은 job_dir/artifacts/final.mp4 로 고정 (규칙!)
    return job_dir / "artifacts" / "final.mp4"
