from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, cast

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.complexity import ComplexRequestDetector
from app.application.conversations.kernel.decision_normalizer import (
    PlannerDecision,
    build_context_text,
    normalize_decision_to_plan,
)
from app.application.conversations.kernel.followup_rules import plan_from_dialogue_state
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.referential_rules import plan_with_referential_rules
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.structured_rule_planner import StructuredRulePlanner
from app.application.conversations.kernel.temporal_parsing import default_now


class PlannerClassifier(Protocol):
    async def classify(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
        context_text: str | None = None,
        prefer_rules: bool = False,
    ) -> Any: ...


class AssistantActionPlanner:
    def __init__(
        self,
        *,
        classifier: PlannerClassifier,
        complex_request_detector: ComplexRequestDetector,
        structured_rule_planner: StructuredRulePlanner,
        now_provider: Callable[[], datetime] | None = None,
        default_timezone: str = "Asia/Shanghai",
    ) -> None:
        self.classifier = classifier
        self.complex_request_detector = complex_request_detector
        self.structured_rule_planner = structured_rule_planner
        self.now_provider = now_provider or default_now
        self.default_timezone = default_timezone

    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan:
        followup_plan = plan_from_dialogue_state(command, turn_context=turn_context)
        if followup_plan is not None:
            return followup_plan

        assessment = self.complex_request_detector.assess(command.text)
        if assessment.is_complex:
            structured_plan = await self.structured_rule_planner.plan(
                command,
                turn_context=turn_context,
                assessment=assessment,
            )
            if structured_plan is not None:
                return structured_plan

        direct_plan = plan_with_referential_rules(
            command,
            turn_context=turn_context,
            now_provider=self.now_provider,
            default_timezone=self.default_timezone,
        )
        if direct_plan is not None:
            return direct_plan

        decision = cast(
            PlannerDecision,
            await self.classifier.classify(
                command,
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                context_text=build_context_text(turn_context),
                prefer_rules=True,
            ),
        )
        return normalize_decision_to_plan(decision)
