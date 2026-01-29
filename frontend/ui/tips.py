def render_tips():
    import streamlit as st
    st.info(
        "✅ 사진은 2~6장, 가로/세로 섞여도 OK\n"
        "✅ 더 잘 나오게 하려면: 음식이 크게 보이는 사진 + 매장 분위기 컷을 섞어보세요\n"
        "✅ OpenAI 키가 없으면: 자막/음성은 간단한 기본 템플릿으로 동작합니다"
    )
