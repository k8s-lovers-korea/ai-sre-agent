#!/usr/bin/env python3
"""
Interactive Terminal Chat with MetricAnalyzeAgent

터미널에서 MetricAnalyzeAgent와 대화할 수 있는 인터페이스를 제공합니다.
AutoGen 0.7+ 기능을 사용하여 실시간 대화가 가능합니다.

Usage:
    python chat_with_agent.py
"""

import asyncio
import sys
from pathlib import Path

import structlog

# Add project paths for imports
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))

from autogen_core import CancellationToken
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.base import TaskResult
from autogen_agentchat.agents import AssistantAgent

from agents.metric_analyze_agent import MetricAnalyzeAgent
from configs.config import get_settings

logger = structlog.get_logger()


class InteractiveChat:
    """터미널 기반 에이전트 대화 인터페이스"""

    def __init__(self):
        self.settings = get_settings()
        self.agent = None
        self.team = None  # RoundRobinGroupChat team
        self._setup_logging()

    def _setup_logging(self):
        """개발용 로깅 설정"""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    def _create_model_client(self):
        """모델 클라이언트 생성"""
        try:
            endpoint = self.settings.llm.azure_openai_endpoint
            api_key = self.settings.llm.azure_openai_api_key

            if not endpoint or not api_key:
                raise ValueError("Azure OpenAI endpoint와 API key가 필요합니다.")

            return AzureOpenAIChatCompletionClient(
                model="gpt-4o",
                api_version=self.settings.llm.azure_openai_api_version,
                azure_endpoint=endpoint,
                api_key=api_key,
                model_capabilities={
                    "vision": False,
                    "function_calling": True,
                    "json_output": True,
                },
            )
        except Exception as e:
            logger.error(f"Failed to create Azure OpenAI client: {e}")
            logger.info("환경변수 확인: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY")
            sys.exit(1)

    def _create_agent(self) -> MetricAnalyzeAgent:
        """MetricAnalyzeAgent 인스턴스 생성"""
        model_client = self._create_model_client()

        agent = MetricAnalyzeAgent(
            name="metric_analyzer",
            description="Kubernetes 메트릭 분석 전문 에이전트",
            model_client=model_client,
        )

        # Team 생성 (단일 에이전트이지만 Team 구조 필요)
        termination = MaxMessageTermination(max_messages=10) | TextMentionTermination(
            "TERMINATE"
        )

        self.team = RoundRobinGroupChat(
            participants=[agent],
            termination_condition=termination,
            max_turns=3,  # 사용자 질문당 최대 3번의 교환
        )

        return agent

    def _print_welcome(self):
        """환영 메시지 출력"""
        print("\n" + "=" * 70)
        print("🤖 MetricAnalyzeAgent 터미널 대화")
        print("=" * 70)
        print("AutoGen 0.7+ 기반 Prometheus 메트릭 분석 에이전트와 대화하세요.")
        print("\n📋 주요 기능:")
        print("  • prometheus_get_essential_metrics: 기본 시스템 메트릭 수집")
        print("  • prometheus_get_metric_names: 사용 가능한 메트릭 탐색")
        print("  • prometheus_query_specific_metrics: 상세 메트릭 쿼리")
        print("  • prometheus_get_targets: Prometheus 타겟 상태 확인")
        print("\n💡 사용 예시:")
        print("  - '기본 메트릭을 수집해줘'")
        print("  - 'CPU와 메모리 사용량을 분석해줘'")
        print("  - 'production namespace의 메트릭을 보여줘'")
        print("  - 'prometheus 타겟 상태를 확인해줘'")
        print("\n🚀 명령어:")
        print("  • 'quit' 또는 'exit': 종료")
        print("  • 'help': 도움말")
        print("  • 'status': 에이전트 상태 확인")
        print("  • 'reset': 분석 상태 초기화")
        print("=" * 70)

    def _print_help(self):
        """도움말 출력"""
        if not self.agent:
            print("\n❌ 에이전트가 초기화되지 않았습니다.")
            return

        agent = self.agent
        print("\n📖 도움말")
        print("-" * 50)
        print(f"현재 워크플로우 단계: Step {agent.get_current_workflow_step()}")
        print("\n" + agent.get_workflow_guidance())
        print("\n🔧 Available Commands:")
        print("  • help: 이 도움말")
        print("  • status: 에이전트와 분석 상태")
        print("  • reset: 분석 상태 초기화")
        print("  • quit/exit: 프로그램 종료")

    def _print_status(self):
        """에이전트 상태 출력"""
        if not self.agent:
            print("\n❌ 에이전트가 초기화되지 않았습니다.")
            return

        agent = self.agent
        state = agent.get_analysis_state()

        print("\n📊 에이전트 상태")
        print("-" * 50)
        print(f"• 현재 단계: Step {state['current_step']}")
        print(f"• 기본 메트릭 수집 완료: {state['essential_metrics_collected']}")
        print(f"• 메트릭 이름 탐색 완료: {state['metric_names_explored']}")
        print(f"• 상세 메트릭 쿼리 완료: {state['detailed_metrics_queried']}")
        print(f"• 타겟 확인 완료: {state['targets_checked']}")

        if state["analysis_context"]:
            print("\n📋 분석 컨텍스트:")
            for key, value in state["analysis_context"].items():
                print(f"  • {key}: {str(value)[:100]}...")

    async def _handle_user_input(self, user_input: str) -> bool:
        """사용자 입력 처리"""
        user_input = user_input.strip()

        # 종료 명령어
        if user_input.lower() in ["quit", "exit", "q"]:
            return False

        # 도움말
        if user_input.lower() in ["help", "h"]:
            self._print_help()
            return True

        # 상태 확인
        if user_input.lower() in ["status", "s"]:
            self._print_status()
            return True

        # 상태 초기화
        if user_input.lower() in ["reset", "r"]:
            if not self.agent:
                print("❌ 에이전트가 초기화되지 않았습니다.")
                return True
            self.agent.reset_analysis_state()
            print("✅ 분석 상태가 초기화되었습니다.")
            return True

        # 빈 입력 무시
        if not user_input:
            return True

        # 에이전트와 대화
        try:
            if not self.agent or not self.team:
                print("❌ 에이전트가 초기화되지 않았습니다.")
                return True

            print(f"\n🤖 {self.agent.name}: 분석 중...")

            # AutoGen 0.7+ Team을 사용한 실제 에이전트 대화
            response = await self._chat_with_agent(user_input)
            print(f"\n💬 응답:\n{response}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            print(f"❌ 오류가 발생했습니다: {e}")

        return True

    async def _chat_with_agent(self, user_input: str) -> str:
        """
        실제 에이전트와 대화

        AutoGen 0.7+ RoundRobinGroupChat을 사용하여 실제 에이전트와 대화합니다.
        """
        try:
            if not self.team:
                return "❌ Team이 초기화되지 않았습니다."

            # Team을 사용하여 실제 대화 실행
            result = await self.team.run(task=user_input)

            # TaskResult에서 응답 추출
            if hasattr(result, "messages") and result.messages:
                # 마지막 메시지가 에이전트의 응답
                last_message = result.messages[-1]

                # getattr로 안전하게 속성 추출
                content_attrs = ["content", "text", "message", "data"]
                for attr in content_attrs:
                    if hasattr(last_message, attr):
                        content = getattr(last_message, attr)
                        if content:
                            return str(content)

                # 모든 속성이 없으면 전체 객체를 문자열로 변환
                return str(last_message)

            # TaskResult에서 직접 응답 확인
            result_attrs = ["summary", "result", "output", "response"]
            for attr in result_attrs:
                if hasattr(result, attr):
                    content = getattr(result, attr)
                    if content:
                        return str(content)

            # 전체 결과 객체 반환
            return f"에이전트 응답: {str(result)}"

        except Exception as e:
            logger.error(f"Error in agent chat: {e}")
            return f"에이전트 대화 중 오류가 발생했습니다: {e}"

    async def run(self):
        """메인 대화 루프"""
        try:
            # 에이전트 초기화
            print("🔄 MetricAnalyzeAgent 초기화 중...")
            self.agent = self._create_agent()
            logger.info("Agent initialized successfully")

            # 환영 메시지
            self._print_welcome()

            # 대화 루프
            while True:
                try:
                    print(
                        f"\n📍 현재 단계: Step {self.agent.get_current_workflow_step()}"
                    )
                    user_input = input("\n💬 메시지 입력 (help: 도움말): ")

                    # 사용자 입력 처리
                    should_continue = await self._handle_user_input(user_input)
                    if not should_continue:
                        break

                except KeyboardInterrupt:
                    print("\n\n⏹️  Ctrl+C로 중단되었습니다.")
                    break
                except EOFError:
                    print("\n\n👋 대화를 종료합니다.")
                    break

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            print(f"❌ 치명적 오류: {e}")
            sys.exit(1)

        finally:
            print("\n👋 MetricAnalyzeAgent와의 대화가 종료되었습니다.")


async def main():
    """메인 실행 함수"""
    chat = InteractiveChat()
    await chat.run()


if __name__ == "__main__":
    asyncio.run(main())
