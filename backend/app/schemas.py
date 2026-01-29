from pydantic import BaseModel, Field

class GenerateResponse(BaseModel):
    job_id: str = Field(..., description="생성 작업 ID")
    video_url: str = Field(..., description="결과 mp4 다운로드/스트리밍 URL")
    caption_text: str = Field(..., description="생성된 상세/홍보 문구")
    hashtags: list[str] = Field(default_factory=list, description="추천 해시태그 리스트")
