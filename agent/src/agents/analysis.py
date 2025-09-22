"""
Analysis Agent

Diagnoses Kubernetes issues using LLM reasoning and observability data.
"""

from __future__ import annotations

from typing import Any
import structlog

from autogen_agentchat.agents import AssistantAgent

from ..tools.kubernetes import KubernetesTools
from ..services.issue_classifier import IssueClassifierService
from ..models.issue_classification import SLATier, ClassifiedIssue

logger = structlog.get_logger()


class AnalysisAgent(AssistantAgent):
    """
    Kubernetes issue analysis agent using AutoGen 0.7.4+ patterns.

    Capabilities:
    - Analyze K8s events and resource states
    - Parse logs and metrics for anomalies
    - Correlate symptoms to root causes
    - Generate structured problem reports
    """

    def __init__(
        self, name: str = "analysis_agent", description: str | None = None, model_client=None, **kwargs
    ):
        if description is None:
            description = self._get_default_description()

        # Initialize Kubernetes tools and classification service
        self.k8s_tools = KubernetesTools()
        self.classifier = IssueClassifierService()

        # AutoGen 0.7.4+ requires model_client
        super().__init__(
            name=name,
            description=description,
            model_client=model_client,
            # tools=[self._get_kubernetes_tools()],  # Tools will be added later
            **kwargs
        )

    def _get_default_description(self) -> str:
        return """You are a Kubernetes SRE Analysis Agent. Your role is to:

1. **Analyze** Kubernetes events, logs, and metrics to identify issues
2. **Correlate** symptoms to determine root causes
3. **Provide** structured analysis with evidence and confidence levels
4. **Classify** issues by severity (Critical/High/Medium/Low) and category (Infrastructure/Application/Network/Security)
5. **Prioritize** issues by severity and business impact using SLA-based priority matrix

Guidelines:
- Always provide evidence for your analysis
- Include confidence levels (High/Medium/Low)
- Consider cascading effects and dependencies
- Focus on actionable insights
- Use 4-level severity classification (Critical, High, Medium, Low)
- Auto-tag issues with appropriate categories
- Calculate priorities based on SLA tiers

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
        Analyze symptoms to identify root causes with enhanced classification.

        Args:
            events: List of Kubernetes events
            pod_status: Pod status information
            context: Additional context data

        Returns:
            Analysis results with diagnosis, classification, and confidence
        """
        logger.info("Analyzing symptoms", event_count=len(events), context=context)

        # Pattern matching for common issues
        issues = []
        classified_issues = []
        confidence = "low"

        # Extract resource context
        namespace = context.get("namespace", "") if context else ""
        resource_kind = context.get("resource_kind", "") if context else ""
        sla_tier = self._determine_sla_tier(namespace, context)

        # Check for common failure patterns in events
        if events:
            for event in events:
                if event.get("type") == "Warning":
                    reason = event.get("reason", "")
                    issue_data = None

                    if "FailedMount" in reason:
                        issue_data = {
                            "type": "storage_issue",
                            "severity": "high",  # Legacy field for backward compatibility
                            "message": "Volume mount failure detected",
                            "evidence": event,
                            "resource_name": event.get("involvedObject", {}).get("name", "")
                        }
                    elif "Failed" in reason or "Error" in reason:
                        issue_data = {
                            "type": "general_failure",
                            "severity": "medium",  # Legacy field for backward compatibility
                            "message": f"Failure detected: {reason}",
                            "evidence": event,
                            "resource_name": event.get("involvedObject", {}).get("name", "")
                        }

                    if issue_data:
                        issues.append(issue_data)
                        # Classify with new system
                        classified_issue = self.classifier.classify_issue(
                            issue_data, namespace, resource_kind, sla_tier
                        )
                        classified_issues.append(classified_issue)
                        confidence = "high"

        # Check pod status issues
        if pod_status and "pods" in pod_status:
            for pod in pod_status["pods"]:
                issue_data = None

                if pod.get("phase") != "Running":
                    issue_data = {
                        "type": "pod_not_running",
                        "severity": "high",  # Legacy field
                        "message": f"Pod {pod.get('name')} is in {pod.get('phase')} state",
                        "evidence": pod,
                        "resource_name": pod.get("name", "")
                    }
                elif pod.get("restarts", 0) > 0:
                    issue_data = {
                        "type": "pod_restarts",
                        "severity": "medium",  # Legacy field
                        "message": f"Pod {pod.get('name')} has {pod.get('restarts')} restarts",
                        "evidence": pod,
                        "resource_name": pod.get("name", "")
                    }

                if issue_data:
                    issues.append(issue_data)
                    classified_issue = self.classifier.classify_issue(
                        issue_data, namespace, resource_kind, sla_tier
                    )
                    classified_issues.append(classified_issue)
                    confidence = "high"

        return {
            "issues_found": len(issues),
            "issues": issues,  # Legacy format for backward compatibility
            "classified_issues": [self._classified_issue_to_dict(ci) for ci in classified_issues],
            "confidence": confidence,
            "analysis_summary": self._generate_enhanced_summary(classified_issues),
            "recommended_next_steps": self._get_enhanced_next_steps(classified_issues),
            "escalation_required": any(ci.needs_escalation() for ci in classified_issues),
        }

    def _generate_summary(self, issues: list[dict[str, Any]]) -> str:
        """Generate a human-readable summary of issues (legacy method)."""
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
    
    def _generate_enhanced_summary(self, classified_issues: list[ClassifiedIssue]) -> str:
        """Generate enhanced summary with new 4-level classification."""
        if not classified_issues:
            return "No significant issues detected in the analysis."

        # Count by severity
        severity_counts = {}
        category_counts = {}
        priority_counts = {}
        
        for issue in classified_issues:
            severity = issue.classification.severity.value
            category = issue.classification.category.value
            priority = issue.classification.priority.value
            
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Build summary
        summary_parts = []
        
        # Severity breakdown
        if severity_counts:
            severity_desc = ", ".join([f"{count} {sev}" for sev, count in severity_counts.items()])
            summary_parts.append(f"Severity: {severity_desc}")
        
        # Category breakdown
        if category_counts:
            category_desc = ", ".join([f"{count} {cat}" for cat, count in category_counts.items()])
            summary_parts.append(f"Categories: {category_desc}")
            
        # Priority breakdown
        if priority_counts:
            priority_desc = ", ".join([f"{count} {pri}" for pri, count in priority_counts.items()])
            summary_parts.append(f"Priorities: {priority_desc}")

        summary = f"Found {len(classified_issues)} classified issue(s). " + "; ".join(summary_parts)

        # Add primary concern
        if classified_issues:
            primary_issue = classified_issues[0]
            summary += f". Primary concern: {primary_issue.message}"
            
        # Add escalation notice
        needs_escalation = [i for i in classified_issues if i.needs_escalation()]
        if needs_escalation:
            summary += f" ({len(needs_escalation)} require escalation)"

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
    
    def _get_enhanced_next_steps(self, classified_issues: list[ClassifiedIssue]) -> list[str]:
        """Get enhanced next steps based on classified issues."""
        if not classified_issues:
            return ["Continue monitoring", "No immediate action required"]

        steps = set()  # Use set to avoid duplicates
        
        # Group by category for more targeted recommendations
        categories = set(issue.classification.category for issue in classified_issues)
        priorities = set(issue.classification.priority for issue in classified_issues)
        
        # Priority-based steps
        if any(p.value in ['p0', 'p1'] for p in priorities):
            steps.add("Immediate response required - notify on-call engineer")
            steps.add("Check status page and customer communications")
            
        # Category-specific steps
        if any(cat.value == 'infrastructure' for cat in categories):
            steps.update([
                "Check node health and resource availability",
                "Verify storage and network infrastructure",
                "Review cluster-level metrics and events"
            ])
            
        if any(cat.value == 'application' for cat in categories):
            steps.update([
                "Examine application logs and container status",
                "Check resource limits and requests",
                "Review deployment and configuration changes"
            ])
            
        if any(cat.value == 'network' for cat in categories):
            steps.update([
                "Verify network connectivity and DNS resolution",
                "Check service endpoints and ingress configuration",
                "Review firewall and security group settings"
            ])
            
        if any(cat.value == 'security' for cat in categories):
            steps.update([
                "Review RBAC permissions and security contexts",
                "Check for unauthorized access attempts",
                "Verify compliance with security policies"
            ])
        
        # Escalation-specific steps
        needs_escalation = [i for i in classified_issues if i.needs_escalation()]
        if needs_escalation:
            steps.add("Execute escalation procedures for overdue issues")
            steps.add("Notify management and update incident tracking")

        # Convert back to list and limit
        return list(steps)[:7]  # Increased limit for enhanced steps
    
    def _determine_sla_tier(self, namespace: str, context: dict[str, Any] | None) -> SLATier:
        """Determine SLA tier based on namespace and context."""
        if not namespace:
            return SLATier.TIER2  # Default
            
        # Production namespaces get higher SLA
        production_indicators = ['prod', 'production', 'live', 'main']
        if any(indicator in namespace.lower() for indicator in production_indicators):
            return SLATier.TIER1
            
        # Development/staging get lower SLA
        dev_indicators = ['dev', 'development', 'staging', 'test', 'demo']
        if any(indicator in namespace.lower() for indicator in dev_indicators):
            return SLATier.TIER3
            
        # Check context for additional hints
        if context:
            if context.get('environment') == 'production':
                return SLATier.TIER1
            elif context.get('environment') in ['development', 'staging']:
                return SLATier.TIER3
                
        return SLATier.TIER2  # Default for standard services
    
    def _classified_issue_to_dict(self, classified_issue: ClassifiedIssue) -> dict[str, Any]:
        """Convert ClassifiedIssue to dictionary for serialization."""
        return {
            "issue_id": classified_issue.issue_id,
            "message": classified_issue.message,
            "issue_type": classified_issue.issue_type,
            "evidence": classified_issue.evidence,
            "severity": classified_issue.classification.severity.value,
            "category": classified_issue.classification.category.value,
            "priority": classified_issue.classification.priority.value,
            "sla_tier": classified_issue.classification.sla_tier.value,
            "confidence": classified_issue.classification.confidence,
            "reasoning": classified_issue.classification.reasoning,
            "namespace": classified_issue.namespace,
            "resource_name": classified_issue.resource_name,
            "resource_kind": classified_issue.resource_kind,
            "detected_at": classified_issue.detected_at.isoformat(),
            "age_minutes": classified_issue.get_age_minutes(),
            "needs_escalation": classified_issue.needs_escalation(),
            "tags": classified_issue.get_tags(),
        }
