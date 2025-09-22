"""
Tests for Issue Classification Service.
"""

import pytest
from datetime import datetime, timedelta

from src.services.issue_classifier import IssueClassifierService
from src.models.issue_classification import (
    IssueSeverity,
    IssueCategory,
    IssuePriority,
    SLATier,
)


class TestIssueClassifierService:
    """Test cases for issue classification."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.classifier = IssueClassifierService()
    
    def test_critical_severity_classification(self):
        """Test critical severity classification."""
        # Test OOMKilled event
        issue = {
            "type": "container_failure",
            "message": "Container was OOMKilled due to memory limit",
            "evidence": {"reason": "OOMKilled"}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="production", resource_kind="Pod"
        )
        
        assert classified.classification.severity == IssueSeverity.CRITICAL
        assert classified.classification.category == IssueCategory.INFRASTRUCTURE
        assert classified.classification.priority == IssuePriority.P0  # Critical + Tier1 (production)
        assert classified.classification.confidence >= 0.8
    
    def test_high_severity_classification(self):
        """Test high severity classification."""
        issue = {
            "type": "storage_issue", 
            "message": "Volume mount failure detected",
            "evidence": {"reason": "FailedMount"}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="staging", resource_kind="Pod", sla_tier=SLATier.TIER3
        )
        
        assert classified.classification.severity == IssueSeverity.HIGH
        assert classified.classification.priority == IssuePriority.P2  # High + Tier3
    
    def test_pod_restart_medium_severity(self):
        """Test pod restart medium severity."""
        issue = {
            "type": "pod_restarts",
            "message": "Pod web-app has 3 restarts",
            "evidence": {"restarts": 3, "name": "web-app"}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="default", resource_kind="Pod"
        )
        
        assert classified.classification.severity == IssueSeverity.MEDIUM
        assert classified.classification.category == IssueCategory.APPLICATION
    
    def test_network_category_classification(self):
        """Test network category classification."""
        issue = {
            "type": "connectivity_issue",
            "message": "DNS resolution failed for service endpoint",
            "evidence": {"reason": "DNS"}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="default", resource_kind="Service"
        )
        
        assert classified.classification.category == IssueCategory.NETWORK
        assert classified.classification.priority in [IssuePriority.P1, IssuePriority.P2, IssuePriority.P3]
    
    def test_security_category_escalation(self):
        """Test security category priority escalation."""
        issue = {
            "type": "auth_failure",
            "message": "RBAC authorization failed for user",
            "evidence": {"reason": "Forbidden"}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="default", resource_kind="Pod", sla_tier=SLATier.TIER3
        )
        
        assert classified.classification.category == IssueCategory.SECURITY
        # Security issues should be escalated by one priority level
        # Low severity + Tier3 would normally be P3, but security escalates to P2
        if classified.classification.severity == IssueSeverity.LOW:
            assert classified.classification.priority == IssuePriority.P2
    
    def test_sla_tier_priority_matrix(self):
        """Test SLA tier priority calculation matrix."""
        # Critical issue in Tier1 should be P0
        issue = {"type": "crash", "message": "OOMKilled", "evidence": {}}
        classified = self.classifier.classify_issue(
            issue, namespace="prod", resource_kind="Pod", sla_tier=SLATier.TIER1
        )
        assert classified.classification.priority == IssuePriority.P0
        
        # Same issue in Tier3 should be P1  
        classified_tier3 = self.classifier.classify_issue(
            issue, namespace="dev", resource_kind="Pod", sla_tier=SLATier.TIER3
        )
        assert classified_tier3.classification.priority == IssuePriority.P1
    
    def test_escalation_timing(self):
        """Test escalation timing logic."""
        issue = {
            "type": "critical_failure",
            "message": "Service completely down",
            "evidence": {}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="prod", resource_kind="Pod"
        )
        
        # Should need escalation if age exceeds SLA
        if classified.classification.priority == IssuePriority.P0:
            # P0 SLA is 15 minutes
            assert not classified.needs_escalation()  # Just created
            
            # Simulate age
            classified.detected_at = datetime.utcnow() - timedelta(minutes=20)
            assert classified.needs_escalation()  # Now exceeds 15 min SLA
    
    def test_issue_tags(self):
        """Test issue tag generation."""
        issue = {
            "type": "security_breach",
            "message": "Unauthorized access attempt detected", 
            "evidence": {}
        }
        
        classified = self.classifier.classify_issue(
            issue, namespace="prod", resource_kind="Pod"
        )
        
        tags = classified.get_tags()
        
        # Should include severity, category, priority, and SLA tier
        assert any("security" in tag for tag in tags)
        assert any(classified.classification.severity.value in tag for tag in tags)
        assert any(classified.classification.priority.value in tag for tag in tags)
        assert len(tags) >= 4  # At minimum: severity, category, priority, sla_tier
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        # Critical patterns should have high confidence
        critical_issue = {
            "type": "system_failure",
            "message": "Node not ready - cluster unstable",
            "evidence": {}
        }
        
        classified = self.classifier.classify_issue(critical_issue)
        assert classified.classification.confidence >= 0.8
        
        # Generic/low severity should have lower confidence
        low_issue = {
            "type": "unknown",
            "message": "Some minor warning",
            "evidence": {}
        }
        
        classified_low = self.classifier.classify_issue(low_issue)
        assert classified_low.classification.confidence <= 0.6


if __name__ == "__main__":
    pytest.main([__file__])