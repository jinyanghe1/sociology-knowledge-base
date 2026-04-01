# backend/core_logic/agent.py
"""RAG Agent workflow with LangGraph (optional) fallback."""

from typing import TypedDict, Sequence, Optional

from backend.core_logic.embedding import get_embedding, generate_text
from backend.vector_store.chroma_manager import ChromaManager
from backend.models.schemas import Source

try:
    from langgraph.graph import StateGraph, END
    from langchain_core.messages import HumanMessage, AIMessage
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


class AgentState(TypedDict):
    messages: list
    question: str
    context: list
    answer: str
    reasoning_steps: list


chroma_manager = ChromaManager()


def retrieve_context(state: AgentState) -> AgentState:
    question = state["question"]
    embedding = get_embedding(question)

    results = chroma_manager.query(
        query_embedding=embedding,
        n_results=10
    )

    sources = []
    if results["ids"] and len(results["ids"]) > 0:
        for i, chunk_id in enumerate(results["ids"][0]):
            sources.append(Source(
                chunk_id=chunk_id,
                document_id=results["metadatas"][0][i].get("document_id", ""),
                content=results["documents"][0][i],
                score=results["distances"][0][i] if "distances" in results else 0.0
            ))

    state["context"] = sources
    state["reasoning_steps"].append(f"Retrieved {len(sources)} relevant chunks")
    return state


def analyze_task(state: AgentState) -> AgentState:
    question = state["question"]
    prompt = f"""Analyze this question and break it down into steps:

Question: {question}

Determine:
1. What is the user asking for?
2. What information do we need?
3. Should this be a simple RAG response or a multi-step analysis?

Respond with either "SIMPLE_RAG" or "MULTI_STEP" followed by your reasoning."""

    analysis = generate_text(prompt)
    state["reasoning_steps"].append(f"Task analysis: {analysis[:100]}...")
    return state


def generate_simple_response(state: AgentState) -> AgentState:
    question = state["question"]
    context_chunks = state["context"]

    if not context_chunks:
        state["answer"] = "No relevant documents found to answer your question."
        return state

    context = "\n\n".join([chunk.content for chunk in context_chunks])
    prompt = f"""Based on the following context, answer the question concisely and accurately.

Context:
{context}

Question: {question}

Provide a clear, direct answer:"""

    state["answer"] = generate_text(prompt)
    state["reasoning_steps"].append("Generated simple RAG response")
    return state


def generate_structured_response(state: AgentState) -> AgentState:
    question = state["question"]
    context_chunks = state["context"]

    if not context_chunks:
        state["answer"] = "No relevant documents found to answer your question."
        return state

    context = "\n\n".join([chunk.content for chunk in context_chunks])
    prompt = f"""Based on the following context, create a structured outline or analysis.

Context:
{context}

Question: {question}

Provide a well-structured response with clear sections and reasoning:"""

    state["answer"] = generate_text(prompt)
    state["reasoning_steps"].append("Generated structured multi-step response")
    return state


def should_use_structured(state: AgentState) -> str:
    reasoning = "".join(state["reasoning_steps"])
    if "MULTI_STEP" in reasoning:
        return "structured"
    return "simple"


def _create_langgraph_workflow():
    """Build the LangGraph workflow (only when langgraph is available)."""
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve_context)
    workflow.add_node("analyze", analyze_task)
    workflow.add_node("simple_response", generate_simple_response)
    workflow.add_node("structured_response", generate_structured_response)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "analyze")

    workflow.add_conditional_edges(
        "analyze",
        should_use_structured,
        {
            "simple": "simple_response",
            "structured": "structured_response"
        }
    )

    workflow.add_edge("simple_response", END)
    workflow.add_edge("structured_response", END)

    return workflow.compile()


def _run_sequential_fallback(question: str) -> dict:
    """Sequential fallback when LangGraph is unavailable."""
    state: AgentState = {
        "messages": [],
        "question": question,
        "context": [],
        "answer": "",
        "reasoning_steps": []
    }
    state = retrieve_context(state)
    state = analyze_task(state)
    if should_use_structured(state) == "structured":
        state = generate_structured_response(state)
    else:
        state = generate_simple_response(state)
    return {
        "answer": state["answer"],
        "sources": state["context"],
        "reasoning_steps": state["reasoning_steps"]
    }


# Build workflow lazily
_agentic_workflow = None


def run_agentic_query(question: str) -> dict:
    global _agentic_workflow

    if _LANGGRAPH_AVAILABLE:
        if _agentic_workflow is None:
            _agentic_workflow = _create_langgraph_workflow()

        initial_state = {
            "messages": [],
            "question": question,
            "context": [],
            "answer": "",
            "reasoning_steps": []
        }
        final_state = _agentic_workflow.invoke(initial_state)
        return {
            "answer": final_state["answer"],
            "sources": final_state["context"],
            "reasoning_steps": final_state["reasoning_steps"]
        }

    return _run_sequential_fallback(question)
