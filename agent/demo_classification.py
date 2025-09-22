#!/usr/bin/env python3
"""
Demo script to showcase the enhanced issue classification system.

This script demonstrates the 4-level severity classification,
category auto-tagging, SLA-based prioritization, and escalation rules.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.issue_classifier import IssueClassifierService
from src.models.issue_classification import SLATier, IssueSeverity, IssueCategory, IssuePriority


def print_banner(title: str):
    """Print a formatted banner."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def demo_classification_system():
    """Demo the classification system with various scenarios."""
    print_banner("SRE Agent - Issue Classification System Demo")
    
    classifier = IssueClassifierService()
    
    # Demo scenarios representing real Kubernetes issues
    scenarios = [
        {
            "name": "Critical Production Outage",
            "issue": {
                "type": "pod_failure",
                "message": "OOMKilled - critical service pod crashed",
                "evidence": {"reason": "OOMKilled", "restarts": 10}
            },
            "namespace": "production",
            "resource_kind": "Pod",
            "sla_tier": SLATier.TIER1
        },
        {
            "name": "Storage Infrastructure Issue", 
            "issue": {
                "type": "storage_issue",
                "message": "PVC mount failed - insufficient storage space",
                "evidence": {"reason": "FailedMount", "pvc": "data-volume"}
            },
            "namespace": "staging",
            "resource_kind": "PersistentVolumeClaim",
            "sla_tier": SLATier.TIER2
        },
        {
            "name": "Network Connectivity Problem",
            "issue": {
                "type": "network_issue", 
                "message": "DNS resolution failed for external service",
                "evidence": {"reason": "DNS", "service": "external-api"}
            },
            "namespace": "default",
            "resource_kind": "Service",
            "sla_tier": SLATier.TIER2
        },
        {
            "name": "Security Policy Violation",
            "issue": {
                "type": "security_violation",
                "message": "RBAC authorization failed - unauthorized pod access",
                "evidence": {"reason": "Forbidden", "user": "test-user"}
            },
            "namespace": "sensitive-data",
            "resource_kind": "Pod", 
            "sla_tier": SLATier.TIER1
        },
        {
            "name": "Development Environment Issue",
            "issue": {
                "type": "config_issue",
                "message": "Deprecated API version in deployment config",
                "evidence": {"reason": "DeprecationWarning"}
            },
            "namespace": "development",
            "resource_kind": "Deployment",
            "sla_tier": SLATier.TIER3
        }
    ]
    
    print(f"\nClassifying {len(scenarios)} incident scenarios...")
    print(f"{'Scenario':<30} {'Severity':<10} {'Category':<15} {'Priority':<8} {'SLA':<6} {'Confidence':<10}")
    print("-" * 85)
    
    classified_results = []
    
    for scenario in scenarios:
        classified = classifier.classify_issue(
            scenario["issue"],
            namespace=scenario["namespace"],
            resource_kind=scenario["resource_kind"],
            sla_tier=scenario["sla_tier"]
        )
        
        classified_results.append((scenario, classified))
        
        print(f"{scenario['name']:<30} "
              f"{classified.classification.severity.value.upper():<10} "
              f"{classified.classification.category.value.upper():<15} "
              f"{classified.classification.priority.value.upper():<8} "
              f"{classified.classification.sla_tier.value.upper():<6} "
              f"{classified.classification.confidence:<10.1f}")
    
    return classified_results


def demo_sla_matrix():
    """Demo the SLA-based priority matrix."""
    print_banner("SLA-Based Priority Matrix Demo")
    
    classifier = IssueClassifierService()
    
    # Test same issue across different SLA tiers
    issue = {
        "type": "critical_failure",
        "message": "Application service completely down",
        "evidence": {"reason": "CrashLoopBackOff"}
    }
    
    print("\nSame CRITICAL severity issue across different SLA tiers:")
    print(f"{'SLA Tier':<15} {'Priority':<10} {'Response SLA':<15}")
    print("-" * 40)
    
    for tier in [SLATier.TIER1, SLATier.TIER2, SLATier.TIER3]:
        classified = classifier.classify_issue(issue, sla_tier=tier)
        response_sla = classified.classification.get_response_sla_minutes()
        
        sla_text = f"{response_sla} minutes" if response_sla < 60 else f"{response_sla//60} hours"
        
        print(f"{tier.value.upper():<15} "
              f"{classified.classification.priority.value.upper():<10} "
              f"{sla_text:<15}")


def demo_escalation_rules():
    """Demo escalation rules and timing."""
    print_banner("Escalation Rules Demo")
    
    classifier = IssueClassifierService()
    
    # Create issues with different priorities
    issues_data = [
        {"message": "Critical system failure", "priority_expected": "P0"},
        {"message": "High impact service degradation", "priority_expected": "P1"}, 
        {"message": "Medium severity pod restarts", "priority_expected": "P2"},
    ]
    
    print("\nEscalation timing for different priority issues:")
    print(f"{'Issue Type':<35} {'Priority':<8} {'SLA Minutes':<12} {'Escalates After':<15}")
    print("-" * 70)
    
    for issue_data in issues_data:
        # Create issue that would classify to expected priority
        issue = {"type": "failure", "message": issue_data["message"], "evidence": {}}
        classified = classifier.classify_issue(issue)
        
        sla_minutes = classified.classification.get_response_sla_minutes()
        
        print(f"{issue_data['message']:<35} "
              f"{classified.classification.priority.value.upper():<8} "
              f"{sla_minutes:<12} "
              f"{sla_minutes} minutes")
    
    # Demo escalation detection
    print(f"\n📈 Testing escalation detection:")
    issue = {"type": "critical", "message": "P0 incident", "evidence": {}}
    classified = classifier.classify_issue(issue)
    
    print(f"   Fresh issue (age: 0 min) - Needs escalation: {classified.needs_escalation()}")
    
    # Simulate aged issue
    classified.detected_at = datetime.utcnow() - timedelta(minutes=20)
    print(f"   Aged issue (age: 20 min) - Needs escalation: {classified.needs_escalation()}")


