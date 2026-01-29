"""
LLM 

역할:
- 메뉴/가게명/톤(+ 옵션 정보)를 받아서
  - 18초 쇼츠용 캡션 8~10줄
  - 3~5문장 프로모션 문구
  - 해시태그 5~12개
를 생성.

목표(정보전달 포함):
- 유튜브 쇼츠처럼 "훅 → 정보 → 신뢰 → 혜택 → 긴급/한정 → CTA" 흐름을 갖게 한다.
- 과장/허위 효능/의학적 주장 금지.
- LLM 키가 없어도 fallback이 '허접'하지 않게 템플릿을 강화한다.
"""

from __future__ import annotations

import json
import re
import random
from dataclasses import dataclass
from typing import List, Optional

from backend.app.core.config import settings
from backend.app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LLMOutput:
    caption_lines: List[str]
    promo_text: str
    hashtags: List[str]


# 유틸
def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def _tone_profile(tone: str) -> dict:
    t = (tone or "감성").strip()

    # 톤별 말투/단어 선택 가이드
    if t in ["힙", "힙합", "스트릿"]:
        return {
            "hook": ["지금 이거 안 먹으면 손해", "이 조합 미쳤다", "요즘 이게 유행이야"],
            "style": "짧고 리듬감 있게, 구어체, 약간 쿨하게",
            "cta": ["지금 바로 찍고 가", "오늘 ㄱㄱ", "지금 주문 ㄱ"],
        }
    if t in ["고급", "프리미엄", "럭셔리"]:
        return {
            "hook": ["오늘은 제대로 먹자", "한 끼라도 품격 있게", "입안에서 정리되는 맛"],
            "style": "정돈된 문장, 과하지 않게, 신뢰감 있게",
            "cta": ["예약/방문 문의 주세요", "지금 바로 확인해보세요", "오늘 한정 추천드립니다"],
        }
    if t in ["가성비", "실속", "저렴"]:
        return {
            "hook": ["가격 보고 두 번 놀람", "이 퀄리티에 이 가격?", "가성비로 끝내자"],
            "style": "정보 중심 + 직설, 부담 없이",
            "cta": ["지금 바로 주문!", "오늘 득템하자", "가성비 찾으면 여기"],
        }

    # 기본: 감성
    return {
        "hook": ["지금 딱 생각나는 맛", "오늘 하루, 이걸로 보상", "입맛 돌아오는 순간"],
        "style": "감성 + 정보 균형, 부드럽게",
        "cta": ["오늘 한 번 들러보세요", "지금 주문/방문 환영", "지금 바로 맛보세요"],
    }


def _shorts_bank(tone: str) -> dict:
    """
    쇼츠 자막용 문장 뱅크(톤별)
    - 너무 광고 티 나는 표현/과장은 피하고
    - 짧고 리듬감 있게(10~16자 중심)
    """
    t = (tone or "감성").strip()

    if t in ["힙", "힙합", "스트릿"]:
        return {
            "sensory": ["비주얼 미쳤다", "향 올라온다", "한입에 끝", "바삭+촉촉", "단짠 밸런스"],
            "usp": ["요즘 이 조합", "입맛 복구됨", "중독주의", "친구랑 ㄱㄱ", "혼밥도 OK"],
            "trust": ["사진 그대로 OK", "재료 아낌없음", "맛은 보장", "기본기 탄탄"],
            "urgency": ["지금이 타이밍", "오늘 안 먹으면 손해", "저녁은 이거"],
            "cta": ["저장하고 가자", "오늘 ㄱㄱ", "지금 주문 ㄱ", "지금 찍고 가"],
        }

    if t in ["고급", "프리미엄", "럭셔리"]:
        return {
            "sensory": ["한입에 정리", "향이 다르다", "식감이 깔끔", "끝맛이 고급"],
            "usp": ["한 끼의 품격", "정성 느껴짐", "밸런스 좋다", "과하지 않게"],
            "trust": ["사진 그대로 OK", "재료 퀄리티", "기본이 탄탄", "깔끔하게 준비"],
            "urgency": ["오늘은 여기", "지금 딱 좋아요", "저녁 추천"],
            "cta": ["오늘 한 번 들러요", "지금 확인해보세요", "예약/방문 문의"],
        }

    if t in ["가성비", "실속", "저렴"]:
        return {
            "sensory": ["양 실화냐", "비주얼 합격", "한입에 든든", "끝까지 뜨끈"],
            "usp": ["가성비로 끝", "배부르게 OK", "혼밥도 굿", "세트로 이득"],
            "trust": ["사진 그대로 OK", "양 속이지 않음", "재방문 각", "맛은 확실"],
            "urgency": ["오늘 메뉴 확정", "지금이 타이밍", "저녁 고민 끝"],
            "cta": ["지금 주문!", "저장해두자", "가성비 찾으면 여기"],
        }

    # 기본: 감성
    return {
        "sensory": ["입맛 돌아온다", "한입에 위로", "따끈하게 딱", "촉촉하게 쫙"],
        "usp": ["오늘 보상 완료", "기분 좋아지는 맛", "부담 없이 좋아", "딱 생각나는 맛"],
        "trust": ["사진 그대로 OK", "정성 담았어요", "기본이 좋아요", "깔끔하게 준비"],
        "urgency": ["오늘은 이거", "지금이 타이밍", "저녁으로 딱"],
        "cta": ["저장하고 가요", "오늘 한 번 들러요", "지금 바로 맛보자"],
    }


