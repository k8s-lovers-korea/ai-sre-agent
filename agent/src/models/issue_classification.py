"""
Issue classification and priority models.

This module defines the 4-level severity classification system, 
issue categories, SLA-based prioritization, and escalation rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


class IssueSeverity(str, Enum):
    """4-level severity classification system."""
    
    CRITICAL = "critical"  # Service completely down, data loss risk
    HIGH = "high"         # Major functionality impacted, performance degradation
    MEDIUM = "medium"     # Minor functionality impacted, workarounds available  
    LOW = "low"          # Minimal impact, cosmetic issues


class IssueCategory(str, Enum):
    """Issue categorization for automatic tagging."""
    
    INFRASTRUCTURE = "infrastructure"  # Node, storage, networking hardware
    APPLICATION = "application"       # Pod crashes, app errors, config issues
    NETWORK = "network"              # Connectivity, DNS, ingress issues
    SECURITY = "security"            # RBAC, vulnerabilities, compliance


class IssuePriority(str, Enum):
    """Priority levels based on SLA requirements."""
    
    P0 = "p0"  # Critical - immediate response required
    P1 = "p1"  # High - response within 1 hour
    P2 = "p2"  # Medium - response within 4 hours  
    P3 = "p3"  # Low - response within 24 hours


class SLATier(str, Enum):
    """Service tier levels for SLA-based prioritization."""
    
    TIER1 = "tier1"  # Production critical services
    TIER2 = "tier2"  # Production standard services
    TIER3 = "tier3"  # Development/staging services


class IssueClassification(BaseModel):
    """Complete issue classification result."""
    
    severity: IssueSeverity
    category: IssueCategory
    priority: IssuePriority
    sla_tier: SLATier
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""
    
    def get_response_sla_minutes(self) -> int:
        """Get SLA response time in minutes based on priority."""
        sla_times = {
            IssuePriority.P0: 15,    # 15 minutes
            IssuePriority.P1: 60,    # 1 hour
            IssuePriority.P2: 240,   # 4 hours
            IssuePriority.P3: 1440,  # 24 hours
        }
        return sla_times[self.priority]
    
    def should_escalate(self, issue_age_minutes: int) -> bool:
        """Check if issue should be escalated based on age and SLA."""
        sla_minutes = self.get_response_sla_minutes()
        return issue_age_minutes >= sla_minutes


class EscalationRule(BaseModel):
    """Escalation rule definition."""
    
    trigger_priority: IssuePriority
    trigger_age_minutes: int
    escalation_actions: list[str]
    notification_channels: list[str] = ["slack", "email"]
    enabled: bool = True


class ClassifiedIssue(BaseModel):
    """Issue with complete classification and metadata."""
    
    # Original issue data
    issue_id: str
    message: str
    issue_type: str
    evidence: Dict[str, Any] = {}
    
    # Classification results
    classification: IssueClassification
    
    # Metadata
    namespace: str = ""
    resource_name: str = ""
    resource_kind: str = ""
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Escalation tracking
    escalated_at: datetime | None = None
    escalation_level: int = 0
    
    def get_age_minutes(self) -> int:
        """Get issue age in minutes."""
        return int((datetime.utcnow() - self.detected_at).total_seconds() / 60)
    
    def needs_escalation(self) -> bool:
        """Check if issue needs escalation."""
        if self.escalated_at:
            return False  # Already escalated
        return self.classification.should_escalate(self.get_age_minutes())
    
    def get_tags(self) -> list[str]:
        """Get issue tags for categorization."""
        tags = [
            self.classification.severity.value,
            self.classification.category.value,
            self.classification.priority.value,
            self.classification.sla_tier.value,
        ]
        
        if self.needs_escalation():
            tags.append("needs-escalation")
            
        return tags