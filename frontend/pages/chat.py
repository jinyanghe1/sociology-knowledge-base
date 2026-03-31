# frontend/pages/chat.py
import streamlit as st
import requests
from datetime import datetime

API_BASE_URL = "http://localhost:8000"


def show():
    st.header("💬 RAG 问答")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "reasoning_steps" not in st.session_state:
        st.session_state.reasoning_steps = []

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("对话")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and "sources" in msg:
                    if msg["sources"]:
                        with st.expander("📚 参考来源"):
                            for i, source in enumerate(msg["sources"]):
                                st.markdown(f"**来源 {i+1}** (相关度: {source['score']:.3f})")
                                st.text(source["content"][:300] + "..." if len(source["content"]) > 300 else source["content"])
                                st.divider()

    with col2:
        st.subheader("设置")
        mode = st.radio(
            "问答模式",
            ["rag", "agentic"],
            format_func=lambda x: "RAG 模式" if x == "rag" else "Agentic 思考流",
            horizontal=True
        )
        top_k = st.slider("召回数量", 1, 20, 5)

        st.divider()

        st.subheader("🔍 Agent 思考流")
        if st.session_state.reasoning_steps:
            for step in st.session_state.reasoning_steps:
                st.markdown(f"- {step}")
        else:
            st.info("运行 Agentic 模式后可查看思考步骤")

    st.divider()

    if prompt := st.chat_input("输入您的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.reasoning_steps = []

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("思考中..."):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/query/",
                    json={
                        "question": prompt,
                        "mode": mode,
                        "top_k": top_k
                    },
                    timeout=120
                )

                if response.status_code == 200:
                    result = response.json()

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": result.get("sources", [])
                    })

                    if "reasoning_steps" in result:
                        st.session_state.reasoning_steps = result["reasoning_steps"]

                    st.rerun()
                else:
                    st.error(f"查询失败: {response.text}")

            except requests.exceptions.Timeout:
                st.error("请求超时，请重试")
            except Exception as e:
                st.error(f"发生错误: {str(e)}")

    if st.session_state.messages:
        if st.button("🗑️ 清空对话"):
            st.session_state.messages = []
            st.session_state.reasoning_steps = []
            st.rerun()
