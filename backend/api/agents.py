# backend/api/agents.py
from fastapi import APIRouter, HTTPException

from backend.models.schemas import AgentTaskRequest, AgentTaskResponse
from backend.core_logic.agentic_notes import get_agentic_notes_agent
from backend.vector_store.chroma_manager import ChromaManager

router = APIRouter(prefix="/agents", tags=["agents"])

chroma_manager = ChromaManager()


@router.post("/task", response_model=AgentTaskResponse)
async def execute_agent_task(request: AgentTaskRequest):
    """Execute an Agentic Notes task.

    Args:
        request: Task request with type (summarize/compare/outline),
                 document IDs, and parameters

    Returns:
        Task result with generated content
    """
    try:
        agent = get_agentic_notes_agent(chroma_manager)
        result = agent.execute(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent task failed: {str(e)}")
