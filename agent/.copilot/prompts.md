# AI-SRE-Agent Development Guidelines

> 이 문서는 GitHub Copilot이 AI-SRE-Agent 프로젝트에서 일관성 있는 코드를 생성하도록 가이드하는 프롬프트입니다.

## Project Overview

이 프로젝트는 **AutoGen 프레임워크**를 기반으로 한 Kubernetes SRE 자동화 에이전트입니다. 멀티 에이전트 시스템을 통해 Kubernetes 클러스터의 문제를 분석하고 해결하는 것을 목표로 합니다.

### Key Technologies
- **AutoGen 0.7.4+**: 멀티 에이전트 대화 시스템
- **Python 3.11+**: 주 개발 언어
- **Pydantic**: 데이터 검증 및 설정 관리
- **FastAPI**: REST API 서버
- **Kubernetes Client**: 클러스터 상호작용
- **Structlog**: 구조화된 로깅

## Code Style Guidelines

### 1. Python Code Standards

#### Import Organization
```python
"""Module docstring describing purpose and usage."""

from __future__ import annotations  # Always first

# Standard library imports
import asyncio
from pathlib import Path
from typing import Any, Dict, List

# Third-party imports
import structlog
from autogen import ConversableAgent
from kubernetes import client

# Local imports
from ..config import get_settings
from ..tools.kubernetes import KubernetesTools
```

#### Type Hints
- **Always use type hints** for function parameters and return values
- Use `from __future__ import annotations` for forward references
- Prefer union syntax: `str | None` over `Optional[str]`
- Use generic types: `list[str]`, `dict[str, Any]`

```python
def analyze_pod_status(
    self, 
    namespace: str, 
    pod_name: str
) -> dict[str, Any]:
    """Analyze pod status and return structured data."""
```

#### Docstrings
Use Google-style docstrings with structured sections:

```python
def create_analysis_agent(
    name: str,
    model: str = "gpt-4",
    temperature: float = 0.3
) -> ConversableAgent:
    """
    Create and configure an analysis agent for SRE operations.

    Args:
        name: Unique identifier for the agent
        model: LLM model to use (default: gpt-4)
        temperature: Sampling temperature (default: 0.3)

    Returns:
        Configured ConversableAgent instance

    Raises:
        ConfigurationError: If model configuration is invalid
    """
```

### 2. AutoGen Patterns

#### Agent Creation
Always follow this pattern for AutoGen agents:

```python
class AnalysisAgent(ConversableAgent):
    """Kubernetes issue analysis agent using AutoGen 0.7.4+ patterns."""

    def __init__(
        self, 
        name: str = "analysis_agent", 
        system_message: str | None = None, 
        **kwargs
    ):
        if system_message is None:
            system_message = self._get_default_system_message()

        super().__init__(name=name, system_message=system_message, **kwargs)

        # Register tools for LLM function calling
        self.register_for_llm(name="get_pod_status")(self.get_pod_status)
        
        # Register for execution
        self.register_for_execution(name="get_pod_status")(self.get_pod_status)
```

#### Function Registration
- Use descriptive function names for tool registration
- Always register both for LLM and execution
- Include comprehensive docstrings for tool functions

```python
@self.register_for_llm(name="analyze_kubernetes_events")
def analyze_events(
    self, 
    namespace: str = "default", 
    hours: int = 1
) -> dict[str, Any]:
    """
    Analyze recent Kubernetes events for anomalies.
    
    Args:
        namespace: Kubernetes namespace to analyze
        hours: Number of hours to look back
        
    Returns:
        Analysis results with event summaries and anomalies
    """
```

### 3. Configuration Management

#### Pydantic Settings
Always use Pydantic BaseSettings for configuration:

```python
class AgentSettings(BaseSettings):
    """Agent configuration with environment variable support."""
    
    model: str = "gpt-4"
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(1000, gt=0)
    timeout_seconds: int = 60

    class Config:
        env_prefix = "AGENT_"
        env_file = ".env"
```

#### Environment Variables
- Use consistent naming: `{SERVICE}_{SETTING}`
- Provide sensible defaults
- Include validation where appropriate

### 4. Error Handling

#### Structured Error Handling
```python
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

class SREAgentError(Exception):
    """Base exception for SRE Agent operations."""

class KubernetesConnectionError(SREAgentError):
    """Kubernetes cluster connection failed."""

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def safe_k8s_operation(operation: callable) -> Any:
    """Execute Kubernetes operations with retry logic."""
    try:
        return await operation()
    except Exception as e:
        logger.error(
            "kubernetes_operation_failed",
            operation=operation.__name__,
            error=str(e)
        )
        raise KubernetesConnectionError(f"Operation failed: {e}") from e
```

