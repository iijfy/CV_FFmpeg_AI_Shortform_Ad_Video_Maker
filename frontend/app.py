import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="🍜 AI 유튜브 숏폼 광고영상 제작 프로그램", layout="centered")

st.title("🍜 AI 유튜브 숏폼 광고 영상 프로그램")
st.caption("✅ 사진은 10~15장 권장(가로/세로 섞여도 OK)")

images = st.file_uploader(
    "가게/음식 사진 업로드 (여러 장 가능)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True
)

col1, col2 = st.columns(2)
with col1:
    store_name = st.text_input("가게 이름", value="")
    menu_name = st.text_input("메뉴 이름", value="")
    tone = st.selectbox("광고 톤", ["힙", "감성", "고급", "가성비"], index=0)

with col2:
    price = st.text_input("가격 예: 9,900원", value="")
    location = st.text_input("위치 예: 망원동/홍대입구", value="")
    benefit = st.text_input("혜택 예: 오픈이벤트/1+1/사이드 증정", value="")
    cta = st.text_input("방문/주문 유도 문구 예: 네이버예약 ㄱㄱ?", value="")

make_btn = st.button("🎬 영상 만들기", type="primary")

if make_btn:
    if not images:
        st.error("이미지를 1장 이상 올려주세요.")
        st.stop()
    if not menu_name.strip():
        st.error("메뉴 이름은 필수입니다.")
        st.stop()

    files = []
    for img in images:
        files.append(("images", (img.name, img.getvalue(), img.type)))

    data = {
        "menu_name": menu_name.strip(),
        "store_name": store_name.strip() or "",
        "tone": tone,
        "price": price.strip() or "",
        "location": location.strip() or "",
        "benefit": benefit.strip() or "",
        "cta": cta.strip() or "",
    }

    with st.spinner("영상 생성 중... (수 초~수십 초)"):
        try:
            r = requests.post(f"{API_BASE}/api/generate", files=files, data=data, timeout=600)
            r.raise_for_status()
            out = r.json()
        except Exception as e:
            st.error(f"요청 실패: {e}")
            st.stop()

    st.success("완료!")
    st.write("**생성 문구(내레이션/자막 동일):**")
    st.text(out.get("caption_text", ""))

    st.write("**해시태그:**", " ".join(out.get("hashtags", [])))

    video_url = out.get("video_url")
    if video_url:
        st.video(f"{API_BASE}{video_url}")
        st.markdown(f"[결과 영상 열기]({API_BASE}{video_url})")
