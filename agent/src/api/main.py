"""
Main API endpoints for SRE Agent.

Provides REST API for the Kubernetes Operator to interact with the agent.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..config import get_settings
from ..workflows.sre_workflow import SREWorkflow

# Load environment variables
load_dotenv()

logger = structlog.get_logger()
settings = get_settings()

# Initialize the SRE workflow
sre_workflow = SREWorkflow()

app = FastAPI(
    title="SRE Agent API",
    description="AutoGen-based SRE Agent for Kubernetes operations",
    version="0.1.0",
)


# Request/Response Models
class DecisionRequest(BaseModel):
    """Request for agent decision."""

    event_type: str
    namespace: str
    resource_name: str
    resource_kind: str
    event_data: dict[str, Any]
    context: dict[str, Any] | None = None


class DecisionResponse(BaseModel):
    """Agent decision response."""

    decision: str  # "approve", "reject", "human_review"
    confidence: float  # 0.0 to 1.0
    recommended_actions: list[dict[str, Any]]
    reasoning: str
    correlation_id: str


class ExecutionRequest(BaseModel):
    """Request for action execution."""

    correlation_id: str
    actions: list[dict[str, Any]]
    dry_run: bool = False


class ExecutionResponse(BaseModel):
    """Action execution response."""

    correlation_id: str
    results: list[dict[str, Any]]
    success: bool
    rollback_available: bool


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/decide", response_model=DecisionResponse)
async def decide(request: DecisionRequest) -> DecisionResponse:
    """
    Main decision endpoint called by the Kubernetes Operator.

    The agent analyzes the Kubernetes event and returns a decision
    with recommended actions.
    """
    logger.info(
        "Received decision request",
        event_type=request.event_type,
        namespace=request.namespace,
        resource=request.resource_name,
    )

    try:
        # Use AutoGen workflow for multi-agent decision making
        correlation_id = f"req-{hash(str(request))}"

        result = await sre_workflow.process_incident(
            event_data=request.event_data,
            namespace=request.namespace,
            resource_name=request.resource_name,
        )

        return DecisionResponse(
            decision=result.get("decision", "human_review"),
            confidence=result.get("confidence", 0.5),
            recommended_actions=result.get("recommended_actions", []),
            reasoning=result.get("reasoning", "Multi-agent analysis completed"),
            correlation_id=correlation_id,
        )

    except Exception as e:
        logger.error("Decision processing failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/execute", response_model=ExecutionResponse)
async def execute(request: ExecutionRequest) -> ExecutionResponse:
    """
    Execute approved actions.

    Called after the operator receives approval for the recommended actions.
    """
    logger.info(
        "Received execution request",
        correlation_id=request.correlation_id,
        action_count=len(request.actions),
        dry_run=request.dry_run,
    )

    try:
        # TODO: Implement action execution with safety guards
        # 1. Validate actions against allow-list
        # 2. Apply rate limiting and idempotency
        # 3. Execute with rollback capability
        # 4. Monitor execution results

        # Placeholder response
        return ExecutionResponse(
            correlation_id=request.correlation_id,
            results=[],
            success=False,
            rollback_available=False,
        )

    except Exception as e:
        logger.error(
            "Execution failed", correlation_id=request.correlation_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        log_level=settings.api.log_level.lower(),
        log_config=None,  # Use structlog instead
    )
