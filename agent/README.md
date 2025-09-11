# SRE Agent

> AutoGen-powered multi-agent system for intelligent Kubernetes SRE operations.

## Quick Start

```bash
# 1. Setup Environment
cd agent
python -m venv venv && source venv/bin/activate
pip install -e ".[dev,azure]"

# 2. Configure Settings
cp .env.example .env
# Edit .env: Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, KUBECONFIG

# 3. Start Development Server
python dev.py
# → http://localhost:8000 (API) + AutoGen multi-agent workflow ready
# → http://localhost:8000/docs (Interactive API Documentation)
# → http://localhost:8000/redoc (Alternative API Docs)

# 4. Test the Multi-Agent System
curl -X POST http://localhost:8000/decide \
  -H "Content-Type: application/json" \
  -d '{"event_type": "Warning", "namespace": "default", "resource_name": "test-pod", "resource_kind": "Pod", "event_data": {}}'
```

## Architecture

**AutoGen GroupChat Workflow**: Multi-agent collaboration for intelligent SRE operations.

```
K8s Event → SREWorkflow (GroupChat) → Decision/Actions
              ↓
    🔍 Analysis Agent (diagnoses with K8s tools)
              ↓
    💡 Recommendation Agent (suggests actions)
              ↓
    🛡️ Guard Agent (validates safety)
              ↓
    ✅ Approval Agent (makes final decision)
              ↓
    ⚡ Execution Agent (implements actions)
```

### Key Components

- **SREWorkflow**: Business logic layer managing multi-agent workflows
- **GroupChatManager**: AutoGen's native orchestrator for agent conversations
- **KubernetesTools**: Real K8s API integration with function calling
- **Analysis Agent**: Pattern matching and symptom correlation with evidence
- **Multi-Agent Decision**: Collaborative reasoning through structured conversations
- **Safety-First**: Dry-run mode, human approval, and action validation

## Configuration

### Environment Variables

**Required:**
- `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_API_KEY` (Azure OpenAI)
- OR `OPENAI_API_KEY` (OpenAI)
- `KUBECONFIG` (Kubernetes config path)

**Optional:**
- `PROMETHEUS_URL` - Metrics integration
- `AZURE_KEY_VAULT_URL` - Secure secret management
- `ENABLE_DRY_RUN=true` - Safety mode (default)
- `REQUIRE_HUMAN_APPROVAL=true` - Human-in-the-loop (default)

### AutoGen Configuration

The workflow is configured through environment variables and code:

**LLM Settings**: Configured in `src/config.py` with model selection per agent
**Agent Behavior**: Defined in `src/workflows/sre_workflow.py` using GroupChatManager
**Tool Registration**: Kubernetes tools auto-registered with function calling
**Safety Guards**: Built into workflow logic and tool execution

Example agent config in `configs/agents.yaml.example`:
```yaml
workflow:
  max_turns: 10
  timeout_seconds: 300
  require_consensus: true
  human_in_loop_actions:
    - "delete_resources"
    - "scale_down_critical"
```

## API Documentation

### Interactive Documentation (FastAPI)

When running the development server, FastAPI automatically provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API testing interface
  - Request/response examples
  - Schema validation

- **ReDoc**: http://localhost:8000/redoc
  - Clean, readable API documentation
  - Generated from OpenAPI schema

### API Endpoints

- `GET /health` - Health check
- `POST /decide` - Multi-agent decision endpoint (called by K8s Operator)
- `POST /execute` - Action execution with safety guards

### Example Usage

```bash
# Health check
curl http://localhost:8000/health

# Decision request (simulates K8s Operator call)
curl -X POST http://localhost:8000/decide \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "Warning",
    "namespace": "production",
    "resource_name": "web-app",
    "resource_kind": "Pod",
    "event_data": {"reason": "FailedMount", "message": "Volume mount failed"}
  }'
```

**💡 Tip**: Use the interactive docs at http://localhost:8000/docs to:
- Test API endpoints with a web interface
- See request/response schemas
- Understand the AutoGen multi-agent workflow
- View real-time validation and examples

**Response**: Multi-agent analysis with decision, confidence, and recommended actions.

## Development