def _normalize_line(s: str) -> str:
    # 너무 긴 공백/기호 정리 (감성 살리되 깨짐 방지)
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("…", ".")
    return s.strip()


def _cap_len(s: str, max_chars: int = 16) -> str:
    # 쇼츠 자막은 너무 길면 답답함. 대략 10~16자 선에서 끊기.
    s = _normalize_line(s)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _hashtags(menu_name: str, store_name: Optional[str], location: Optional[str]) -> List[str]:
    tags = []
    base = [
        f"#{menu_name}",
        "#맛집",
        "#오늘의메뉴",
        "#먹방",
        "#쇼츠",
        "#배달",
        "#포장",
    ]
    tags.extend(base)

    if store_name:
        tags.append(f"#{store_name.replace(' ', '')}")
    if location:
        tags.append(f"#{location.replace(' ', '')}")

    out = []
    seen = set()
    for t in tags:
        if t not in seen and len(out) < 12:
            out.append(t)
            seen.add(t)
    return out



# 이모지(절제) - fallback에만 사용
def _emoji_pool(tone: str) -> List[str]:
    t = (tone or "감성").strip()
    if t in ["힙", "힙합", "스트릿"]:
        return ["🔥", "⚡️", "😋", "💥", "🖤"]
    if t in ["고급", "프리미엄", "럭셔리"]:
        return ["✨", "🍷", "🤍", "🌿", "⭐️"]
    if t in ["가성비", "실속", "저렴"]:
        return ["💸", "✅", "🍽️", "😋", "🔥"]
    return ["✨", "😋", "🔥", "🌙", "🤍"]


def _looks_like_info_line(s: str) -> bool:
    """
    가격/위치/혜택 같은 '정보 줄' 판별
    - 이런 줄엔 이모지를 붙이면 유치해 보일 확률이 높아서 금지
    """
    s = (s or "").strip()
    if not s:
        return False

    # 가격 느낌
    if any(x in s for x in ["원", "₩", "만원", "천원", "세트", "1인", "2인"]):
        return True

    # 위치 느낌
    if any(x in s for x in ["역", "동", "구", "시", "근처", "앞", "옆", "골목", "거리"]):
        return True

    # 혜택/이벤트 느낌
    if any(x in s for x in ["할인", "증정", "서비스", "이벤트", "쿠폰", "혜택", "리뷰"]):
        return True

    return False


def _add_emojis_fallback(lines: List[str], tone: str, max_emojis: int = 2) -> List[str]:
    """
    fallback 전용: 이모지를 '딱' 몇 줄에만 추가
    룰:
    - 줄당 최대 1개
    - 전체 max_emojis개만
    - 정보줄(가격/위치/혜택)에는 절대 붙이지 않음
    """
    if not lines:
        return lines

    pool = _emoji_pool(tone)

    candidates = []
    for i, s in enumerate(lines):
        s = (s or "").strip()
        if not s:
            continue
        if _looks_like_info_line(s):
            continue
        # 이미 이모지/특수기호가 있으면 과해지니 스킵
        if any(ch in s for ch in ["🔥", "✨", "😋", "⭐", "💸", "✅", "⚡", "💥", "🤍", "🖤", "🌙", "🍽", "🍷", "🌿"]):
            continue
        candidates.append(i)

    if not candidates:
        return lines

    k = min(max_emojis, len(candidates))
    picks = random.sample(candidates, k=k)

    out = lines[:]
    for idx in picks:
        out[idx] = f"{random.choice(pool)} {out[idx]}".strip()

    return out



