"""
영상 생성 - FFmpeg

핵심 아이디어:
- 업로드한 여러 장의 사진을 9:16 슬라이드 쇼로 만들고
- 자막을 drawtext로 burn-in 하고
- BGM을 믹싱해서
- 최종 18초 mp4를 만든다.
- moviepy로도 가능하지만, 안정성/속도/호환성은 FFmpeg가 훨씬 좋다고 하여 선택함
- 그래서 "FFmpeg 커맨드를 만들고 실행"하는 구조로 만듬
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

from backend.app.core.config import settings
from backend.app.core.logger import get_logger
from backend.app.services.caption_placement import pick_anchors_for_images

from typing import Optional
from pathlib import Path

logger = get_logger(__name__)

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

# ffprobe도 같은 prefix를 쓰도록 맞추기
if Path(FFMPEG_BIN).name == "ffmpeg":
    FFPROBE_BIN = os.getenv("FFPROBE_BIN", "ffprobe")
else:
    FFPROBE_BIN = str(Path(FFMPEG_BIN).with_name("ffprobe"))


def _project_root() -> Path:
   
    return Path(__file__).resolve().parents[3]


def _run(cmd: list[str]):
    # FFmpeg 실행 유틸
    logger.info("FFmpeg 실행: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{p.stderr}")
    return p


def get_audio_duration_sec(audio_path: Path) -> float:
    # ffprobe로 오디오 길이(초) 측정
    cmd = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{p.stderr}")
    return float((p.stdout or "").strip() or "0")


def _escape_drawtext(s: str) -> str:
    # drawtext 필터 문자열이 깨지지 않도록 최소 escape
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace("%", "\\%")
    return s


def _pick_y_by_anchor_name(anchor_name: str) -> str:
    # top/mid/bottom에 따라 y 위치를 정함
    if anchor_name == "top":
        return "h*0.12"
    if anchor_name == "mid":
        return "h*0.48"
    return "h*0.82"


def _effect_zoompan(i: int) -> str:
    """
    안전한 zoompan 프리셋 (ffmpeg expr에서 on/d 같은 변수 사용 X)

    - zoompan 내부에서 프레임 인덱스/길이(d)를 나눗셈으로 쓰면
      ffmpeg 버전에 따라 'd' 파싱 문제가 나서 깨질 수 있음.
    - 그래서 "좌표를 고정"하거나 "간단한 식"만 사용

    리턴값: "zoompan=..." 전체 문자열
    """
    k = i % 4

    # 공통: 프레임 누적 줌인 (쇼츠 느낌나게)
    # zoom은 내부 상태로 누적되므로 zoom+... 형태가 안정적
    z_fast = "z='min(zoom+0.0040,1.20)'"
    z_slow = "z='min(zoom+0.0030,1.16)'"

    if k == 0:
        # 0) 중앙 줌인
        return f"zoompan={z_fast}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    if k == 1:
        # 1) 오른쪽 살짝 포커스 (고정 오프셋)
        return f"zoompan={z_slow}:x='iw*0.55-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    if k == 2:
        # 2) 위쪽 살짝 포커스
        return f"zoompan={z_slow}:x='iw/2-(iw/zoom/2)':y='ih*0.42-(ih/zoom/2)'"

    # 3) 아래쪽 살짝 포커스
    return f"zoompan={z_slow}:x='iw/2-(iw/zoom/2)':y='ih*0.62-(ih/zoom/2)'"




def build_slideshow(images: list[Path], out_video: Path) -> Path:
    """
    이미지 -> 무음 슬라이드쇼 mp4 생성

    포인트
    - images 개수로 18초를 균등 분할
    - 각 컷마다 zoompan 모션을 다르게 줘서 지루함 줄임
    - scale/pad/setsar로 입력 포맷이 달라도 concat 안정화
    """
    out_video.parent.mkdir(parents=True, exist_ok=True)

    total = float(settings.VIDEO_SECONDS)  # 기본 18초
    fps = 30
    n = max(1, len(images))
    per = total / n

    w, h = settings.VIDEO_SIZE.split("x")
    w, h = int(w), int(h)
    frames_per = max(1, int(per * fps))

    cmd = [FFMPEG_BIN, "-y"]

    # 1) 이미지 입력 추가 (-loop 1로 각 이미지를 영상처럼)
    for img in images:
        cmd += ["-loop", "1", "-t", str(per), "-i", str(img)]

    # 2) 각 이미지별 필터 체인 생성 (핵심: motion은 i로부터 만든다)
    filters: list[str] = []
    for i, _img in enumerate(images):
        motion = _effect_zoompan(i)  
        filters.append(
            f"[{i}:v]"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,"
            f"{motion}:d={frames_per}:s={w}x{h}:fps={fps},"
            f"eq=contrast=1.06:saturation=1.05,"
            f"trim=duration={per},setpts=PTS-STARTPTS,"
            f"format=yuv420p"
            f"[v{i}]"
        )

    # 3) concat으로 이어붙이기 (모든 v{i}를 하나로)
    concat_inputs = "".join([f"[v{i}]" for i in range(n)])
    filters.append(
        f"{concat_inputs}"
        f"concat=n={n}:v=1:a=0,"
        f"setsar=1,"
        f"format=yuv420p"
        f"[vout]"
    )

    filter_complex = ";".join(filters)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-t", str(total),
        str(out_video),
    ]
    _run(cmd)
    return out_video



def burn_text_overlays(
    in_video: Path,
    image_paths: list[Path],
    lines: list[str],
    out_video: Path,
    timings: Optional[List[Tuple[float, float]]] = None, 
) -> Path:
    """
    libass 없이도 항상 동작하는 drawtext 자막

    - timings가 있으면: 각 줄의 (start,end) 구간을 그대로 사용(싱크 개선)
    - timings가 없으면: total/n 균등 분배
    """
    out_video.parent.mkdir(parents=True, exist_ok=True)

    total = float(settings.VIDEO_SECONDS)
    lines = lines or [" "]
    n = max(1, len(lines))

    if not timings or len(timings) != n:
        per = total / n
        timings = [(i * per, (i + 1) * per) for i in range(n)]
        timings[-1] = (timings[-1][0], total)

    anchors = pick_anchors_for_images(image_paths)[:n]

    # 실행 위치 상관없이 안정적으로 폰트 찾기
    fontfile_path = (_project_root() / "assets" / "fonts" / "BMHANNAPro.ttf").resolve()
    fontfile = str(fontfile_path)  # ffmpeg에는 str로 넘거야 함

    # 자막 스타일: settings에서 읽기
    fontsize = int(getattr(settings, "CAPTION_FONT_SIZE", 104))
    borderw = int(getattr(settings, "CAPTION_BORDER_W", 12))
    box_alpha = float(getattr(settings, "CAPTION_BOX_ALPHA", 0.35))
    boxborder = int(getattr(settings, "CAPTION_BOX_BORDER", 18))


    draw_filters: list[str] = []
    for i, raw in enumerate(lines):
        start, end = timings[i]
        txt = _escape_drawtext((raw or "").strip())

        # 빈 텍스트면 필터 자체를 생략 (깨짐 방지)
        if not txt:
            continue

        y_expr = _pick_y_by_anchor_name(anchors[i].name) if i < len(anchors) else "h*0.12"

        draw_filters.append(
            "drawtext="
            f"fontfile='{fontfile}':"
            f"text='{txt}':"

            # 폰트 
            f"fontsize={fontsize}:"


            # 글자색/테두리/그림자 
            "fontcolor=white:"
            f"borderw={borderw}:"
            "bordercolor=black:"
            "shadowx=3:shadowy=3:shadowcolor=black@0.7:"

            # 반투명 박스배경 깔기
            "box=1:"
            f"boxcolor=black@{box_alpha}:"
            f"boxborderw={boxborder}:"


            # 위치: 가운데 정렬
            "x=(w-text_w)/2:"
            f"y={y_expr}:"

            # 타이밍
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )

    if not draw_filters:
        cmd = [FFMPEG_BIN, "-y", "-i", str(in_video), "-c", "copy", str(out_video)]
        _run(cmd)
        return out_video

    vf = ",".join(draw_filters)

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(in_video),
        "-vf", vf,
        "-c:a", "copy",
        str(out_video),
    ]
    _run(cmd)
    return out_video



def mix_audio(
    in_video: Path,
    voice_path: Optional[Path],
    bgm_path: Optional[Path],
    out_video: Path,
) -> Path:
    """
    최종 길이를 항상 settings.VIDEO_SECONDS로 고정 + BGM 덕킹(목소리 나오면 BGM 자동으로 내려감)

    - voice가 짧아도: apad + atrim으로 total 길이 맞춤
    - bgm은 loop 후 total로 자름
    - 둘 다 있으면:
        1) voice 정리(볼륨, apad, trim)
        2) bgm 정리(볼륨, trim)
        3) sidechaincompress로 bgm ducking
        4) amix로 합치고 total로 trim
    """
    out_video.parent.mkdir(parents=True, exist_ok=True)

    total = float(settings.VIDEO_SECONDS)
    cmd = [FFMPEG_BIN, "-y", "-i", str(in_video)]

    has_voice = bool(voice_path and Path(voice_path).exists())
    has_bgm = bool(bgm_path and Path(bgm_path).exists())

    # 오디오가 아예 없으면 그대로 복사
    if not has_voice and not has_bgm:
        cmd += ["-c", "copy", str(out_video)]
        _run(cmd)
        return out_video

    filter_parts: list[str] = []
    idx = 1  # 0은 video 입력

    
    # Voice chain
    if has_voice:
        cmd += ["-i", str(voice_path)]
    
        filter_parts.append(
            f"[{idx}:a]"
            f"volume=1.0,"
            f"apad,"
            f"atrim=0:{total},"
            f"asetpts=N/SR/TB"
            f"[a_voice]"
        )
        idx += 1

    
    # BGM chain
    if has_bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm_path)]
        # bgm 볼륨은 덕킹 전 기준값. 너무 크면 덕킹해도 거슬림.
        filter_parts.append(
            f"[{idx}:a]"
            f"volume=0.22,"
            f"atrim=0:{total},"
            f"asetpts=N/SR/TB"
            f"[a_bgm]"
        )
        idx += 1

    
    # Mix / Ducking
    if has_voice and has_bgm:
        # 핵심: sidechaincompress
        # 파라미터 감각:
        # - threshold: 덕킹 시작 기준(낮을수록 자주 덕킹)
        # - ratio: 눌리는 강도(10~20이면 광고 느낌으로 확실함)
        # - attack: 내려가는 속도(빠를수록 '딱' 내려감)
        # - release: 다시 올라오는 속도(너무 짧으면 펌핑, 너무 길면 답답)
        filter_parts.append(
            "[a_bgm][a_voice]"
            "sidechaincompress="
            "threshold=0.035:"
            "ratio=16:"
            "attack=10:"
            "release=250:"
            "makeup=1"
            "[a_bgm_duck]"
        )

        # 덕킹된 bgm + voice 합치기
        filter_parts.append(
            "[a_voice][a_bgm_duck]"
            "amix=inputs=2:duration=longest:dropout_transition=2,"
            f"atrim=0:{total},asetpts=N/SR/TB"
            "[a_out]"
        )

    elif has_voice and not has_bgm:
        filter_parts.append("[a_voice]anull[a_out]")

    elif has_bgm and not has_voice:
        filter_parts.append("[a_bgm]anull[a_out]")

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "0:v:0",
        "-map", "[a_out]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-t", str(total),
        str(out_video),
    ]
    _run(cmd)
    return out_video
