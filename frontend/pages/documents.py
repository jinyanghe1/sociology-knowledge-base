# frontend/pages/documents.py
import streamlit as st
import requests
import time

API_BASE_URL = "http://localhost:8000"


def show():
    st.header("📁 文档管理")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("上传文档")
        uploaded_file = st.file_uploader(
            "选择文件",
            type=["pdf", "doc", "docx", "ppt", "pptx", "md", "markdown", "txt"],
            help="支持 PDF、Word、PPT、Markdown 和文本文件"
        )

        if uploaded_file:
            if st.button("上传并处理", type="primary"):
                with st.spinner("上传中..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    response = requests.post(
                        f"{API_BASE_URL}/api/documents",
                        files=files
                    )

                    if response.status_code == 200:
                        doc = response.json()
                        st.success(f"✅ 上传成功: {doc['filename']}")

                        with st.spinner("处理文档中..."):
                            process_response = requests.post(
                                f"{API_BASE_URL}/documents/{doc['id']}/process"
                            )

                            if process_response.status_code == 200:
                                st.success("✅ 文档处理完成")
                                st.rerun()
                            else:
                                st.error(f"处理失败: {process_response.text}")
                    else:
                        st.error(f"上传失败: {response.text}")

    with col2:
        st.subheader("文档列表")
        response = requests.get(f"{API_BASE_URL}/api/documents")

        if response.status_code == 200:
            documents = response.json()

            if not documents:
                st.info("暂无文档，请上传文档开始使用")
            else:
                for doc in documents:
                    status_emoji = {
                        "pending": "⏳",
                        "processing": "🔄",
                        "ready": "✅",
                        "error": "❌"
                    }.get(doc["status"], "❓")

                    with st.container():
                        col_a, col_b, col_c = st.columns([3, 1, 1])

                        with col_a:
                            st.markdown(f"**{status_emoji} {doc['filename']}**")
                            st.caption(f"类型: {doc['file_type']} | 块数: {doc['chunk_count']}")

                        with col_b:
                            st.markdown(f"状态: `{doc['status']}`")

                        with col_c:
                            if st.button("🗑️", key=f"del_{doc['id']}"):
                                del_response = requests.delete(
                                    f"{API_BASE_URL}/api/documents/{doc['id']}"
                                )
                                if del_response.status_code == 200:
                                    st.success("已删除")
                                    st.rerun()
                                else:
                                    st.error("删除失败")

                        st.divider()
        else:
            st.error("获取文档列表失败")
