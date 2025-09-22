"""
Issue Classification Service.

Provides intelligent classification of Kubernetes issues into severity levels,
categories, and priority assignments based on SLA requirements.
"""

from __future__ import annotations

import re
from typing import Any, Dict

import structlog

from ..models.issue_classification import (
    IssueSeverity,
    IssueCategory, 
    IssuePriority,
    SLATier,
    IssueClassification,
    EscalationRule,
    ClassifiedIssue,
)

logger = structlog.get_logger()


class IssueClassifierService:
    """Service for classifying and prioritizing Kubernetes issues."""
    
    def __init__(self):
        """Initialize the classifier with default rules."""
        self.escalation_rules = self._create_default_escalation_rules()
        self.severity_patterns = self._create_severity_patterns()
        self.category_patterns = self._create_category_patterns()
    
    def classify_issue(
        self, 
        issue: Dict[str, Any], 
        namespace: str = "", 
        resource_kind: str = "",
        sla_tier: SLATier = SLATier.TIER2
    ) -> ClassifiedIssue:
        """
        Classify an issue with severity, category, and priority.
        
        Args:
            issue: Issue data with 'type', 'message', 'evidence'
            namespace: Kubernetes namespace
            resource_kind: Type of K8s resource
            sla_tier: Service SLA tier for priority calculation
            
        Returns:
            Classified issue with complete metadata
        """
        logger.info("Classifying issue", 
                   issue_type=issue.get('type'), 
                   namespace=namespace,
                   resource_kind=resource_kind)
        
        # Extract basic issue info
        issue_type = issue.get('type', 'unknown')
        message = issue.get('message', '')
        evidence = issue.get('evidence', {})
        
        # Classify severity
        severity = self._classify_severity(issue_type, message, evidence)
        
        # Classify category  
        category = self._classify_category(issue_type, message, resource_kind)
        
        # Calculate priority based on severity and SLA tier
        priority = self._calculate_priority(severity, category, sla_tier)
        
        # Create classification
        classification = IssueClassification(
            severity=severity,
            category=category,
            priority=priority,
            sla_tier=sla_tier,
            confidence=self._calculate_confidence(severity, category),
            reasoning=self._generate_reasoning(severity, category, priority)
        )
        
        return ClassifiedIssue(
            issue_id=f"{namespace}-{resource_kind}-{hash(message) % 10000}",
            message=message,
            issue_type=issue_type,
            evidence=evidence,
            classification=classification,
            namespace=namespace,
            resource_name=issue.get('resource_name', ''),
            resource_kind=resource_kind,
        )
    
    def _classify_severity(self, issue_type: str, message: str, evidence: Dict[str, Any]) -> IssueSeverity:
        """Classify issue severity based on type, message, and evidence."""
        
        message_lower = message.lower()
        
        # Critical severity patterns
        critical_patterns = [
            'outofmemory', 'oomkilled', 'crashloopbackoff', 
            'imagepullbackoff', 'failedmount', 'node.*not.*ready',
            'cluster.*down', 'etcd.*failed', 'api.*server.*down'
        ]
        
        # High severity patterns
        high_patterns = [
            'failed.*scheduling', 'insufficient.*resources', 'pod.*evicted',
            'unhealthy.*container', 'probe.*failed', 'restart.*limit'
        ]
        
        # Check critical patterns
        for pattern in critical_patterns:
            if re.search(pattern, message_lower) or re.search(pattern, issue_type.lower()):
                return IssueSeverity.CRITICAL
        
        # Check high patterns        
        for pattern in high_patterns:
            if re.search(pattern, message_lower) or re.search(pattern, issue_type.lower()):
                return IssueSeverity.HIGH
                
        # Check specific issue types
        if issue_type in ['storage_issue', 'pod_not_running']:
            return IssueSeverity.HIGH
        elif issue_type in ['pod_restarts', 'general_failure']:
            return IssueSeverity.MEDIUM
            
        # Check restart count in evidence
        if isinstance(evidence, dict) and evidence.get('restarts', 0) > 5:
            return IssueSeverity.HIGH
        elif isinstance(evidence, dict) and evidence.get('restarts', 0) > 0:
            return IssueSeverity.MEDIUM
            
        return IssueSeverity.LOW
    
    def _classify_category(self, issue_type: str, message: str, resource_kind: str) -> IssueCategory:
        """Classify issue category based on patterns and resource type."""
        
        message_lower = message.lower()
        
        # Network category patterns
        network_patterns = [
            'dns', 'connection.*refused', 'network.*unavailable', 
            'ingress', 'loadbalancer', 'service.*unreachable'
        ]
        
        # Security category patterns
        security_patterns = [
            'rbac', 'unauthorized', 'forbidden', 'authentication',
            'security.*context', 'privilege.*escalation'
        ]
        
        # Infrastructure category patterns
        infrastructure_patterns = [
            'node', 'storage', 'volume', 'disk', 'memory', 'cpu',
            'hardware', 'failedmount', 'insufficient.*resources'
        ]
        
        # Check category patterns
        for pattern in network_patterns:
            if re.search(pattern, message_lower):
                return IssueCategory.NETWORK
                
        for pattern in security_patterns:
            if re.search(pattern, message_lower):
                return IssueCategory.SECURITY
                
        for pattern in infrastructure_patterns:
            if re.search(pattern, message_lower):
                return IssueCategory.INFRASTRUCTURE
        
        # Resource-based classification
        infrastructure_resources = {'Node', 'PersistentVolume', 'StorageClass'}
        network_resources = {'Service', 'Ingress', 'NetworkPolicy'}
        
        if resource_kind in infrastructure_resources:
            return IssueCategory.INFRASTRUCTURE
        elif resource_kind in network_resources:
            return IssueCategory.NETWORK
            
        # Default to application for pods and other app resources
        return IssueCategory.APPLICATION
    
    def _calculate_priority(self, severity: IssueSeverity, category: IssueCategory, sla_tier: SLATier) -> IssuePriority:
        """Calculate priority based on severity, category, and SLA tier."""
        
        # Priority matrix: severity + SLA tier
        priority_matrix = {
            (IssueSeverity.CRITICAL, SLATier.TIER1): IssuePriority.P0,
            (IssueSeverity.CRITICAL, SLATier.TIER2): IssuePriority.P0,
            (IssueSeverity.CRITICAL, SLATier.TIER3): IssuePriority.P1,
            
            (IssueSeverity.HIGH, SLATier.TIER1): IssuePriority.P0,
            (IssueSeverity.HIGH, SLATier.TIER2): IssuePriority.P1,
            (IssueSeverity.HIGH, SLATier.TIER3): IssuePriority.P2,
            
            (IssueSeverity.MEDIUM, SLATier.TIER1): IssuePriority.P1,
            (IssueSeverity.MEDIUM, SLATier.TIER2): IssuePriority.P2,
            (IssueSeverity.MEDIUM, SLATier.TIER3): IssuePriority.P3,
            
            (IssueSeverity.LOW, SLATier.TIER1): IssuePriority.P2,
            (IssueSeverity.LOW, SLATier.TIER2): IssuePriority.P3,
            (IssueSeverity.LOW, SLATier.TIER3): IssuePriority.P3,
        }
        
        base_priority = priority_matrix.get((severity, sla_tier), IssuePriority.P3)
        
        # Escalate security issues by one level
        if category == IssueCategory.SECURITY and base_priority != IssuePriority.P0:
            priority_escalation = {
                IssuePriority.P3: IssuePriority.P2,
                IssuePriority.P2: IssuePriority.P1, 
                IssuePriority.P1: IssuePriority.P0,
            }
            return priority_escalation.get(base_priority, base_priority)
            
        return base_priority
    
    def _calculate_confidence(self, severity: IssueSeverity, category: IssueCategory) -> float:
        """Calculate confidence score for the classification."""
        
        # Base confidence based on how specific the patterns are
        confidence_map = {
            IssueSeverity.CRITICAL: 0.9,  # Critical patterns are very specific
            IssueSeverity.HIGH: 0.8,      # High patterns are quite specific
            IssueSeverity.MEDIUM: 0.6,    # Medium is more general
            IssueSeverity.LOW: 0.4,       # Low is default/fallback
        }
        
        base_confidence = confidence_map[severity]
        
        # Adjust based on category specificity
        if category in [IssueCategory.SECURITY, IssueCategory.NETWORK]:
            base_confidence += 0.1  # More specific categories
        
        return min(base_confidence, 1.0)
    
    def _generate_reasoning(self, severity: IssueSeverity, category: IssueCategory, priority: IssuePriority) -> str:
        """Generate human-readable reasoning for the classification."""
        return f"Classified as {severity.value} {category.value} issue with {priority.value} priority based on pattern matching and SLA requirements."
    
    def _create_default_escalation_rules(self) -> list[EscalationRule]:
        """Create default escalation rules."""
        return [
            EscalationRule(
                trigger_priority=IssuePriority.P0,
                trigger_age_minutes=15,
                escalation_actions=["notify_oncall", "create_incident"],
                notification_channels=["slack", "sms", "email"]
            ),
            EscalationRule(
                trigger_priority=IssuePriority.P1,
                trigger_age_minutes=60,
                escalation_actions=["notify_team_lead", "update_status_page"],
                notification_channels=["slack", "email"]
            ),
            EscalationRule(
                trigger_priority=IssuePriority.P2,
                trigger_age_minutes=240,
                escalation_actions=["notify_team", "schedule_review"],
                notification_channels=["slack"]
            ),
        ]
    
    def _create_severity_patterns(self) -> Dict[IssueSeverity, list[str]]:
        """Create severity classification patterns."""
        return {
            IssueSeverity.CRITICAL: [
                'outofmemory', 'oomkilled', 'crashloopbackoff',
                'imagepullbackoff', 'failedmount', 'node.*not.*ready'
            ],
            IssueSeverity.HIGH: [
                'failed.*scheduling', 'insufficient.*resources', 'pod.*evicted'
            ],
            IssueSeverity.MEDIUM: [
                'pod.*restart', 'container.*exit'
            ],
            IssueSeverity.LOW: [
                'config.*warning', 'deprecation'
            ]
        }
    
    def _create_category_patterns(self) -> Dict[IssueCategory, list[str]]:
        """Create category classification patterns."""
        return {
            IssueCategory.INFRASTRUCTURE: [
                'node', 'storage', 'volume', 'disk', 'memory', 'cpu'
            ],
            IssueCategory.APPLICATION: [
                'pod', 'container', 'deployment', 'application'
            ],
            IssueCategory.NETWORK: [
                'dns', 'connection', 'network', 'ingress', 'service'
            ],
            IssueCategory.SECURITY: [
                'rbac', 'unauthorized', 'forbidden', 'security'
            ]
        }