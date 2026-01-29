"""
FastAPI 엔트리포인트

- /api/generate : 영상 생성
- /outputs/...  : 결과 mp4 정적 서빙

왜 정적 서빙?
- MVP에서는 DB나 Object Storage 없이도,
  생성된 파일을 바로 URL로 보여주면 데모가 쉬워지기 때문
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.app.core.config import settings
from backend.app.api.routes import router as api_router
from backend.app.core.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title="AI Shortform Ad Video Maker", version="0.1.0")

# CORS: Streamlit(8502)에서 FastAPI(8000) 호출할 거라 열어둠
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# 폴더가 없으면 FastAPI가 시작부터 죽기 때문에 미리 생성해둔다.
Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

@app.get("/health")
def health():
    return {"ok": True}