# fallback (키 없을 때도 "괜찮게")
def _fallback(
    menu_name: str,
    store_name: Optional[str],
    tone: str,
    n_lines: int,
    price: Optional[str] = None,
    location: Optional[str] = None,
    benefit: Optional[str] = None,
    cta: Optional[str] = None,
) -> LLMOutput:
    store = store_name or "우리 가게"
    tonep = _tone_profile(tone)
    bank = _shorts_bank(tone)

    hook = tonep["hook"][0]  # 톤 프로필의 훅
    cta_text = cta or random.choice(bank["cta"])

    # 정보는 한 줄에 1개만
    if price:
        info = f"{price}면 끝"
    elif benefit:
        info = benefit
    elif location:
        info = location
    else:
        info = random.choice(bank["urgency"])

    sensory = random.choice(bank["sensory"])
    usp = random.choice(bank["usp"])
    trust = random.choice(bank["trust"])

    base_lines = [
        hook,
        f"{menu_name} 나왔음",
        sensory,
        usp,
        trust,
        info,
        cta_text,
    ]

    n = max(4, min(12, int(n_lines or 6)))

    lines = base_lines[:n]
    if len(lines) < n:
        fillers = ["한입에 끝", "육즙 터진다", "오늘 메뉴 확정", "저장해두자"]
        k = 0
        while len(lines) < n and k < 10:
            lines.insert(-1, fillers[k % len(fillers)])
            k += 1

    # 길이 캡
    lines = [_cap_len(_normalize_line(x), 16) for x in lines]

    # fallback에만 절제 이모지 추가(최대 2개)
    lines = _add_emojis_fallback(lines, tone, max_emojis=2)

    promo_parts = [
        f"{store}의 {menu_name} 추천!",
        f"{('가격은 ' + price) if price else '지금 막 준비했어요.'}",
        f"{('위치는 ' + location) if location else ''}".strip(),
        f"{benefit if benefit else '따끈하게 준비해서 바로 드실 수 있어요.'}",
        f"주문/방문은 {cta_text}.",
    ]
    promo = " ".join([p for p in promo_parts if p])

    tags = _hashtags(menu_name, store_name, location)
    return LLMOutput(lines, promo, tags)



# OpenAI 호출 (있으면 더 자연스럽게)
def _parse_json_safely(text: str) -> Optional[dict]:
    """
    모델이 JSON 외 텍스트를 섞어도 최대한 복구하는 파서
    """
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None

    chunk = m.group(0)
    try:
        return json.loads(chunk)
    except Exception:
        return None


