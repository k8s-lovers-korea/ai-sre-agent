"""
Main SRE Workflow using AutoGen GroupChat.

This is the primary orchestrator that manages multi-agent conversations
for Kubernetes incident response and remediation.
"""

from __future__ import annotations

import asyncio
from typing import Any
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_core import CancellationToken
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from ..agents.analysis import AnalysisAgent
from ..config import get_settings

logger = structlog.get_logger()


class SREWorkflow:
    """
    Main SRE workflow orchestrator using AutoGen 0.7.4+ Team structure.

    This class manages the multi-agent conversation flow:
    1. Analysis Agent diagnoses the issue
    2. Recommendation Agent suggests actions
    3. Guard Agent validates safety
    4. Approval Agent makes final decision
    5. Execution Agent implements approved actions
    """

    def __init__(self):
        self.settings = get_settings()
        self._model_clients = []  # Track model clients for cleanup
        self.agents = self._create_agents()
        self.team = self._create_team()

    def _create_agents(self) -> dict[str, AssistantAgent]:
        """Create all agents for the workflow."""

        # Create Azure OpenAI model clients for v0.4
        # Use environment variables for Azure OpenAI configuration
        azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        if not azure_api_key or not azure_endpoint:
            raise ValueError(
                "Azure OpenAI configuration missing. Please set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT environment variables."
            )

        analysis_model_client = AzureOpenAIChatCompletionClient(
            model="gpt-4o",  # or your deployed model name
            azure_deployment="gpt-4o",  # your deployment name in Azure
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            seed=42,
            temperature=0.1
        )
        self._model_clients.append(analysis_model_client)

        # Create analysis agent
        analysis_agent = AnalysisAgent(
            name="analysis_agent",
            description="SRE analysis agent specialized in Kubernetes troubleshooting.",
            model_client=analysis_model_client
        )

        # Create other placeholder agents
        recommendation_model_client = AzureOpenAIChatCompletionClient(
            model="gpt-4o",  # or your deployed model name
            azure_deployment="gpt-4o",  # your deployment name in Azure
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            seed=42,
            temperature=0.1
        )
        self._model_clients.append(recommendation_model_client)

        recommendation_agent = AssistantAgent(
            name="recommendation_agent",
            description="Suggest remediation actions based on analysis.",
            model_client=recommendation_model_client
        )

        return {
            "analysis": analysis_agent,
            "recommendation": recommendation_agent,
        }

    def _create_team(self) -> RoundRobinGroupChat:
        """Create the multi-agent team."""
        # Create termination conditions for v0.4
        max_messages_termination = MaxMessageTermination(max_messages=20)
        text_termination = TextMentionTermination("TERMINATE")
        termination = max_messages_termination | text_termination

        return RoundRobinGroupChat(
            participants=list(self.agents.values()),
            termination_condition=termination,
            max_turns=10
        )

    async def process_incident(
        self, event_data: dict[str, Any], namespace: str, resource_name: str
    ) -> dict[str, Any]:
        """
        Process a Kubernetes incident using multi-agent workflow.

        Args:
            event_data: Kubernetes event data
            namespace: K8s namespace
            resource_name: Resource name

        Returns:
            Decision result with recommended actions
        """
        logger.info(
            "Starting SRE workflow", namespace=namespace, resource=resource_name
        )

        # Initial task to start the team conversation
        initial_task = f"""
        Kubernetes Incident Detected:

        Namespace: {namespace}
        Resource: {resource_name}
        Event Data: {event_data}

        Please analyze this incident and recommend appropriate actions.
        """

        try:
            # Start the multi-agent team processing using v0.4 async pattern
            logger.info("Starting multi-agent team processing", task=initial_task)

            # Use the new v0.4 run method with CancellationToken
            cancellation_token = CancellationToken()
            task_result = await self.team.run(task=initial_task, cancellation_token=cancellation_token)

            # Extract decision from TaskResult
            result = self._extract_decision(task_result)

            logger.info("Team processing completed", result=result)
            return result

        except Exception as e:
            logger.error("Workflow processing failed", error=str(e))
            return {
                "decision": "error",
                "confidence": 0.0,
                "recommended_actions": [],
                "reasoning": f"Workflow failed: {str(e)}",
            }

    def _extract_decision(self, task_result: TaskResult) -> dict[str, Any]:
        """Extract final decision from task result using v0.4 TaskResult structure."""

        try:
            # In v0.4, TaskResult contains messages with the conversation history
            if not task_result.messages:
                return {
                    "decision": "error",
                    "confidence": 0.0,
                    "recommended_actions": [],
                    "reasoning": "No messages in task result",
                }

            # Get the last message from the conversation
            last_message = task_result.messages[-1]
            last_content = getattr(last_message, 'content', str(last_message))

            # Simple heuristic to extract decision based on content
            # In production, this could use structured parsing or another LLM
            if "TERMINATE" in last_content or "approve" in last_content.lower():
                decision = "approve"
                confidence = 0.8
            elif "reject" in last_content.lower() or "error" in last_content.lower():
                decision = "reject"
                confidence = 0.7
            else:
                decision = "human_review"
                confidence = 0.5

            # Extract basic actions (this could be more sophisticated)
            recommended_actions = [
                {
                    "action": "review_team_analysis",
                    "description": "Review the multi-agent team analysis",
                    "priority": "medium"
                }
            ]

            return {
                "decision": decision,
                "confidence": confidence,
                "recommended_actions": recommended_actions,
                "reasoning": f"Multi-agent team analysis: {last_content[:200]}...",
                "full_conversation": [str(msg) for msg in task_result.messages]
            }

        except Exception as e:
            logger.error("Error extracting decision from TaskResult", error=str(e))
            return {
                "decision": "error",
                "confidence": 0.0,
                "recommended_actions": [],
                "reasoning": f"Error parsing task result: {str(e)}",
            }

    async def close(self) -> None:
        """Close all model clients properly."""
        for client in self._model_clients:
            try:
                await client.close()
            except Exception as e:
                logger.warning("Error closing model client", error=str(e))
