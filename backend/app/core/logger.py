"""
로거(Logger) 모듈

왜 굳이 로거를 쓰나?
- print()는 '검색/필터/레벨'이 안됨
- 운영/디버깅할 때 "어디서 뭐가 터졌는지" 추적하려면 로거가 기본값
"""

import logging

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # 이미 설정되어 있으면 중복 설정 방지

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
