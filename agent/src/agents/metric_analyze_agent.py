"""
Metric Analysis Agent

A specialized AutoGen agent that analyzes Prometheus metrics using the step-by-step
workflow defined in the Prometheus Tools documentation. This agent follows a
structured approach:
1. Basic system metrics collection
2. Metric name exploration
3. Detailed metric queries
4. Service status verification
"""

from __future__ import annotations

from typing import Any

import structlog
from autogen_agentchat.agents import AssistantAgent
from autogen_core.models import ChatCompletionClient

from plugins.prometheus_plugin import get_prometheus_tools_for_agent

logger = structlog.get_logger()

logger = structlog.get_logger()


class MetricAnalyzeAgent(AssistantAgent):
    """
    Kubernetes metric analysis agent using AutoGen 0.7.4+ patterns.

    This agent follows the step-by-step workflow from PROMETHEUS_TOOLS_README.md:
    1. Get essential system metrics first
    2. Explore metric names if deeper analysis is needed
    3. Query specific metrics for detailed investigation
    4. Check Prometheus targets if metrics queries fail

    The agent makes intelligent decisions about when to proceed to the next step
    based on the analysis results and conversation context.
    """

    def __init__(
        self,
        name: str = "metric_analyze_agent",
        description: str | None = None,
        model_client: ChatCompletionClient | None = None,
        **kwargs,
    ):
        if model_client is None:
            raise ValueError("model_client is required for MetricAnalyzeAgent")

        if description is None:
            description = self._get_default_description()

        # Get Prometheus tools for the agent
        prometheus_tools = get_prometheus_tools_for_agent()

        # Initialize with Prometheus tools
        super().__init__(
            name=name,
            description=description,
            model_client=model_client,
            tools=prometheus_tools,
            **kwargs,
        )

        # Track analysis state for step-by-step workflow
        self._analysis_state = {
            "current_step": 1,  # Current step in the workflow
            "essential_metrics_collected": False,
            "metric_names_explored": False,
            "detailed_metrics_queried": False,
            "targets_checked": False,
            "analysis_context": {},  # Store context between steps
            "step_results": {},  # Store results from each step
        }

    def _get_default_description(self) -> str:
        return """You are a Kubernetes Metric Analysis Agent specializing in 
Prometheus monitoring data.

Your role follows a structured 4-step workflow:

**Step 1: Essential Metrics Collection**
- Always start with prometheus_get_essential_metrics()
- Get CPU, memory, disk usage percentages and system availability
- Evaluate if these basic metrics are sufficient for the analysis

**Step 2: Metric Name Exploration (if needed)**
- Use prometheus_get_metric_names() to discover available metrics
- Filter by namespace, pod name, or metric patterns
- Identify specific metrics for deeper investigation

**Step 3: Detailed Metric Queries (if needed)**
- Use prometheus_query_specific_metrics() with discovered metric names
- Analyze time-series data with appropriate time ranges and resolution
- Focus on metrics that show anomalies or issues

**Step 4: Service Status Verification (if needed)**
- Use prometheus_get_targets() if metric queries fail
- Verify Prometheus scraping health and target availability
- Report monitoring system issues

**Decision Logic:**
- Stop at Step 1 if essential metrics provide sufficient insights
- Proceed to next steps only when:
  - Basic metrics show anomalies requiring deeper investigation
  - Other agents explicitly request more detailed analysis
  - Conversation context indicates need for specific metrics

**Key Principles:**
- Be efficient - don't over-collect data
- Provide clear analysis with confidence levels
- Include evidence from metrics in your reasoning
- Suggest actionable next steps based on findings

Available Tools:
- prometheus_get_essential_metrics: Get basic system health metrics
- prometheus_get_metric_names: Discover available metrics
- prometheus_query_specific_metrics: Query detailed time-series data
- prometheus_get_targets: Check Prometheus scraping status"""

    def _should_advance_step(self, message_content: str) -> bool:
        """
        Determine if we should advance to the next step based on message content
        and current analysis state.

        Args:
            message_content: The content of the latest message

        Returns:
            True if we should advance to the next step
        """
        content_lower = message_content.lower()
        current_step = self._analysis_state["current_step"]

        # Keywords that indicate need for deeper analysis
        deeper_analysis_keywords = [
            "detailed",
            "specific metrics",
            "drill down",
            "investigate",
            "explore",
            "analyze further",
            "more data",
            "time series",
        ]

        # Keywords that indicate metric discovery is needed
        metric_discovery_keywords = [
            "what metrics",
            "available metrics",
            "metric names",
            "discover",
            "find metrics",
            "explore metrics",
        ]

        # Keywords that indicate targets check is needed
        targets_check_keywords = [
            "targets",
            "scraping",
            "prometheus health",
            "monitoring status",
            "metrics not working",
            "query failed",
        ]

        # Step 1 -> Step 2: Advance if basic metrics show issues
        # or deeper analysis requested
        if current_step == 1:
            if (
                any(keyword in content_lower for keyword in deeper_analysis_keywords)
                or any(
                    keyword in content_lower for keyword in metric_discovery_keywords
                )
                or "anomal" in content_lower
                or "issue" in content_lower
                or "problem" in content_lower
            ):
                return True

        # Step 2 -> Step 3: Advance if specific metrics identified
        elif current_step == 2:
            if (
                any(keyword in content_lower for keyword in deeper_analysis_keywords)
                or "query" in content_lower
                or "time series" in content_lower
            ):
                return True

        # Step 3 -> Step 4: Advance if queries fail or targets check requested
        elif current_step == 3:
            if (
                any(keyword in content_lower for keyword in targets_check_keywords)
                or "failed" in content_lower
                or "error" in content_lower
            ):
                return True

        return False

    def get_current_workflow_step(self) -> int:
        """Get the current step in the workflow."""
        return self._analysis_state["current_step"]

    def set_workflow_step(self, step: int) -> None:
        """Set the current workflow step (for external control)."""
        if 1 <= step <= 4:
            self._analysis_state["current_step"] = step
            logger.info("Workflow step set", step=step)
        else:
            logger.warning("Invalid workflow step", step=step)

    def get_analysis_state(self) -> dict[str, Any]:
        """Get the current analysis state."""
        return self._analysis_state.copy()

    def reset_analysis_state(self) -> None:
        """Reset the analysis state to start fresh."""
        self._analysis_state = {
            "current_step": 1,
            "essential_metrics_collected": False,
            "metric_names_explored": False,
            "detailed_metrics_queried": False,
            "targets_checked": False,
            "analysis_context": {},
            "step_results": {},
        }
        logger.info("Analysis state reset")

    def update_analysis_context(self, key: str, value: Any) -> None:
        """Update analysis context with new information."""
        self._analysis_state["analysis_context"][key] = value
        logger.debug("Analysis context updated", key=key)

    def get_workflow_guidance(self) -> str:
        """Get guidance for the current workflow step."""
        step = self._analysis_state["current_step"]

        guidance = {
            1: """**Current Step: Essential Metrics Collection**
            
Start by calling prometheus_get_essential_metrics() to get basic system health.
Parameters to consider:
- namespace: Filter by specific namespace if incident is namespace-specific
- pod_name: Filter by pod pattern if investigating specific pods
- start_time/end_time: Use if analyzing historical data
- step: Use "1m" for recent data, "5m" for longer time ranges

Evaluate if these metrics are sufficient or if deeper analysis is needed.""",
            2: """**Current Step: Metric Name Exploration**
            
Call prometheus_get_metric_names() to discover available metrics.
Parameters to consider:
- namespace: Same as essential metrics for consistency
- pod_name: Focus on problematic pods
- metric_name: Use patterns like "cpu_*", "memory_*", "network_*"
  based on Step 1 findings
- limit: Start with 500-1000 metrics

Identify specific metrics that need detailed investigation.""",
            3: """**Current Step: Detailed Metric Queries**
            
Call prometheus_query_specific_metrics() with metrics found in Step 2.
Parameters to consider:
- metric_names: Use specific metrics from Step 2 (limit to 3-5 per query)
- start_time/end_time: Focus on incident timeframe
- limit_per_metric: Use 50-100 for detailed analysis
- step: Use "30s" or "1m" for high resolution

Analyze time-series patterns and anomalies.""",
            4: """**Current Step: Service Status Verification**
            
Call prometheus_get_targets() to check Prometheus health.
Use this step when:
- Metric queries return empty results
- Connections to Prometheus fail
- Suspected monitoring system issues

Verify that Prometheus is scraping targets correctly.""",
        }

        return guidance.get(step, "Unknown step")

    def should_stop_at_current_step(self, analysis_results: dict[str, Any]) -> bool:
        """
        Determine if the current step results are sufficient to stop the workflow.

        Args:
            analysis_results: Results from the current step

        Returns:
            True if we should stop at the current step
        """
        current_step = self._analysis_state["current_step"]

        if current_step == 1:  # Essential metrics
            # Stop if metrics show normal operation
            if analysis_results.get("status") == "success":
                metrics = analysis_results.get("metrics", {})

                # Check for any concerning patterns
                concerning_patterns = [
                    "cpu_usage_percent" in str(metrics)
                    and any(
                        float(str(v).replace("%", "")) > 80
                        for v in str(metrics).split()
                        if v.replace("%", "").replace(".", "").isdigit()
                    ),
                    "memory_usage_percent" in str(metrics)
                    and any(
                        float(str(v).replace("%", "")) > 90
                        for v in str(metrics).split()
                        if v.replace("%", "").replace(".", "").isdigit()
                    ),
                    "unavailable" in str(metrics).lower(),
                    "error" in str(metrics).lower(),
                ]

                # If no concerning patterns, we can stop here
                if not any(concerning_patterns):
                    return True

        elif current_step == 2:  # Metric names
            # Stop if we found the needed metrics
            if analysis_results.get("status") == "success" and analysis_results.get(
                "metric_names"
            ):
                return True

        elif current_step == 3:  # Detailed metrics
            # Stop if we got detailed analysis
            if analysis_results.get("status") == "success":
                return True

        elif current_step == 4:  # Targets
            # Always stop after targets check
            return True

        return False
