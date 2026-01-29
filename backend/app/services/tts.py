from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Optional

from backend.app.core.config import settings
from backend.app.core.logger import get_logger

logger = get_logger(__name__)


FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    logger.info("TTS 실행: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr or "command failed")
    return p


def _macos_say(text: str, out_mp3: Path) -> Optional[Path]:
    """
    macOS 내장 say로 MP3 생성

    - say는 AIFF/CAF 쪽이 안정적이라 일단 aiff로 뽑고
    - ffmpeg로 mp3로 변환
    """
    if not text.strip():
        return None

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    tmp_aiff = out_mp3.with_suffix(".aiff")

    # 말 빠르기: say는 -r로 WPM 조절
    # 180~220이 쇼츠 느낌이 잘 난다고 하여 200 기준
    wpm = int(200 * float(settings.TTS_SPEED))
    voice = settings.TTS_VOICE or "Yuna"

    cmd_say = [
        "say",
        "-v",
        voice,
        "-r",
        str(wpm),
        "-o",
        str(tmp_aiff),
        text,
    ]

    try:
        _run(cmd_say)
    except Exception as e:
        logger.warning("macOS say 실패(voice=%s). 기본 voice로 재시도: %s", voice, e)
        # voice가 없는 경우가 많아서 -v 없이 1회 더
        _run(["say", "-r", str(wpm), "-o", str(tmp_aiff), text])

    # aiff -> mp3
    cmd_ff = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(tmp_aiff),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "192k",
        str(out_mp3),
    ]
    _run(cmd_ff)

    # tmp 정리
    try:
        tmp_aiff.unlink(missing_ok=True)  # py3.8+ ok
    except Exception:
        pass

    return out_mp3


def _openai_tts(text: str, out_mp3: Path) -> Optional[Path]:
    """OpenAI TTS (키가 있을 때만)

    NOTE: MVP에선 REST로 호출 (SDK 버전 변동 이슈 회피)
    """
    if not settings.OPENAI_API_KEY:
        return None
    if not text.strip():
        return None

    import requests

    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini-tts",
        "voice": settings.OPENAI_TTS_VOICE,
        "input": text,
        "format": "mp3",
        # 광고 쇼츠 톤: 빠르고 끊어읽기, 군더더기 없는 호흡
        "instructions": "Speak fast and energetic like a short-form ad. Minimal pauses. Clear diction.",
    }

    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI TTS failed: {r.status_code} {r.text}")

    out_mp3.write_bytes(r.content)
    return out_mp3


def synthesize_voice(text: str, out_mp3: Path) -> Optional[Path]:
    """
    텍스트 -> 음성(mp3)

    동작 규칙
    1) OPENAI_API_KEY가 있으면 OpenAI TTS 사용
    2) 없으면 macOS say로 fallback (맥이 아니면 None)
    """
    if settings.OPENAI_API_KEY:
        try:
            return _openai_tts(text, out_mp3)
        except Exception as e:
            logger.warning("OpenAI TTS 실패. local TTS로 fallback: %s", e)

    if platform.system() == "Darwin":
        return _macos_say(text, out_mp3)

    # 다른 OS는 MVP 범위 밖: 음성 없이 진행
    logger.info("OPENAI_API_KEY가 없고 macOS도 아니어서 TTS를 스킵합니다(무음으로 진행).")
    return None


from typing import List, Tuple

def _ffprobe_duration_sec(path: Path) -> float:
    # mp3 실제 길이(초) 측정 - 자막 싱크의 기준이 됨
    ffprobe = os.getenv("FFPROBE_BIN", "ffprobe")
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{p.stderr}")
    return float((p.stdout or "").strip() or "0")

