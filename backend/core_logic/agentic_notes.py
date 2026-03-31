"""Agentic Notes - Multi-document Analysis Tasks.

Implements LangGraph workflows for:
- Summarize: Generate document summaries
- Compare: Find contradictions across documents  
- Outline: Generate structured outlines from sources
"""

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from backend.models.schemas import AgentTaskRequest, AgentTaskResponse, AgentTaskType
from backend.vector_store.chroma_manager import ChromaManager


class AgenticState(TypedDict):
    """State for Agentic Notes workflow."""

    messages: Annotated[list, add_messages]
    task_type: str
    document_ids: List[str]
    chunks: List[Dict[str, Any]]
    result: Optional[str]
    metadata: Dict[str, Any]


class AgenticNotesAgent:
    """LangGraph-powered agent for document analysis tasks."""

    def __init__(self, chroma_manager: Optional[ChromaManager] = None):
        """Initialize agent.

        Args:
            chroma_manager: ChromaDB manager for document retrieval
        """
        self.chroma = chroma_manager or ChromaManager()
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build LangGraph workflow."""
        workflow = StateGraph(AgenticState)

        workflow.add_node("retrieve", self._retrieve_chunks)
        workflow.add_node("analyze", self._analyze)
        workflow.add_node("summarize", self._summarize)
        workflow.add_node("compare", self._compare)
        workflow.add_node("outline", self._outline)

        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "analyze")
        workflow.add_conditional_edges(
            "analyze",
            self._route_by_task,
            {
                AgentTaskType.SUMMARIZE.value: "summarize",
                AgentTaskType.COMPARE.value: "compare",
                AgentTaskType.OUTLINE.value: "outline",
            },
        )
        workflow.add_edge("summarize", END)
        workflow.add_edge("compare", END)
        workflow.add_edge("outline", END)

        return workflow.compile()

    def _retrieve_chunks(self, state: AgenticState) -> AgenticState:
        """Retrieve chunks for specified documents."""
        import ollama

        document_ids = state["document_ids"]
        # Get all chunks for these documents
        all_chunks = []
        for doc_id in document_ids:
            results = self.chroma.get(where={"document_id": doc_id})
            if results and results.get("ids"):
                for i, chunk_id in enumerate(results["ids"]):
                    all_chunks.append({
                        "id": chunk_id,
                        "content": results["documents"][i],
                        "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                    })

        state["chunks"] = all_chunks
        state["messages"].append(
            {"role": "system", "content": f"Retrieved {len(all_chunks)} chunks from {len(document_ids)} documents"}
        )
        return state

    def _analyze(self, state: AgenticState) -> AgenticState:
        """Analyze task requirements."""
        state["messages"].append(
            {"role": "system", "content": f"Starting {state['task_type']} analysis"}
        )
        return state

    def _route_by_task(self, state: AgenticState) -> str:
        """Route to task handler."""
        return state["task_type"]

    def _summarize(self, state: AgenticState) -> AgenticState:
        """Generate summary."""
        import ollama

        chunks_text = "\n\n".join([c.get("content", "") for c in state["chunks"]])

        prompt = f"""请对以下文档内容进行简洁总结，提取核心观点和主要论据:

{chunks_text[:8000]}

请用中文输出总结，包含:
1. 主要观点
2. 关键论据
3. 结论"""

        try:
            response = ollama.generate(model="deepseek-r1:1.5b", prompt=prompt)
            result = response["response"]
        except Exception as e:
            result = f"生成总结时出错: {str(e)}"

        state["result"] = result
        state["messages"].append({"role": "assistant", "content": result})
        return state

    def _compare(self, state: AgenticState) -> AgenticState:
        """Compare documents and identify contradictions."""
        import ollama

        # Group chunks by document
        doc_chunks = {}
        for chunk in state["chunks"]:
            doc_id = chunk.get("metadata", {}).get("document_id", "unknown")
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
            doc_chunks[doc_id].append(chunk.get("content", ""))

        # Format for comparison
        comparison_text = ""
        for i, (doc_id, contents) in enumerate(doc_chunks.items(), 1):
            doc_text = "\n".join(contents)
            comparison_text += f"\n--- 文档 {i} ---\n{doc_text[:2000]}\n"

        prompt = f"""请比较以下文档内容，识别它们之间的:
1. 观点矛盾点
2. 视角差异
3. 互补内容

{comparison_text}

请用中文输出对比分析。"""

        try:
            response = ollama.generate(model="deepseek-r1:1.5b", prompt=prompt)
            result = response["response"]
        except Exception as e:
            result = f"生成对比时出错: {str(e)}"

        state["result"] = result
        state["metadata"]["contradictions"] = []
        state["messages"].append({"role": "assistant", "content": result})
        return state

    def _outline(self, state: AgenticState) -> AgenticState:
        """Generate structured outline."""
        import ollama

        chunks_text = "\n\n".join([c.get("content", "") for c in state["chunks"]])
        topic = state.get("metadata", {}).get("topic", "研究主题")

        prompt = f"""基于以下文档内容，为"{topic}"生成一份结构化大纲:

{chunks_text[:8000]}

请用中文输出层级大纲格式，包含:
1. 一级标题 (主要章节)
2. 二级标题 (子章节)
3. 每个章节的核心要点"""

        try:
            response = ollama.generate(model="deepseek-r1:1.5b", prompt=prompt)
            result = response["response"]
        except Exception as e:
            result = f"生成大纲时出错: {str(e)}"

        state["result"] = result
        state["messages"].append({"role": "assistant", "content": result})
        return state

    def execute(self, request: AgentTaskRequest) -> AgentTaskResponse:
        """Execute agent task."""
        initial_state = AgenticState(
            messages=[],
            task_type=request.task_type.value,
            document_ids=request.document_ids,
            chunks=[],
            result=None,
            metadata=request.parameters,
        )

        final_state = self.workflow.invoke(initial_state)

        return AgentTaskResponse(
            result=final_state.get("result", "No result generated"),
            metadata=final_state.get("metadata", {}),
        )


# Singleton instance
_agentic_instance: Optional[AgenticNotesAgent] = None


def get_agentic_notes_agent(chroma_manager: Optional[ChromaManager] = None) -> AgenticNotesAgent:
    """Get singleton agentic notes agent."""
    global _agentic_instance
    if _agentic_instance is None:
        _agentic_instance = AgenticNotesAgent(chroma_manager)
    return _agentic_instance