def generate_copy(
    menu_name: str,
    store_name: Optional[str],
    tone: str,
    n_lines: int = 6,
    price: Optional[str] = None,
    location: Optional[str] = None,
    benefit: Optional[str] = None,
    cta: Optional[str] = None,
) -> LLMOutput:
    """
    LLM이 있으면 LLM, 없으면 fallback.

    n_lines:
    - routes.py에서 컷 수(target_cuts)에 맞춰 넘겨줌 (보통 6)
    """
    menu_name = _clean(menu_name) or "오늘의 메뉴"
    store_name = _clean(store_name)
    tone = _clean(tone) or "감성"

    price = _clean(price)
    location = _clean(location)
    benefit = _clean(benefit)
    cta = _clean(cta)

    n_lines = max(4, min(12, int(n_lines or 6)))

    if not settings.OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY가 없어 fallback 문구를 사용합니다.")
        return _fallback(
            menu_name=menu_name,
            store_name=store_name,
            tone=tone,
            n_lines=n_lines,
            price=price,
            location=location,
            benefit=benefit,
            cta=cta,
        )

    import requests

    store_str = store_name or "미기재"
    price_str = price or "미기재"
    location_str = location or "미기재"
    benefit_str = benefit or "미기재"
    cta_str = cta or "미기재"

    prompt = f"""
너는 한국 음식점 유튜브 쇼츠(9:16, 18초) 광고 자막 카피라이터다.
10~30대 남녀노소 상대로 재미있게 음식점/메뉴를 홍보하는 문구를 만든다.
너무 짧게는 하지말고 적어도 6자 이상은 되게 한다.
목표: "짧게, 박자 있게, 저장/방문을 부르게, 재미 있게" 만드는 자막.


입력:
- 가게명: {store_str}
- 메뉴명: {menu_name}
- 톤: {tone}
- 가격: {price_str}
- 위치: {location_str}
- 혜택: {benefit_str}
- CTA: {cta_str}

출력은 JSON만:
{{
  "caption_lines": ["...","..."],
  "promo_text": "3~5문장",
  "hashtags": ["#..."]
}}

[caption_lines 규칙] (가장 중요)
- 정확히 {n_lines}줄.
- 각 줄: 10~16자(공백 포함). 길면 자르고 다시 써라.
- 문장부호/느낌표/이모지 남발 금지(이모지는 전체 0~1개만).
- '최고의/완벽한/해드립니다/강추/대박/무조건' 같은 광고 티 나는 말투 금지.
- 한 줄엔 정보 1개만(가격/위치/혜택 중 하나). 미기재면 넣지 마라.
- 구어체 + 리듬감. “짧은 말” 위주.
- 마지막 줄은 반드시 CTA(저장/방문/주문 유도).


[이모지 규칙]
- 캡션 전체에 이모지는 "정확히 1개"만 사용해라.
- 그 1개는 "첫 줄(훅)"에만 붙여라.
- 사용 가능한 이모지: 🔥 ⭐️ 🍜 🍖 🥟 🍣 🧀 🥩 🌶️
- 다른 이모지 금지.

[전개 템플릿]
1) 훅(시선 잡기) 
2) 비주얼/식감/향(감각 1개)
3) 장점(가성비/푸짐/매운맛/담백 등 1개)
4) (선택) 가격 or 혜택 (1개만)
5) (선택) 위치/동네 (1개만)
6) CTA(저장/오늘가자/지금주문)

[좋은 예]
- "🔥 비주얼 미쳤네 이거 보여?"
- "육즙이.. 이거머임?!"
- "바삭+촉촉한 완벽 조합 배고파!!"
- "이정도면 가성비 끝 아님?"
- "검색하느라 힘 빼지마!"
- "한번오면 또 오게 될걸?!"
- "후기만 봐도 맛집이지?^^"
- "오늘 저녁은.. 여기다! ㅋㅋ"
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You write short-form Korean ad copy with clear structure and strong rhythm."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
        "top_p": 0.9,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.2,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = _parse_json_safely(content)

        if not data:
            raise ValueError("JSON parse failed")

        lines = data.get("caption_lines") or []
        promo = data.get("promo_text") or ""
        tags = data.get("hashtags") or []

        lines = [str(x) for x in lines][:n_lines]
        if len(lines) < n_lines:
            fb = _fallback(menu_name, store_name, tone, n_lines, price, location, benefit, cta).caption_lines
            lines += fb[len(lines):n_lines]

        lines = [_cap_len(_normalize_line(x), 16) for x in lines]

        promo = str(promo).strip()
        if not promo:
            promo = _fallback(menu_name, store_name, tone, n_lines, price, location, benefit, cta).promo_text

        if not isinstance(tags, list) or len(tags) < 3:
            tags = _hashtags(menu_name, store_name, location)
        else:
            out = []
            seen = set()
            for t in tags:
                t = str(t).strip()
                if not t:
                    continue
                if not t.startswith("#"):
                    t = "#" + t.replace(" ", "")
                if t not in seen:
                    out.append(t)
                    seen.add(t)
                if len(out) >= 12:
                    break
            tags = out or _hashtags(menu_name, store_name, location)

        return LLMOutput(lines, promo, tags)

    except Exception as e:
        logger.warning("LLM 호출 실패/파싱 실패. fallback으로 대체합니다. err=%s", e)
        return _fallback(
            menu_name=menu_name,
            store_name=store_name,
            tone=tone,
            n_lines=n_lines,
            price=price,
            location=location,
            benefit=benefit,
            cta=cta,
        )
