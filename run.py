#!/usr/bin/env python3
"""
FastAPI + Streamlit을 '동시에' 띄우는 실행 스크립트.

왜 이런 파일이 있나?
- 부트캠프/해커톤에서 가장 흔한 실수: 백엔드/프론트 실행 커맨드가 제각각이라 팀원이 헷갈림
- python run.py 하나로 "항상 동일하게" 실행되게 만들면 생산성이 확 올라감

실행:
  python run.py
"""

import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
BACKEND_APP = PROJECT_ROOT / "backend" / "app" / "main.py"
FRONTEND_APP = PROJECT_ROOT / "frontend" / "app.py"

processes: list[subprocess.Popen] = []

def pick_free_port(start: int = 8501, end: int = 8510, host: str = "127.0.0.1") -> int:
    """start~end 중 사용 가능한 첫 포트를 선택"""
    import socket
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    # 다 찼으면 그냥 기본값 반환(실패할 수도 있음)
    return start


def shutdown(*_):
    print("\n🛑 종료 신호 받음. 프로세스 정리 중...")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    print("✅ 종료 완료")
    sys.exit(0)

def main():
    # Ctrl+C / 종료 시그널 처리
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # (1) FastAPI 실행
    # - uvicorn을 서브프로세스로 띄움
    api_cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload",
    ]
    print("🚀 Starting FastAPI:", " ".join(api_cmd))
    processes.append(subprocess.Popen(api_cmd, cwd=str(PROJECT_ROOT)))

    # (2) Streamlit 실행
    st_port = pick_free_port(start=8501, end=8510, host='127.0.0.1')

    st_cmd = [
        sys.executable, "-m", "streamlit",
        "run", str(FRONTEND_APP),
        "--server.port", str(st_port),
        "--server.address", "127.0.0.1",
    ]
    print(f"✅ Streamlit port: {st_port}")
    print("🚀 Starting Streamlit:", " ".join(st_cmd))
    processes.append(subprocess.Popen(st_cmd, cwd=str(PROJECT_ROOT)))

    # 메인 프로세스는 그냥 기다림 (서브프로세스가 죽으면 같이 종료되도록)
    for p in processes:
        p.wait()

if __name__ == "__main__":
    main()