def demo_issue_tags():
    """Demo issue tagging system.""" 
    print_banner("Issue Tagging System Demo")
    
    classifier = IssueClassifierService()
    
    # Different types of issues to show tagging
    tag_examples = [
        {"type": "security_breach", "message": "Unauthorized access detected", "namespace": "production"},
        {"type": "network_failure", "message": "DNS resolution timeout", "namespace": "staging"}, 
        {"type": "storage_critical", "message": "Disk space exhausted", "namespace": "development"},
    ]
    
    print("\nAutomatic issue tagging examples:")
    print(f"{'Issue':<40} {'Tags'}")
    print("-" * 80)
    
    for example in tag_examples:
        issue = {"type": example["type"], "message": example["message"], "evidence": {}}
        classified = classifier.classify_issue(issue, namespace=example["namespace"])
        
        tags = classified.get_tags()
        tags_str = ", ".join(tags)
        
        print(f"{example['message']:<40} {tags_str}")


async def demo_enhanced_analysis():
    """Demo enhanced analysis agent with classification."""
    print_banner("Enhanced Analysis Agent Demo")
    
    print("Note: This demo shows the enhanced analysis capabilities.")
    print("In a real environment, this would integrate with Kubernetes APIs.")
    
    # Simulate Kubernetes events and pod status
    mock_events = [
        {
            "type": "Warning",
            "reason": "FailedMount", 
            "message": "Unable to mount volume",
            "involvedObject": {"name": "web-app-pod"}
        },
        {
            "type": "Warning",
            "reason": "OOMKilled",
            "message": "Container killed due to memory limit",
            "involvedObject": {"name": "api-server-pod"}
        }
    ]
    
    mock_pod_status = {
        "pods": [
            {"name": "web-app-pod", "phase": "Pending", "restarts": 0},
            {"name": "api-server-pod", "phase": "Running", "restarts": 5}
        ]
    }
    
    mock_context = {
        "namespace": "production",
        "resource_kind": "Pod"
    }
    
    # Note: In a real scenario, we'd create the agent with proper model_client
    print(f"🔍 Simulated analysis of {len(mock_events)} events and {len(mock_pod_status['pods'])} pods")
    print(f"   Namespace: {mock_context['namespace']}")
    print(f"   Resource Kind: {mock_context['resource_kind']}")
    
    print(f"\n📊 Analysis Results Preview:")
    print(f"   - Would classify storage issue as HIGH severity, INFRASTRUCTURE category")
    print(f"   - Would classify OOM issue as CRITICAL severity, INFRASTRUCTURE category") 
    print(f"   - Would assign P0 priority for production Tier1 critical issues")
    print(f"   - Would recommend immediate escalation for critical issues")
    
    print(f"\n🏷️  Issue Tags Generated:")
    print(f"   - Storage Issue: ['high', 'infrastructure', 'p1', 'tier1']")
    print(f"   - OOM Issue: ['critical', 'infrastructure', 'p0', 'tier1', 'needs-escalation']")


def main():
    """Run the classification system demo."""
    print("🤖 AI-SRE Agent - Enhanced Issue Classification System")
    print("    Implementing 4-level severity classification and SLA-based prioritization")
    
    try:
        # Run classification demos
        classified_results = demo_classification_system()
        demo_sla_matrix()
        demo_escalation_rules() 
        demo_issue_tags()
        
        # Run analysis demo
        asyncio.run(demo_enhanced_analysis())
        
        print_banner("Demo Summary")
        print("✅ 4-Level Severity Classification: Critical, High, Medium, Low")
        print("✅ Issue Category Auto-Tagging: Infrastructure, Application, Network, Security") 
        print("✅ SLA-Based Priority Matrix: P0-P3 based on severity + SLA tier")
        print("✅ Automatic Escalation Rules: Based on issue age vs SLA response times")
        print("✅ Enhanced Analysis Integration: Backward-compatible with existing system")
        
        print(f"\n🎯 Key Achievements:")
        print(f"   • Security issues get automatic priority escalation")
        print(f"   • Production namespaces auto-detected as Tier1 SLA")
        print(f"   • Confidence scoring reflects classification accuracy")
        print(f"   • Issue tagging enables better categorization and filtering")
        
        print(f"\n📈 Escalation SLAs:")
        print(f"   • P0 (Critical): 15 minutes")
        print(f"   • P1 (High): 1 hour") 
        print(f"   • P2 (Medium): 4 hours")
        print(f"   • P3 (Low): 24 hours")
        
        print(f"\n🚀 System Ready: Issue classification and prioritization implemented!")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()