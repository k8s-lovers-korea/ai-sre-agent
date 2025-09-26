"""
Main SRE Workflow using AutoGen GroupChat.

This is the primary orchestrator that manages multi-agent conversations
for Kubernetes incident response and remediation.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

from agents.analysis import AnalysisAgent
from agents.metric_analyze_agent import MetricAnalyzeAgent
from configs.config import get_settings
from plugins.log_summarizer import get_log_summarizer_tools
from plugins.loki_client import get_loki_tools

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
        self.loki_tools = get_loki_tools(mock=self.settings.monitoring.loki_mock)
        self.log_summarizer_tools = get_log_summarizer_tools()
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
        all_tools = self.loki_tools + self.log_summarizer_tools

        analysis_model_client = AzureOpenAIChatCompletionClient(
            model="gpt-4o",  # or your deployed model name
            azure_deployment="gpt-4o",  # your deployment name in Azure
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            seed=42,
            temperature=0.1,
        )
        self._model_clients.append(analysis_model_client)

        # Create analysis agent
        analysis_agent = AnalysisAgent(
            name="analysis_agent",
            description="SRE analysis agent specialized in Kubernetes troubleshooting.",
            model_client=analysis_model_client,
            tools=all_tools,
        )

        # Create metric analysis agent
        metric_model_client = AzureOpenAIChatCompletionClient(
            model="gpt-4o",  # or your deployed model name
            azure_deployment="gpt-4o",  # your deployment name in Azure
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            seed=42,
            temperature=0.1,
        )
        self._model_clients.append(metric_model_client)

        metric_analyze_agent = MetricAnalyzeAgent(
            name="metric_analyze_agent",
            description="Metric analysis agent specialized in Prometheus monitoring data.",
            model_client=metric_model_client,
        )

        # Create other placeholder agents
        recommendation_model_client = AzureOpenAIChatCompletionClient(
            model="gpt-4o",  # or your deployed model name
            azure_deployment="gpt-4o",  # your deployment name in Azure
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            seed=42,
            temperature=0.1,
        )
        self._model_clients.append(recommendation_model_client)

        recommendation_agent = AssistantAgent(
            name="recommendation_agent",
            description="Suggest remediation actions based on analysis.",
            model_client=recommendation_model_client,
            tools=all_tools,
        )

        return {
            "analysis": analysis_agent,
            "metric_analyze": metric_analyze_agent,
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
            max_turns=10,
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

        Please analyze this incident comprehensively. You have access to:
        
        **Log Collection Tools (Loki):**
        - analyze_pod_errors(namespace, pod_name, time_window_minutes): 
          Get error logs for specific pods
        - get_application_logs(app_label, namespace, log_level, 
          time_window_minutes): Get application logs
        - search_logs_by_pattern(pattern, namespace, time_window_minutes): 
          Search logs by patterns
        
        **Advanced Log Analysis Tools (LLM-powered):**
        - summarize_error_logs(error_logs, incident_context, 
          time_window_minutes): AI-powered error analysis
        - summarize_application_logs(app_logs, application_name, 
          analysis_focus): Application-specific insights
        - analyze_log_patterns(log_entries, pattern_description, 
          severity_focus): Pattern analysis
        - comprehensive_log_analysis(all_logs, incident_summary, 
          affected_components): Holistic analysis
        
        **Prometheus Metric Analysis Tools:**
        The metric_analyze_agent specializes in step-by-step Prometheus 
        analysis following best practices. It will:
        
        1. Start with essential system metrics (CPU, memory, disk usage)
        2. Explore available metrics if deeper investigation is needed
        3. Query specific metrics for detailed time-series analysis
        4. Check Prometheus targets if metrics collection fails
        
        **Recommended Workflow:**
        1. First, collect relevant logs using Loki tools
        2. Then use LLM-powered analysis tools to get intelligent insights
        3. If performance issues are suspected, engage metric_analyze_agent 
           for comprehensive Prometheus analysis
        4. Combine findings for comprehensive incident analysis
        5. Provide actionable recommendations based on AI analysis
        
        The AI analysis tools will provide:
        - Root cause identification
        - Business impact assessment
        - Priority-based action plans
        - Cross-component correlation analysis
        
        Start by analyzing the incident and using the appropriate tools to 
        gather comprehensive information.
        """

        try:
            # Start the multi-agent team processing using v0.4 async pattern
            logger.info("Starting multi-agent team processing", task=initial_task)

            # Use the new v0.4 run method with CancellationToken
            cancellation_token = CancellationToken()
            task_result = await self.team.run(
                task=initial_task, cancellation_token=cancellation_token
            )

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
            last_content = getattr(last_message, "content", str(last_message))

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
                    "priority": "medium",
                }
            ]

            return {
                "decision": decision,
                "confidence": confidence,
                "recommended_actions": recommended_actions,
                # "reasoning": f"Multi-agent team analysis: {last_content[:200]}...",
                "reasoning": f"Multi-agent team analysis with AI-powered log analysis: {last_content}",
                "full_conversation": [str(msg) for msg in task_result.messages],
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
        # Close Loki tools
        try:
            await self.loki_tools.close()
        except Exception as e:
            logger.warning("Error closing Loki tools", error=str(e))
        try:
            # Log summarizer tools may not have close method if they're just functions
            if hasattr(self.log_summarizer_tools, "close"):
                await self.log_summarizer_tools.close()
        except Exception as e:
            logger.warning("Error closing log summarizer tools", error=str(e))

        logger.info("SRE Workflow closed")
