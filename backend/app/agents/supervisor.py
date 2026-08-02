"""
agents/supervisor.py — LangGraph Supervisor & Graph Builder
"""

import uuid
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.analytics import analytics_node
from app.agents.application import application_node
from app.agents.job_match import job_match_node
from app.agents.job_search import job_search_node
from app.agents.notification import notification_node, post_apply_notification_node
from app.agents.resume_analysis import resume_analysis_node
from app.agents.resume_tailor import resume_tailor_node
from app.agents.state import AgentState, create_initial_state
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ─── Routing functions (conditional edges) ───────────────────────────────────

def route_after_job_search(state: AgentState) -> Literal["resume_analysis", "analytics"]:
    if state.get("should_stop") or not state.get("raw_jobs"):
        return "analytics"
    return "resume_analysis"


def route_after_resume_analysis(state: AgentState) -> Literal["job_match", "analytics"]:
    if state.get("should_stop") or not state.get("resume_data"):
        return "analytics"
    return "job_match"


def route_after_job_match(state: AgentState) -> Literal["resume_tailor", "analytics"]:
    if state.get("should_stop") or not state.get("jobs_above_threshold"):
        return "analytics"
    return "resume_tailor"


def route_after_resume_tailor(state: AgentState) -> Literal["notification", "analytics"]:
    if state.get("should_stop"):
        return "analytics"
    return "notification"


def route_after_notification(state: AgentState) -> Literal["application", "analytics"]:
    """
    If human approval is required, the graph INTERRUPTS here.
    LangGraph's interrupt_before mechanism pauses at 'application' node
    and waits for the graph to be resumed with human_decision set.
    """
    if state.get("should_stop"):
        return "analytics"
    return "application"


def route_after_application(state: AgentState) -> Literal["post_notify", "analytics"]:
    if state.get("skip_application"):
        return "analytics"
    return "post_notify"


# ─── Graph Builder ────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("job_search", job_search_node)
    graph.add_node("resume_analysis", resume_analysis_node)
    graph.add_node("job_match", job_match_node)
    graph.add_node("resume_tailor", resume_tailor_node)
    graph.add_node("notification", notification_node)
    graph.add_node("application", application_node)
    graph.add_node("post_notify", post_apply_notification_node)
    graph.add_node("analytics", analytics_node)

    # Entry point
    graph.add_edge(START, "job_search")

    # Conditional routing
    graph.add_conditional_edges("job_search", route_after_job_search)
    graph.add_conditional_edges("resume_analysis", route_after_resume_analysis)
    graph.add_conditional_edges("job_match", route_after_job_match)
    graph.add_conditional_edges("resume_tailor", route_after_resume_tailor)
    graph.add_conditional_edges("notification", route_after_notification)
    graph.add_conditional_edges("application", route_after_application)

    # Linear tail
    graph.add_edge("post_notify", "analytics")
    graph.add_edge("analytics", END)

    return graph


def compile_graph():
    """
    Compile the graph with MemorySaver checkpointer.
    MemorySaver stores state in-process memory.
    For production, swap with PostgresSaver or RedisSaver for persistence.
    interrupt_before=["application"] pauses the graph before the application
    node fires, enabling the human approval gate.
    """
    graph = build_graph()
    checkpointer = MemorySaver()
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["application"],  # Human-in-the-loop gate
    )


# Module-level compiled graph instance
_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
        logger.info("LangGraph compiled and ready")
    return _compiled_graph


# ─── Public runner functions ──────────────────────────────────────────────────

async def run_agent_pipeline(
    user_id: str,
    resume_id: str,
    triggered_by: str = "user",
    portals: list[str] | None = None,
    categories: list[str] | None = None,
    match_threshold: float | None = None,
) -> dict:
    """
    Start a full agent pipeline run.
    Returns the run_id — use resume_pipeline(run_id, decision) to continue after approval.
    """
    run_id = str(uuid.uuid4())
    initial_state = create_initial_state(
        user_id=user_id,
        resume_id=resume_id,
        run_id=run_id,
        triggered_by=triggered_by,
        portals=portals,
        categories=categories,
        match_threshold=match_threshold,
    )

    graph = get_graph()
    config = {"configurable": {"thread_id": run_id}}

    logger.info("Pipeline started", extra={"run_id": run_id, "user_id": user_id})

    # Run until the interrupt (before application node)
    result = await graph.ainvoke(initial_state, config=config)

    return {
        "run_id": run_id,
        "status": "awaiting_approval" if result.get("awaiting_human_approval") else "complete",
        "jobs_found": result.get("jobs_found_count", 0),
        "jobs_new": result.get("jobs_new_count", 0),
        "matches": len(result.get("jobs_above_threshold", [])),
        "applications": [
            {
                "application_id": app.get("application_id"),
                "job_title": app.get("job", {}).get("title"),
                "company": app.get("job", {}).get("company"),
                "match_score": app.get("match_score"),
                "tailored_resume_path": app.get("tailored_resume_path"),
                "cover_letter_path": app.get("cover_letter_path"),
            }
            for app in result.get("applications_to_process", [])
        ],
        "summary": result.get("summary"),
        "errors": result.get("errors", []),
    }


async def resume_pipeline(run_id: str, decision: str, edit_instructions: str = "") -> dict:
    """
    Resume the pipeline after human approval/rejection.
    decision: 'approve' | 'reject'
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": run_id}}

    update = {
        "human_decision": decision,
        "human_edit_instructions": edit_instructions,
        "awaiting_human_approval": False,
    }

    logger.info("Pipeline resumed", extra={"run_id": run_id, "decision": decision})

    result = await graph.ainvoke(update, config=config)

    return {
        "run_id": run_id,
        "status": "complete",
        "applications_submitted": result.get("applications_submitted", 0),
        "summary": result.get("summary"),
        "errors": result.get("errors", []),
    }