#!/usr/bin/env python3
"""
Enhanced Interactive Terminal Chat with MetricAnalyzeAgent

AutoGen 0.7+ 최신 기능을 활용한 실시간 스트리밍 터미널 채팅
- RoundRobinGroupChat 기반 실제 에이전트 대화
- Console UI를 통한 실시간 스트리밍
- Prometheus 도구 직접 호출 지원

Usage:
    python enhanced_chat.py
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
from autogen_agentchat.ui import Console

from agents.metric_analyze_agent import MetricAnalyzeAgent
from configs.config import get_settings

logger = structlog.get_logger()


class EnhancedInteractiveChat:
    """향상된 터미널 기반 에이전트 대화 인터페이스"""

    def __init__(self):
        self.settings = get_settings()
        self.agent = None
        self.team = None
        self.console = None  # Console UI for streaming
        self._setup_logging()

    def _setup_logging(self):
        """개발용 로깅 설정"""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
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
            print(f"❌ Azure OpenAI 클라이언트 생성 실패: {e}")
            print("환경변수 확인: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY")
            sys.exit(1)

    def _create_agent_and_team(self) -> MetricAnalyzeAgent:
        """MetricAnalyzeAgent와 Team 생성"""
        model_client = self._create_model_client()

        agent = MetricAnalyzeAgent(
            name="metric_analyzer",
            description="Kubernetes 메트릭 분석 전문 에이전트 - 실시간 터미널 대화",
            model_client=model_client,
        )

        # Termination conditions
        max_messages = MaxMessageTermination(max_messages=5)
        text_term = TextMentionTermination("TERMINATE")
        termination = max_messages | text_term

        # RoundRobinGroupChat Team 생성
        self.team = RoundRobinGroupChat(
            participants=[agent],
            termination_condition=termination,
            max_turns=3,
        )

        # Console UI 설정 (AutoGen 0.7+ 스트리밍 지원)
        try:
            # Console은 스트리밍을 위한 wrapper이므로 여기서는 설정만
            self.console = True  # Console 사용 가능 플래그
        except Exception as e:
            logger.warning(f"Console UI 초기화 실패: {e}")
            self.console = False

        return agent

    def _print_enhanced_welcome(self):
        """향상된 환영 메시지"""
        print("\n" + "🚀" * 25)
        print("🤖 Enhanced MetricAnalyzeAgent Chat (AutoGen 0.7+)")
        print("🚀" * 25)
        print("실제 AutoGen Team을 사용한 Prometheus 메트릭 분석 에이전트")
        print("\n✨ 주요 특징:")
        print("  • 실제 AutoGen RoundRobinGroupChat 사용")
        print("  • Prometheus 도구 실시간 호출")
        print("  • 단계별 워크플로우 진행")
        print("  • Function Calling 지원")

        if self.console:
            print("  • Console UI 스트리밍 지원 ✅")
        else:
            print("  • Console UI 스트리밍 비활성화 ⚠️")

        print("\n🔧 Prometheus 도구:")
        print("  1. prometheus_get_essential_metrics()")
        print("  2. prometheus_get_metric_names()")
        print("  3. prometheus_query_specific_metrics()")
        print("  4. prometheus_get_targets()")

        print("\n💬 대화 예시:")
        print('  • "기본 메트릭을 수집해줘"')
        print('  • "production namespace의 CPU 사용률을 확인해줘"')
        print('  • "prometheus 타겟 상태를 점검해줘"')
        print('  • "메모리 사용률이 높은 pod를 찾아줘"')

        print("\n⌨️  명령어:")
        print("  • help/h: 도움말 및 상태")
        print("  • reset/r: 에이전트 상태 초기화")
        print("  • quit/exit/q: 종료")
        print("🚀" * 25)

    def _print_agent_status(self):
        """에이전트 상태 출력"""
        if not self.agent:
            print("❌ 에이전트가 초기화되지 않았습니다.")
            return

        print("\n📊 에이전트 상태")
        print("-" * 40)

        try:
            current_step = self.agent.get_current_workflow_step()
            state = self.agent.get_analysis_state()

            print(f"🔄 현재 워크플로우 단계: Step {current_step}")
            print(
                f"📈 기본 메트릭 수집: {'✅' if state['essential_metrics_collected'] else '⏸️'}"
            )
            print(f"🔍 메트릭 탐색: {'✅' if state['metric_names_explored'] else '⏸️'}")
            print(f"📊 상세 쿼리: {'✅' if state['detailed_metrics_queried'] else '⏸️'}")
            print(f"🎯 타겟 확인: {'✅' if state['targets_checked'] else '⏸️'}")

            if state["analysis_context"]:
                print("\n📋 분석 컨텍스트:")
                for key, value in state["analysis_context"].items():
                    print(f"  • {key}: {str(value)[:60]}...")
        except Exception as e:
            print(f"상태 확인 중 오류: {e}")

    async def _handle_command(self, user_input: str) -> bool:
        """명령어 처리"""
        cmd = user_input.lower().strip()

        if cmd in ["quit", "exit", "q"]:
            return False

        elif cmd in ["help", "h"]:
            self._print_agent_status()
            if self.agent:
                try:
                    print(
                        f"\n📚 현재 단계 가이드:\n{self.agent.get_workflow_guidance()}"
                    )
                except:
                    print("가이드 정보를 가져올 수 없습니다.")
            return True

        elif cmd in ["reset", "r"]:
            if self.agent:
                try:
                    self.agent.reset_analysis_state()
                    print("✅ 에이전트 상태가 초기화되었습니다.")
                except:
                    print("❌ 상태 초기화 중 오류가 발생했습니다.")
            return True

        return True

    async def _chat_with_team(self, user_input: str) -> str:
        """실제 AutoGen Team과의 대화"""
        try:
            if not self.team:
                return "❌ Team이 초기화되지 않았습니다."

            print("🔄 에이전트가 분석 중입니다...")

            # Console UI를 사용한 스트리밍 (가능한 경우)
            if self.console:
                try:
                    # run_stream을 사용한 스트리밍 실행
                    async for message in self.team.run_stream(task=user_input):
                        # 스트리밍 메시지 실시간 출력
                        print(f"📨 {message}")
                    return "✅ 스트리밍 대화가 완료되었습니다."
                except Exception as e:
                    logger.warning(f"Console 스트리밍 실패, 일반 모드로 전환: {e}")
                    self.console = False  # 스트리밍 비활성화

            # 일반 Team 실행
            result = await self.team.run(task=user_input)

            # 결과에서 에이전트 응답 추출
            if hasattr(result, "messages") and result.messages:
                for message in reversed(result.messages):  # 최신 메시지부터 확인
                    content_attrs = ["content", "text", "message", "data"]
                    for attr in content_attrs:
                        if hasattr(message, attr):
                            content = getattr(message, attr)
                            if content and str(content).strip():
                                return str(content)

                # 마지막 메시지 전체 반환
                return f"Agent: {str(result.messages[-1])}"

            # TaskResult에서 직접 내용 추출
            return f"Team 실행 완료: {str(result)}"

        except Exception as e:
            logger.error(f"Team 대화 오류: {e}")
            return f"❌ 대화 중 오류 발생: {e}"

    async def run_interactive_chat(self):
        """메인 대화 루프"""
        try:
            # 초기화
            print("🔄 Enhanced MetricAnalyzeAgent 초기화 중...")
            self.agent = self._create_agent_and_team()
            logger.info("Enhanced agent and team initialized successfully")

            # 환영 메시지
            self._print_enhanced_welcome()

            # 대화 루프
            while True:
                try:
                    # 현재 상태 표시
                    if self.agent:
                        try:
                            step = self.agent.get_current_workflow_step()
                            print(f"\n📍 현재: Step {step} | ", end="")
                        except:
                            print(f"\n📍 Agent 준비됨 | ", end="")
                    else:
                        print(f"\n📍 대기 중 | ", end="")

                    # 사용자 입력 받기
                    user_input = input("💬 메시지: ").strip()

                    if not user_input:
                        continue

                    # 명령어 처리
                    if user_input.lower() in [
                        "quit",
                        "exit",
                        "q",
                        "help",
                        "h",
                        "reset",
                        "r",
                    ]:
                        should_continue = await self._handle_command(user_input)
                        if not should_continue:
                            break
                        continue

                    # 에이전트와 실제 대화
                    response = await self._chat_with_team(user_input)
                    print(f"\n🤖 응답:\n{response}\n")

                except KeyboardInterrupt:
                    print("\n\n⏹️  Ctrl+C로 중단되었습니다.")
                    break
                except EOFError:
                    print("\n\n👋 대화를 종료합니다.")
                    break

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            print(f"❌ 치명적 오류: {e}")
            return

        finally:
            print("\n🎯 Enhanced MetricAnalyzeAgent 채팅이 종료되었습니다.")
            print("감사합니다! 🚀")


async def main():
    """메인 함수"""
    chat = EnhancedInteractiveChat()
    await chat.run_interactive_chat()


if __name__ == "__main__":
    asyncio.run(main())
