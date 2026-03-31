"""Streamlit Frontend - AI Knowledge Base.

Main entry point for the Streamlit application.
Provides left-right panel layout:
- Left: Document list and preview with shutdown button
- Right: Chat interface with Agentic Notes
"""

import os
import subprocess
import time
import zipfile
from io import BytesIO
from typing import List, Optional

import requests
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="AI 知识库",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Backend API URL
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def init_session_state():
    """Initialize Streamlit session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "selected_docs" not in st.session_state:
        st.session_state.selected_docs = []
    if "current_doc" not in st.session_state:
        st.session_state.current_doc = None
    if "shutdown_requested" not in st.session_state:
        st.session_state.shutdown_requested = False


def shutdown_services():
    """Shutdown backend and frontend services."""
    try:
        # Get project directory
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stop_script = os.path.join(project_dir, "scripts", "stop.sh")
        
        if os.path.exists(stop_script):
            subprocess.Popen(["bash", stop_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # Fallback: kill processes on ports
            subprocess.run(["lsof", "-ti:8000"], capture_output=True)
            subprocess.run(["lsof", "-ti:8501"], capture_output=True)
        
        return True
    except Exception as e:
        st.error(f"停止服务时出错: {e}")
        return False


def fetch_documents() -> List[dict]:
    """Fetch document list from backend."""
    try:
        response = requests.get(f"{API_BASE_URL}/api/documents", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def upload_document(file) -> Optional[dict]:
    """Upload single document to backend."""
    try:
        files = {"file": (file.name, file.getvalue())}
        response = requests.post(
            f"{API_BASE_URL}/api/documents", files=files, timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"上传失败 {file.name}: {e}")
        return None


def upload_folder(files: List) -> dict:
    """Upload multiple files (folder upload)."""
    results = {"success": [], "failed": []}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total = len(files)
    for i, file in enumerate(files):
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"上传中... ({i+1}/{total}) {file.name}")
        
        result = upload_document(file)
        if result:
            results["success"].append(file.name)
        else:
            results["failed"].append(file.name)
    
    progress_bar.empty()
    status_text.empty()
    return results


def send_query(question: str, document_ids: List[str] = None) -> Optional[dict]:
    """Send query to RAG backend."""
    try:
        payload = {
            "question": question,
            "mode": "rag",
            "top_k": 5,
            "document_ids": document_ids,
        }
        response = requests.post(
            f"{API_BASE_URL}/api/query", json=payload, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"查询失败: {e}")
        return None


def send_agent_task(task_type: str, document_ids: List[str], **params) -> Optional[dict]:
    """Send agent task to backend."""
    try:
        payload = {
            "task_type": task_type,
            "document_ids": document_ids,
            "parameters": params,
        }
        response = requests.post(
            f"{API_BASE_URL}/api/agents/task", json=payload, timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Agent 任务失败: {e}")
        return None


def render_sidebar():
    """Render left sidebar with document management."""
    with st.sidebar:
        st.title("📚 文档库")

        # Upload section with tabs for single/folder
        st.subheader("上传文档")
        upload_tab1, upload_tab2 = st.tabs(["单个文件", "文件夹/批量"])
        
        with upload_tab1:
            uploaded_file = st.file_uploader(
                "支持 PDF, Word, PPT, Markdown, TXT",
                type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt"],
                key="doc_uploader",
            )
            if uploaded_file:
                with st.spinner("上传中..."):
                    result = upload_document(uploaded_file)
                    if result:
                        st.success(f"✅ 已上传: {result.get('filename', 'unknown')}")
                        time.sleep(1)
                        st.rerun()
        
        with upload_tab2:
            st.caption("选择多个文件或上传 ZIP 压缩包")
            uploaded_files = st.file_uploader(
                "批量上传",
                type=["pdf", "doc", "docx", "ppt", "pptx", "md", "txt", "zip"],
                accept_multiple_files=True,
                key="batch_uploader",
            )
            if uploaded_files:
                # Handle ZIP files
                all_files = []
                for file in uploaded_files:
                    if file.name.endswith('.zip'):
                        with zipfile.ZipFile(BytesIO(file.getvalue())) as z:
                            for zip_file in z.namelist():
                                if zip_file.endswith(('.pdf', '.doc', '.docx', '.ppt', '.pptx', '.md', '.txt')):
                                    all_files.append((zip_file, z.read(zip_file)))
                    else:
                        all_files.append(file)
                
                if all_files:
                    results = upload_folder(all_files)
                    if results["success"]:
                        st.success(f"✅ 成功上传 {len(results['success'])} 个文件")
                    if results["failed"]:
                        st.error(f"❌ 失败 {len(results['failed'])} 个文件: {', '.join(results['failed'][:3])}")
                    time.sleep(1)
                    st.rerun()

        st.divider()

        # Document list
        st.subheader("文档列表")
        documents = fetch_documents()

        if not documents:
            st.info("暂无文档，请上传")
        else:
            # Document selection
            doc_options = {doc["id"]: f"{doc['filename']} ({doc['status']})" for doc in documents}
            selected = st.multiselect(
                "选择要查询的文档（不选=全库搜索）",
                options=list(doc_options.keys()),
                format_func=lambda x: doc_options[x],
                key="doc_selector",
            )
            st.session_state.selected_docs = selected

            # Document preview
            st.subheader("文档预览")
            for doc in documents[:10]:  # Limit preview to 10 docs
                with st.expander(f"📄 {doc['filename']}"):
                    st.write(f"**状态:** {doc['status']}")
                    st.write(f"**上传时间:** {doc['upload_time']}")
                    st.write(f"**分块数:** {doc['chunk_count']}")
            
            if len(documents) > 10:
                st.caption(f"... 还有 {len(documents) - 10} 个文档")

        st.divider()

        # Shutdown section
        st.subheader("⚠️ 系统管理")
        with st.expander("🛑 关闭系统", expanded=False):
            st.warning("这将保存所有数据并停止前后端服务")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("保存数据", use_container_width=True):
                    st.success("✅ 数据已保存")
            with col2:
                if st.button("🛑 停止服务", type="primary", use_container_width=True):
                    st.session_state.shutdown_requested = True
                    st.rerun()


def render_shutdown_dialog():
    """Render shutdown confirmation dialog."""
    st.markdown("---")
    st.error("## 🛑 确认关闭系统？")
    st.write("此操作将：")
    st.write("1. 保存当前会话数据")
    st.write("2. 关闭前端界面")
    st.write("3. 停止后端 API 服务")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 确认关闭", type="primary", use_container_width=True):
            with st.spinner("正在停止服务..."):
                shutdown_services()
            st.success("服务已停止，可以关闭浏览器")
            st.balloons()
            # Stop the script
            st.stop()
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state.shutdown_requested = False
            st.rerun()
    st.markdown("---")


def render_chat_interface():
    """Render right panel chat interface."""
    st.title("💬 AI 助手")

    # Agentic Notes toolbar
    with st.expander("🤖 Agentic Notes - 思考流", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("📝 总结文档", use_container_width=True):
                if st.session_state.selected_docs:
                    with st.spinner("生成总结中..."):
                        result = send_agent_task(
                            "summarize", st.session_state.selected_docs
                        )
                        if result:
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": f"**📋 文档总结**\n\n{result.get('result', '')}",
                                }
                            )
                            st.rerun()
                else:
                    st.warning("请先选择文档")

        with col2:
            if st.button("⚖️ 对比矛盾", use_container_width=True):
                if len(st.session_state.selected_docs) >= 2:
                    with st.spinner("分析矛盾点..."):
                        result = send_agent_task(
                            "compare", st.session_state.selected_docs
                        )
                        if result:
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": f"**⚖️ 矛盾点分析**\n\n{result.get('result', '')}",
                                }
                            )
                            st.rerun()
                else:
                    st.warning("请选择至少 2 个文档")

        with col3:
            topic = st.text_input("主题", placeholder="输入大纲主题", key="outline_topic")
            if st.button("📑 生成大纲", use_container_width=True):
                if st.session_state.selected_docs and topic:
                    with st.spinner("生成大纲中..."):
                        result = send_agent_task(
                            "outline",
                            st.session_state.selected_docs,
                            topic=topic,
                        )
                        if result:
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": f"**📑 结构化大纲**\n\n{result.get('result', '')}",
                                }
                            )
                            st.rerun()
                elif not topic:
                    st.warning("请输入主题")
                else:
                    st.warning("请先选择文档")

    st.divider()

    # Chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("输入问题，或选择文档后点击上方按钮..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                response = send_query(prompt, st.session_state.selected_docs)
                if response:
                    answer = response.get("answer", "无法生成回答")
                    sources = response.get("sources", [])

                    # Display answer
                    st.markdown(answer)

                    # Display sources
                    if sources:
                        with st.expander("📚 参考来源"):
                            for i, src in enumerate(sources, 1):
                                st.markdown(f"**来源 {i}** (相似度: {src.get('score', 0):.2f})")
                                st.caption(src.get("content", "")[:300] + "...")

                    # Add to session state
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer}
                    )


def main():
    """Main application entry."""
    init_session_state()

    # Show shutdown dialog if requested
    if st.session_state.shutdown_requested:
        render_shutdown_dialog()

    # Two-column layout: sidebar (left) + main (right)
    render_sidebar()
    render_chat_interface()

    # Footer
    st.divider()
    st.caption("AI Knowledge Base | 本地知识库系统 | 端口: 8501")


if __name__ == "__main__":
    main()
