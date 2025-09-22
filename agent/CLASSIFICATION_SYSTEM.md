# Issue Classification and Priority System

This document describes the enhanced 4-level issue classification and SLA-based priority system implemented for the AI-SRE Agent.

## Overview

The system automatically classifies Kubernetes issues using:
- **4-Level Severity Classification**: Critical, High, Medium, Low
- **Category Auto-Tagging**: Infrastructure, Application, Network, Security
- **SLA-Based Priority Matrix**: P0-P3 priorities based on severity + SLA tier
- **Automatic Escalation Rules**: Based on issue age vs SLA response times

## Severity Classification

### Critical (P0-P1)
- **Patterns**: `OOMKilled`, `CrashLoopBackOff`, `ImagePullBackOff`, `FailedMount`, `Node not ready`
- **Impact**: Service completely down, data loss risk
- **Response**: Immediate action required

### High (P1-P2) 
- **Patterns**: `Failed scheduling`, `Insufficient resources`, `Pod evicted`, `Probe failed`
- **Impact**: Major functionality impacted, performance degradation
- **Response**: Urgent attention needed

### Medium (P2-P3)
- **Patterns**: `Pod restart`, `Container exit`, existing `pod_restarts`, `general_failure`
- **Impact**: Minor functionality impacted, workarounds available
- **Response**: Scheduled resolution

### Low (P3)
- **Patterns**: `Config warning`, `Deprecation`, unknown issues
- **Impact**: Minimal impact, cosmetic issues
- **Response**: Best effort resolution

## Category Classification

### Infrastructure
- **Patterns**: `node`, `storage`, `volume`, `disk`, `memory`, `cpu`, `hardware`
- **Resources**: `Node`, `PersistentVolume`, `StorageClass`
- **Examples**: Storage failures, resource exhaustion, hardware issues

### Application  
- **Patterns**: `pod`, `container`, `deployment`, `application`
- **Resources**: `Pod`, `Deployment`, `ReplicaSet`
- **Examples**: App crashes, configuration errors, container issues

### Network
- **Patterns**: `dns`, `connection`, `network`, `ingress`, `service`
- **Resources**: `Service`, `Ingress`, `NetworkPolicy`
- **Examples**: Connectivity issues, DNS failures, load balancer problems

### Security
- **Patterns**: `rbac`, `unauthorized`, `forbidden`, `security`
- **Impact**: Security issues get automatic priority escalation (+1 level)
- **Examples**: Authorization failures, policy violations, access control

## SLA Tiers and Priority Matrix

### SLA Tier Detection
- **Tier1**: Production namespaces (`prod*`, `production`, `live`, `main`, `critical`, `sensitive`)
- **Tier2**: Standard services (default)
- **Tier3**: Development namespaces (`dev*`, `staging`, `test`, `demo`)

### Priority Calculation Matrix

| Severity | Tier1 | Tier2 | Tier3 |
|----------|-------|-------|-------|
| Critical | P0    | P0    | P1    |
| High     | P0    | P1    | P2    |
| Medium   | P1    | P2    | P3    |
| Low      | P2    | P3    | P3    |

**Special Rule**: Security issues are escalated by one priority level.

## Escalation Rules

### Response SLA Times
- **P0 (Critical)**: 15 minutes
- **P1 (High)**: 1 hour  
- **P2 (Medium)**: 4 hours
- **P3 (Low)**: 24 hours

### Escalation Actions
- **P0**: `notify_oncall`, `create_incident` → Slack, SMS, Email
- **P1**: `notify_team_lead`, `update_status_page` → Slack, Email
- **P2**: `notify_team`, `schedule_review` → Slack

## Integration

### AnalysisAgent Enhancement
```python
# Enhanced analysis with classification
result = await analysis_agent._analyze_symptoms(events, pod_status, context)

# Returns both legacy and new format
{
    "issues": [...],              # Legacy format
    "classified_issues": [...],   # New classified format
    "escalation_required": bool,
    "analysis_summary": "...",
    "confidence": "high"
}
```

### API Response Enhancement
```python
# DecisionResponse now includes classification data
{
    "decision": "approve",
    "confidence": 0.8,
    "classified_issues": [...],
    "escalation_required": false,
    "highest_priority": "p1", 
    "issue_categories": ["infrastructure", "application"]
}
```

## Usage Examples

### Basic Classification
```python
from src.services.issue_classifier import IssueClassifierService

classifier = IssueClassifierService()

issue = {
    "type": "pod_failure",
    "message": "OOMKilled - container crashed",
    "evidence": {"reason": "OOMKilled"}
}

classified = classifier.classify_issue(
    issue, 
    namespace="production", 
    resource_kind="Pod"
)

print(f"Severity: {classified.classification.severity.value}")    # critical
print(f"Category: {classified.classification.category.value}")    # infrastructure  
print(f"Priority: {classified.classification.priority.value}")    # p0
print(f"Tags: {classified.get_tags()}")                          # ['critical', 'infrastructure', 'p0', 'tier1']
```

### Escalation Detection
```python
# Check if issue needs escalation
if classified.needs_escalation():
    print(f"Issue requires escalation - age: {classified.get_age_minutes()} minutes")
    print(f"SLA exceeded: {classified.classification.get_response_sla_minutes()} minutes")
```

## Confidence Scoring

The system provides confidence scores for classifications:
- **Critical patterns**: 0.9 (very specific patterns)
- **High patterns**: 0.8 (quite specific patterns)  
- **Medium patterns**: 0.6 (more general patterns)
- **Low/unknown**: 0.4 (fallback classification)

Security and Network categories get +0.1 confidence boost for specificity.

## Testing

Run the classification demo:
```bash
cd agent
python demo_classification.py
```

Run unit tests:
```bash
cd agent
PYTHONPATH=/path/to/agent python -m pytest tests/test_issue_classifier.py -v
```

## Benefits

1. **Standardized Classification**: Consistent 4-level severity system
2. **SLA-Based Prioritization**: Automatic priority calculation based on business impact
3. **Smart Escalation**: Time-based escalation aligned with SLA requirements
4. **Enhanced Categorization**: Automatic tagging for better issue management
5. **Backward Compatibility**: Existing analysis workflow continues to work
6. **Security Focus**: Automatic escalation for security-related issues