### Install & Run
```bash
# Install with dev dependencies
pip install -e ".[dev,azure]"

# Development server with hot reload + debug logs
python dev.py
# ✅ API: http://localhost:8000
# ✅ Docs: http://localhost:8000/docs (Swagger UI)
# ✅ Docs: http://localhost:8000/redoc (ReDoc)

# Or direct API start (production mode)
python -m src.api.main
```

### Testing
```bash
# Run all tests
pytest --cov=src tests/

# Test specific components
pytest tests/test_sre_workflow.py -v
pytest tests/test_kubernetes_tools.py -v
```

### Code Quality
```bash
# Format and lint
black src/ && ruff check src/ --fix

# Type checking
mypy src/

# Pre-commit hooks
pre-commit install && pre-commit run --all-files
```

### AutoGen Development Guide

이 프로젝트는 **AutoGen 0.2+**를 사용한 멀티 에이전트 시스템입니다. AutoGen의 올바른 사용 패턴을 이해하고 개발하기 위한 가이드입니다.

#### AutoGen 핵심 개념

AutoGen에서는 **"Orchestrator"라는 공식 용어가 없습니다**. 대신 다음 구조를 사용:

```python
# 1. GroupChatManager (AutoGen의 실제 orchestrator)
from autogen import GroupChat, GroupChatManager

# 2. Workflow (비즈니스 로직 래퍼)
class SREWorkflow:
    def __init__(self):
        self.agents = self._create_agents()
        self.group_chat = self._create_group_chat()
        self.manager = self._create_manager()  # GroupChatManager
    
    def _create_manager(self) -> GroupChatManager:
        return GroupChatManager(
            groupchat=self.group_chat,
            llm_config={"model": "gpt-4", "temperature": 0.0}
        )
```

#### 에이전트 작성 패턴

**Function Calling 에이전트** (권장):
```python
from autogen import ConversableAgent

class AnalysisAgent(ConversableAgent):
    def __init__(self, name: str, **kwargs):
        super().__init__(name=name, system_message="...", **kwargs)
        
        # 도구 등록 (AutoGen 0.2+ 패턴)
        self.register_for_llm(name="get_pod_status")(self.k8s_tools.get_pod_status)
        self.register_for_execution(name="get_pod_status")(self.k8s_tools.get_pod_status)
```

#### 도구(Tools) 작성 패턴

**타입 어노테이션 필수** (AutoGen function calling):
```python
from typing import Annotated

async def get_pod_status(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod_name: Annotated[str, "Pod name to check"] | None = None,
) -> dict[str, Any]:
    """
    Get pod status information.
    
    Args:
        namespace: Kubernetes namespace
        pod_name: Specific pod name (optional)
    
    Returns:
        Pod status information
    """
    # 구현...
```

#### 워크플로우 실행 패턴

**비동기 처리** (권장):
```python
async def process_incident(self, event_data: dict) -> dict:
    initial_message = f"분석해주세요: {event_data}"
    
    result = await self.manager.a_initiate_chat(
        self.agents["analysis"], 
        message=initial_message,
        max_turns=10
    )
    
    return self._extract_decision(result)
```

#### 개발 시 주의사항

1. **LLM Config**: 각 에이전트마다 다른 모델/설정 가능
2. **Function Calling**: `Annotated` 타입 힌트 필수
3. **Error Handling**: AutoGen 내부 예외 처리 고려
4. **Async/Await**: 모든 LLM 호출은 비동기 권장
5. **Message History**: GroupChat이 대화 히스토리 자동 관리

#### 디버깅 팁

```python
# 1. 에이전트 대화 로그 확인
import structlog
logger = structlog.get_logger()

# 2. 개발 모드에서 mock 사용
if self.settings.development.mock_k8s_api:
    return self._mock_pod_status(namespace, pod_name)

# 3. GroupChat 메시지 히스토리 검사
print(f"Messages: {self.group_chat.messages}")
```

### Project Structure
```
src/
├── workflows/
│   └── sre_workflow.py     # AutoGen GroupChat workflow
├── agents/
│   └── analysis.py         # K8s issue analysis agent
├── tools/
│   └── kubernetes.py       # K8s API integration
├── api/
│   └── main.py            # FastAPI endpoints
├── guards/                 # Safety mechanisms (empty)
├── config.py              # Pydantic settings
└── __init__.py

configs/
├── agents.yaml.example    # Agent configuration template
└── README.md              # Configuration guide

dev.py                     # Development server
pyproject.toml            # Project dependencies & config
.env.example              # Environment template
```
