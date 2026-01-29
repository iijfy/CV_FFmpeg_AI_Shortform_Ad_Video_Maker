"""
Pydantic 스키마

왜 스키마가 필요한가?
- FastAPI는 타입힌트/스키마로 요청/응답을 자동 문서화(Swagger) 해줍니다.
- 프론트/백엔드 사이 계약(Contract)이 명확해져서 협업이 쉬워집니다.
"""

from pydantic import BaseModel, Field

class GenerateResponse(BaseModel):
    job_id: str = Field(..., description="생성 작업 ID")
    video_url: str = Field(..., description="결과 mp4 다운로드/스트리밍 URL")
    caption_text: str = Field(..., description="생성된 상세/홍보 문구")
    hashtags: list[str] = Field(default_factory=list, description="추천 해시태그 리스트")