def _postprocess_voice(in_mp3: Path, out_mp3: Path, speed: float = 1.10) -> Path:
    """
    '느리고 액션감 없는' 원인 1순위 = 말 사이 공백 + 전체 템포
    → silenceremove로 앞/뒤/중간 작은 무음 줄이고, atempo로 살짝 빠르게,
      loudnorm로 음량 정리(영상에서 또렷해짐)
    """
    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    # atempo는 0.5~2.0 범위만 안전
    speed = max(0.8, min(1.4, float(speed)))

    af = ",".join([
        # 앞/뒤 무음 제거(너무 세게 자르면 발음 끊김 → threshold는 -40dB 근처 추천)
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-40dB:"
        "stop_periods=1:stop_duration=0.05:stop_threshold=-40dB",
        # 템포 살짝 업(체감 액션감)
        f"atempo={speed}",
        # 음량/다이내믹 정리 (목소리 또렷)
        "loudnorm=I=-16:LRA=11:TP=-1.5",
    ])

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(in_mp3),
        "-vn",
        "-af", af,
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        str(out_mp3),
    ]
    _run(cmd)
    return out_mp3

def synthesize_voice_lines(
    lines: List[str],
    out_dir: Path,
    *,
    speed_up: float = 1.10,
    tiny_pause_sec: float = 0.03,
) -> Tuple[Path, List[Tuple[float, float]]]:

    out_dir.mkdir(parents=True, exist_ok=True)

    parts: List[Path] = []
    durs: List[float] = []

    for i, line in enumerate(lines):
        line = (line or "").strip()
        if not line:
            continue

        raw = out_dir / f"line_{i:02d}_raw.mp3"
        part = out_dir / f"line_{i:02d}.mp3"

        try:
            # 1) TTS 생성
            tts_out = synthesize_voice(line, raw)

            # 핵심: TTS가 None이거나 파일이 안 생기면 이 줄은 스킵
            if (tts_out is None) or (not raw.exists()) or (raw.stat().st_size < 1000):
                logger.warning("TTS line_%02d 생성 실패/무음 (OS=%s, key=%s) → 스킵",
                               i, platform.system(), bool(settings.OPENAI_API_KEY))
                continue

            # 2) 후처리(무음 제거/속도/정규화)
            _postprocess_voice(raw, part, speed=speed_up)

            # 후처리 결과 파일 체크
            if (not part.exists()) or (part.stat().st_size < 1000):
                logger.warning("TTS line_%02d 후처리 결과가 비정상 → 스킵", i)
                continue

            # 3) 길이 측정 (ffprobe 실패해도 대충 추정해서 진행)
            try:
                dur = _ffprobe_duration_sec(part)
            except Exception:
                dur = max(0.7, min(2.2, len(line) / 7.0))  # 글자수 기반 추정

            parts.append(part)
            durs.append(dur)

        except Exception as e:
            logger.warning("TTS line_%02d 처리 중 예외 → 스킵: %s", i, e)
            continue

    # 아무 파트도 없으면: '명확한 원인 로그'를 남기고 무음으로 반환(파이프라인은 유지)
    if not parts:
        logger.error(
            "TTS 결과가 0개입니다. (OS=%s, OPENAI_API_KEY=%s) "
            "→ Linux/Docker면 OPENAI_API_KEY가 백엔드에 주입돼야 합니다.",
            platform.system(), bool(settings.OPENAI_API_KEY)
        )
        empty = out_dir / "voice.mp3"
        # 빈 bytes mp3는 깨질 수 있어서 ffmpeg로 0.2초 무음 mp3 생성(안전)
        cmd_silence = [
            FFMPEG_BIN, "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "0.2",
            "-codec:a", "libmp3lame", "-b:a", "192k",
            str(empty),
        ]
        _run(cmd_silence)
        return empty, []

    # concat은 기존 그대로
    concat_txt = out_dir / "concat.txt"
    concat_txt.write_text(
        "\n".join([f"file '{p.as_posix()}'" for p in parts]),
        encoding="utf-8"
    )

    voice_mp3 = out_dir / "voice.mp3"
    cmd_concat = [
        FFMPEG_BIN, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-codec:a", "libmp3lame", "-b:a", "192k",
        str(voice_mp3),
    ]
    _run(cmd_concat)

    timings: List[Tuple[float, float]] = []
    t = 0.0
    for dur in durs:
        start = t
        end = t + dur
        timings.append((start, end))
        t = end + float(tiny_pause_sec)

    return voice_mp3, timings
