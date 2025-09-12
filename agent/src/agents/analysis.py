"""
Analysis Agent

Diagnoses Kubernetes issues using LLM reasoning and observability data.
"""

from __future__ import annotations

from typing import Any
import structlog

from autogen import ConversableAgent

from ..tools.kubernetes import KubernetesTools

logger = structlog.get_logger()


class AnalysisAgent(ConversableAgent):
    """
    Kubernetes issue analysis agent using AutoGen 0.7.4+ patterns.

    Capabilities:
    - Analyze K8s events and resource states
    - Parse logs and metrics for anomalies
    - Correlate symptoms to root causes
    - Generate structured problem reports
    """

    def __init__(
        self, name: str = "analysis_agent", system_message: str | None = None, **kwargs
    ):
        if system_message is None:
            system_message = self._get_default_system_message()

        super().__init__(name=name, system_message=system_message, **kwargs)

        # Initialize Kubernetes tools
        self.k8s_tools = KubernetesTools()

        # Register AutoGen function calling tools
        self.register_for_llm(name="get_pod_status")(self.k8s_tools.get_pod_status)
        self.register_for_llm(name="get_recent_events")(
            self.k8s_tools.get_recent_events
        )
        self.register_for_llm(name="analyze_symptoms")(self._analyze_symptoms)

        # Register for execution
        self.register_for_execution(name="get_pod_status")(
            self.k8s_tools.get_pod_status
        )
        self.register_for_execution(name="get_recent_events")(
            self.k8s_tools.get_recent_events
        )
        self.register_for_execution(name="analyze_symptoms")(self._analyze_symptoms)

    def _get_default_system_message(self) -> str:
        return """You are a Kubernetes SRE Analysis Agent. Your role is to:

1. **Analyze** Kubernetes events, logs, and metrics to identify issues
2. **Correlate** symptoms to determine root causes
3. **Provide** structured analysis with evidence and confidence levels
4. **Prioritize** issues by severity and business impact

Guidelines:
- Always provide evidence for your analysis
- Include confidence levels (High/Medium/Low)
- Consider cascading effects and dependencies
- Focus on actionable insights

Available tools:
- analyze_k8s_events: Parse Kubernetes events for issues
- analyze_pod_status: Check pod health and status
- analyze_resource_usage: Examine resource consumption patterns"""

    async def _analyze_symptoms(
        self,
        events: list[dict[str, Any]],
        pod_status: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Analyze symptoms to identify root causes.

        Args:
            events: List of Kubernetes events
            pod_status: Pod status information
            context: Additional context data

        Returns:
            Analysis results with diagnosis and confidence
        """
        logger.info("Analyzing symptoms", event_count=len(events), context=context)

        # Pattern matching for common issues
        issues = []
        confidence = "low"

        # Check for common failure patterns
        if events:
            for event in events:
                if event.get("type") == "Warning":
                    reason = event.get("reason", "")

                    if "FailedMount" in reason:
                        issues.append(
                            {
                                "type": "storage_issue",
                                "severity": "high",
                                "message": "Volume mount failure detected",
                                "evidence": event,
                            }
                        )
                        confidence = "high"

                    elif "Failed" in reason or "Error" in reason:
                        issues.append(
                            {
                                "type": "general_failure",
                                "severity": "medium",
                                "message": f"Failure detected: {reason}",
                                "evidence": event,
                            }
                        )
                        confidence = "medium"

        # Check pod status issues
        if pod_status and "pods" in pod_status:
            for pod in pod_status["pods"]:
                if pod.get("phase") != "Running":
                    issues.append(
                        {
                            "type": "pod_not_running",
                            "severity": "high",
                            "message": f"Pod {pod.get('name')} is in {pod.get('phase')} state",
                            "evidence": pod,
                        }
                    )
                    confidence = "high"

                if pod.get("restarts", 0) > 0:
                    issues.append(
                        {
                            "type": "pod_restarts",
                            "severity": "medium",
                            "message": f"Pod {pod.get('name')} has {pod.get('restarts')} restarts",
                            "evidence": pod,
                        }
                    )

        return {
            "issues_found": len(issues),
            "issues": issues,
            "confidence": confidence,
            "analysis_summary": self._generate_summary(issues),
            "recommended_next_steps": self._get_next_steps(issues),
        }

    def _generate_summary(self, issues: list[dict[str, Any]]) -> str:
        """Generate a human-readable summary of issues."""
        if not issues:
            return "No significant issues detected in the analysis."

        high_severity = [i for i in issues if i.get("severity") == "high"]
        medium_severity = [i for i in issues if i.get("severity") == "medium"]

        summary = f"Found {len(issues)} issue(s): "

        if high_severity:
            summary += f"{len(high_severity)} high-severity, "
        if medium_severity:
            summary += f"{len(medium_severity)} medium-severity"

        summary = summary.rstrip(", ")

        # Add top issue details
        if issues:
            top_issue = issues[0]
            summary += f". Primary concern: {top_issue.get('message')}"

        return summary

    def _get_next_steps(self, issues: list[dict[str, Any]]) -> list[str]:
        """Get recommended next steps based on issues."""
        if not issues:
            return ["Continue monitoring", "No immediate action required"]

        steps = []
        issue_types = {issue.get("type") for issue in issues}

        if "storage_issue" in issue_types:
            steps.extend(
                [
                    "Check PVC status and storage class",
                    "Verify storage node availability",
                    "Review storage provisioner logs",
                ]
            )

        if "pod_not_running" in issue_types:
            steps.extend(
                [
                    "Check pod events and logs",
                    "Verify resource limits and requests",
                    "Check node capacity and scheduling",
                ]
            )

        if "pod_restarts" in issue_types:
            steps.extend(
                [
                    "Examine container logs for crash reasons",
                    "Check resource limits",
                    "Review health check configurations",
                ]
            )

        # Add generic steps if no specific patterns
        if not steps:
            steps.extend(
                [
                    "Review recent changes and deployments",
                    "Check application logs",
                    "Monitor resource usage trends",
                ]
            )

        return steps[:5]  # Limit to 5 steps