### 5. Logging Standards

#### Structured Logging with Structlog
```python
import structlog

logger = structlog.get_logger()

# Good: Structured logging
logger.info(
    "agent_conversation_started",
    agent_name=agent.name,
    conversation_id=conv_id,
    participants=len(participants)
)

# Good: Error logging with context
logger.error(
    "kubernetes_api_error",
    namespace=namespace,
    resource_type="Pod",
    error_code=response.status_code,
    error_message=response.text
)
```

### 6. Testing Patterns

#### Async Testing
```python
import pytest
import pytest_asyncio

class TestAnalysisAgent:
    """Test suite for AnalysisAgent functionality."""

    @pytest.fixture
    async def mock_k8s_client(self):
        """Mock Kubernetes client for testing."""
        # Setup mock
        pass

    @pytest.mark.asyncio
    async def test_pod_analysis_success(self, mock_k8s_client):
        """Test successful pod analysis workflow."""
        agent = AnalysisAgent()
        result = await agent.analyze_pod("test-namespace", "test-pod")
        
        assert result["status"] == "healthy"
        assert "analysis" in result
```

### 7. File Organization

#### Project Structure
```
agent/
├── src/
│   ├── agents/          # AutoGen agent implementations
│   ├── tools/           # Kubernetes and monitoring tools
│   ├── workflows/       # Multi-agent conversation flows
│   ├── guards/          # Safety and validation logic
│   └── api/            # FastAPI endpoints
├── configs/            # Configuration files
├── tests/             # Test suites
└── pyproject.toml     # Project configuration
```

#### Naming Conventions
- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions/Variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`

### 8. AutoGen Best Practices

#### Multi-Agent Workflows
```python
class SREWorkflow:
    """Orchestrate multi-agent SRE operations."""
    
    def __init__(self):
        self.agents = {
            "analysis": AnalysisAgent(),
            "recommendation": RecommendationAgent(),
            "approval": ApprovalAgent(),
            "execution": ExecutionAgent()
        }
        
    async def handle_incident(self, incident_data: dict) -> dict:
        """Process incident through agent pipeline."""
        # Analysis phase
        analysis = await self.agents["analysis"].analyze(incident_data)
        
        # Recommendation phase
        recommendations = await self.agents["recommendation"].recommend(analysis)
        
        # Approval phase
        approved_actions = await self.agents["approval"].review(recommendations)
        
        # Execution phase (if approved)
        if approved_actions:
            results = await self.agents["execution"].execute(approved_actions)
            return results
```

#### Safety First
- Always implement dry-run mode for destructive operations
- Require human approval for high-risk actions
- Implement proper access controls and audit logging
- Use allowlists for permitted actions

## Development Workflow

### Before Implementing New Features

1. **Check existing patterns** in similar files
2. **Follow the agent-based architecture** - don't create monolithic functions
3. **Add proper configuration** using Pydantic Settings
4. **Include comprehensive error handling** with structured logging
5. **Write tests** for new functionality
6. **Update documentation** as needed

### Code Review Checklist

- [ ] Type hints on all functions
- [ ] Proper docstrings with Args/Returns/Raises
- [ ] Structured logging instead of print statements
- [ ] Error handling with custom exceptions
- [ ] Configuration via Pydantic Settings
- [ ] Tests for new functionality
- [ ] Follows AutoGen 0.7.4+ patterns
- [ ] Includes safety measures for Kubernetes operations

## Common Anti-Patterns to Avoid

❌ **Don't**: Use print statements for logging
✅ **Do**: Use structlog with structured data

❌ **Don't**: Hard-code configuration values
✅ **Do**: Use Pydantic Settings with environment variables

❌ **Don't**: Create generic "do everything" functions
✅ **Do**: Follow the agent-based architecture with specific responsibilities

❌ **Don't**: Ignore error handling
✅ **Do**: Implement comprehensive error handling with retries where appropriate

❌ **Don't**: Mix synchronous and asynchronous code carelessly
✅ **Do**: Be consistent with async/await patterns

---

*이 가이드라인을 따라 일관성 있고 유지보수 가능한 AutoGen 기반 SRE 에이전트를 개발하세요.*