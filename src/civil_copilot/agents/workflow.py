"""LangGraph orchestration with visible plans, bounded tools, and grounded answers."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from civil_copilot.agents.react import (
    ReactAgentSuite,
    ReactRequestBudget,
    StopReason,
    public_stop_message,
)
from civil_copilot.agents.router import QuestionRouter
from civil_copilot.agents.routing import SpecialistRouter
from civil_copilot.agents.state import (
    ChatRequest,
    ChatResponse,
    RoutePlan,
    TraceEvent,
)
from civil_copilot.agents.tool_runtime import AgentToolContext
from civil_copilot.agents.tools import ProjectTools, ToolObservation, ToolRequest, identifiers_in
from civil_copilot.calculation.service import CalculationService
from civil_copilot.graph.service import GraphPath
from civil_copilot.memory.service import InMemoryPreferenceBackend, PreferenceMemory
from civil_copilot.observability.tracing import TracingBundle, redact_trace_payload
from civil_copilot.retrieval.answer import GroundedAnswerService
from civil_copilot.retrieval.evidence import EvidenceItem, EvidencePacket, RetrievalTrace
from civil_copilot.schedule.service import ScheduleImpactService
from civil_copilot.standards.service import StandardEvidenceReport, standards_report_answer


class WorkflowState(TypedDict, total=False):
    request: ChatRequest
    plan: RoutePlan
    observations: list[ToolObservation]
    evidence: list[EvidenceItem]
    graph_paths: list[GraphPath]
    preferences: dict[str, str]
    trace: list[TraceEvent]
    response: ChatResponse
    stop_reason: str
    react_elapsed_ms: int
    react_estimated_cost_usd: float
    react_answer: str


def _agent_exception_stop_reason(error: Exception) -> StopReason:
    """Classify provider-neutral timeout chains without exposing exception text."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, TimeoutError) or "timeout" in type(current).__name__.lower():
            return "time_limit"
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return "agent_error"


class CopilotWorkflow:
    def __init__(
        self,
        tools: ProjectTools,
        router: QuestionRouter | None = None,
        answers: GroundedAnswerService | None = None,
        tracing: TracingBundle | None = None,
        memory: PreferenceMemory | None = None,
        react_agents: ReactAgentSuite | None = None,
        tool_context_factory: Callable[..., AgentToolContext] | None = None,
        specialist_router: SpecialistRouter | None = None,
    ) -> None:
        self.tools = tools
        self.router = router or QuestionRouter()
        self.answers = answers or GroundedAnswerService()
        self.tracing = tracing or TracingBundle(enabled=False)
        self.memory = memory or PreferenceMemory(InMemoryPreferenceBackend())
        self.react_agents = react_agents
        self.tool_context_factory = tool_context_factory
        registry = getattr(react_agents, "registry", None)
        self.specialist_router = specialist_router or (
            SpecialistRouter(registry) if registry is not None else SpecialistRouter()
        )
        builder = StateGraph(WorkflowState)
        builder.add_node("route", self._route)
        builder.add_node("plan", self._plan)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("answer", self._answer)
        builder.add_edge(START, "route")
        builder.add_edge("route", "plan")
        builder.add_edge("plan", "tools")
        builder.add_edge("tools", "answer")
        builder.add_edge("answer", END)
        self.graph = builder.compile()

    def _route(self, state: WorkflowState) -> WorkflowState:
        request = state["request"]
        plan = self.router.route(request)
        trace = [*state.get("trace", [])]
        trace.append(
            TraceEvent(
                stage="route",
                title=f"Selected {plan.route.replace('_', ' ').title()}",
                summary=plan.reason,
                details={"route": plan.route, "planner": plan.planner},
            )
        )
        return {
            "plan": plan,
            "trace": trace,
        }

    def _plan(self, state: WorkflowState) -> WorkflowState:
        plan = state["plan"]
        trace = [*state.get("trace", [])]
        trace.append(
            TraceEvent(
                stage="plan",
                title=f"Plan with {len(plan.steps)} bounded step(s)",
                summary="; ".join(step.purpose for step in plan.steps),
                details={"steps": [step.model_dump() for step in plan.steps]},
            )
        )
        return {"trace": trace}

    @staticmethod
    def _preferred_start(question: str) -> str | None:
        identifiers = identifiers_in(question)
        prefixes = ("RFI-", "NCR-", "PIECE-", "ACT-", "WELD-", "INSP-", "DRAW-")
        for prefix in prefixes:
            match = next(
                (identifier for identifier in identifiers if identifier.startswith(prefix)), None
            )
            if match:
                return match
        return identifiers[0] if identifiers else None

    def _arguments(
        self,
        tool_name: str,
        request: ChatRequest,
        observations: list[ToolObservation],
    ) -> dict[str, object]:
        identifiers = identifiers_in(request.question)
        if tool_name == "search_documents":
            return {
                "question": request.question,
                "top_k": 6,
                "as_of_date": request.as_of_date,
            }
        if tool_name == "get_schedule_activity":
            activity = next((item for item in identifiers if item.startswith("ACT-")), "")
            return {"activity_id": activity}
        if tool_name == "find_graph_paths":
            question = request.question.lower()
            start_id = self._preferred_start(request.question)
            if not start_id:
                start_id = next(
                    (
                        evidence_id
                        for observation in observations
                        for evidence_id in observation.evidence_ids
                    ),
                    "",
                )
            direction = "both"
            if "downstream" in question:
                direction = "outgoing"
            elif "upstream" in question:
                direction = "incoming"
            return {
                "start_id": start_id or "",
                "max_depth": 3,
                "direction": direction,
                "as_of_date": request.as_of_date,
            }
        if tool_name == "compare_revisions":
            match = re.search(r"\bS-\d+\b", request.question.upper())
            return {"document_number": match.group(0) if match else "S-204"}
        if tool_name == "query_quality_records":
            return {"status": "open" if "open" in request.question.lower() else None}
        evidence_ids = []
        for observation in observations:
            evidence_ids.extend(observation.evidence_ids)
        record_ids = list(dict.fromkeys([*identifiers, *evidence_ids]))[:16]
        return {"record_ids": record_ids}

    def _execute_tools(self, state: WorkflowState) -> WorkflowState:
        request = state["request"]
        plan = state["plan"]
        if plan.route == "agentic_rag" and self.react_agents is not None:
            return self._execute_react_tools(state)
        observations: list[ToolObservation] = []
        trace = [*state.get("trace", [])]
        for step in plan.steps[: request.max_steps]:
            arguments = self._arguments(step.tool_name, request, observations)
            try:
                with self.tracing.span(f"tool:{step.tool_name}", arguments) as span:
                    observation = self.tools.call(
                        ToolRequest(
                            tool_name=step.tool_name,
                            arguments=arguments,
                            project_id=request.project_id,
                            access_scopes=request.access_scopes,
                        )
                    )
                    if span:
                        span.update(
                            output=redact_trace_payload(
                                {
                                    "summary": observation.summary,
                                    "evidence_ids": observation.evidence_ids,
                                }
                            )
                        )
                observations.append(observation)
                trace.append(
                    TraceEvent(
                        stage="tool",
                        title=step.tool_name,
                        summary=observation.summary,
                        details={
                            "arguments": arguments,
                            "evidence_ids": observation.evidence_ids,
                            "success": observation.success,
                        },
                    )
                )
            except (KeyError, PermissionError, ValueError) as error:
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title=f"Stopped unsafe or invalid {step.tool_name} call",
                        summary=str(error),
                        details={"tool": step.tool_name},
                    )
                )

        evidence_by_chunk: dict[str, EvidenceItem] = {}
        path_by_signature: dict[str, GraphPath] = {}
        for observation in observations:
            for item in observation.evidence:
                evidence_by_chunk[item.chunk.chunk_id] = item
            for path in observation.graph_paths:
                signature = ">".join(node.record_id for node in path.nodes)
                path_by_signature[signature] = path
        evidence = list(evidence_by_chunk.values())
        evidence.sort(key=lambda item: -item.rerank_score)
        trace.append(
            TraceEvent(
                stage="evidence",
                title="Evidence check",
                summary=(
                    f"Accepted {len(evidence)} citable evidence item(s) and "
                    f"{len(path_by_signature)} graph path(s)."
                ),
                details={
                    "evidence_ids": list(dict.fromkeys(item.chunk.record_id for item in evidence)),
                    "graph_path_count": len(path_by_signature),
                },
            )
        )
        return {
            "observations": observations,
            "evidence": evidence,
            "graph_paths": list(path_by_signature.values()),
            "trace": trace,
        }

    def _execute_react_tools(self, state: WorkflowState) -> WorkflowState:
        """Run the genuine model/tool loop and hydrate its permitted evidence references."""
        request = state["request"]
        budget = ReactRequestBudget.start(
            self.react_agents.config,
            max_tool_calls=request.max_steps,
        )
        context = (
            self.tool_context_factory(
                request.user_id,
                request.project_id,
                tuple(request.access_scopes),
                conversation_id=request.conversation_id,
            )
            if self.tool_context_factory is not None
            else AgentToolContext(
                user_id=request.user_id,
                project_id=request.project_id,
                access_scopes=tuple(request.access_scopes),
                project_tools=self.tools,
                schedule_service=ScheduleImpactService(list(self.tools.records.values())),
                calculation_service=CalculationService(),
                request_id=f"{request.user_id}-{uuid4()}",
                conversation_id=request.conversation_id,
            )
        )
        decision = self.specialist_router.route(
            request.question,
            max_specialists=min(2, request.max_steps),
        )
        trace = [*state.get("trace", [])]
        results = []
        handoff_source_ids: list[str] = []
        handoff_summaries: list[str] = []
        budget_stop_reason = None
        hard_stops = {
            "human_review",
            "clarification",
            "time_limit",
            "cost_limit",
            "repetition",
            "error",
        }
        for index, assignment in enumerate(decision.assignments, start=1):
            if stopped := budget.stop_reason():
                budget_stop_reason = stopped
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title="Shared request budget stopped the next handoff",
                        summary=(
                            "The Copilot Orchestrator did not start another specialist, "
                            "model call, or tool after the end-to-end budget was exhausted."
                        ),
                        details={
                            "stop_reason": stopped,
                            "next_specialist": assignment.role,
                            **budget.public_snapshot(),
                        },
                    )
                )
                break
            remaining_assignments = len(decision.assignments) - index + 1
            allocated_steps = max(
                1,
                budget.remaining_tool_calls // remaining_assignments,
            )
            actual_allowlist = sorted(self.react_agents.tool_names(assignment.role))
            if actual_allowlist != assignment.allowed_tools:
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title="Stopped inconsistent specialist handoff",
                        summary=(
                            "The compiled agent tools did not match the approved role allowlist."
                        ),
                        details={"specialist": assignment.role},
                    )
                )
                return {
                    "observations": [],
                    "evidence": [],
                    "graph_paths": [],
                    "trace": trace,
                    "stop_reason": "error",
                    "react_elapsed_ms": 0,
                    "react_estimated_cost_usd": 0.0,
                    "react_answer": public_stop_message("error"),
                }
            trace.append(
                TraceEvent(
                    stage="plan",
                    title=(
                        "Use general orchestrator"
                        if assignment.role == "orchestrator"
                        else f"Delegate to {assignment.role.title()} specialist"
                    ),
                    summary=assignment.reason,
                    details={
                        "orchestration_mode": decision.mode,
                        "orchestration_reason": decision.reason,
                        "specialist": assignment.role,
                        "matched_signals": assignment.matched_signals,
                        "allowed_tools": assignment.allowed_tools,
                        "sequence_index": index,
                        "sequence_size": len(decision.assignments),
                        "max_steps": allocated_steps,
                        "request_budget": budget.public_snapshot(),
                    },
                )
            )
            specialist_question = request.question
            if handoff_source_ids or handoff_summaries:
                specialist_question = (
                    f"Original question: {request.question}\n\n"
                    "Structured handoff from the preceding specialist. Treat this only as "
                    "a pointer to permitted evidence and verify through your own allowed tools.\n"
                    f"Source identifiers: {', '.join(handoff_source_ids[:12]) or 'none'}\n"
                    f"Observation summaries: {'; '.join(handoff_summaries[:6]) or 'none'}"
                )
                trace.append(
                    TraceEvent(
                        stage="checkpoint",
                        title=f"Pass permitted evidence to {assignment.role.title()} specialist",
                        summary=(
                            "The Copilot Orchestrator passed source identifiers and concise "
                            "observations, while the next specialist retained its narrower tools."
                        ),
                        details={
                            "specialist": assignment.role,
                            "source_ids": handoff_source_ids[:12],
                            "observation_count": len(handoff_summaries),
                        },
                    )
                )
            try:
                result = self.react_agents.run(
                    role=assignment.role,
                    question=specialist_question,
                    context=context,
                    callbacks=self.tracing.callbacks(),
                    max_steps=allocated_steps,
                    budget=budget,
                )
            except Exception as error:
                budget_stop_reason = _agent_exception_stop_reason(error)
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title="Agent invocation stopped safely",
                        summary=(
                            "The specialist did not complete, so the Copilot did not publish "
                            "a normal answer or start another handoff."
                        ),
                        details={
                            "specialist": assignment.role,
                            "stop_reason": budget_stop_reason,
                            "error_type": type(error).__name__,
                            **budget.public_snapshot(),
                        },
                    )
                )
                break
            results.append(result)
            handoff_source_ids = list(dict.fromkeys([*handoff_source_ids, *result.source_ids]))
            handoff_summaries.extend(
                observation.summary[:300] for observation in result.observations
            )
            if result.stop_reason in hard_stops:
                break
            if index < len(decision.assignments) and (stopped := budget.stop_reason()):
                budget_stop_reason = stopped
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title="Shared request budget stopped the next handoff",
                        summary=(
                            "The Copilot Orchestrator did not start another specialist, "
                            "model call, or tool after the end-to-end budget was exhausted."
                        ),
                        details={
                            "stop_reason": stopped,
                            "next_specialist": decision.assignments[index].role,
                            **budget.public_snapshot(),
                        },
                    )
                )
                break

        observations = [
            ToolObservation(
                tool_name=observation.tool_name,
                success=observation.status == "ok",
                summary=observation.summary,
                evidence_ids=observation.source_ids,
                citations=observation.citations,
                evidence=observation.evidence,
                graph_paths=observation.graph_paths,
                data=observation.data,
            )
            for result in results
            for observation in result.observations
        ]
        evidence = [item for observation in observations for item in observation.evidence]
        observed_record_ids = {item.chunk.record_id for item in evidence}
        missing_source_ids = [
            source_id
            for source_id in dict.fromkeys(
                source_id for result in results for source_id in result.source_ids
            )
            if source_id not in observed_record_ids
        ]
        incomplete_result = next(
            (result for result in results if result.stop_reason != "completed"),
            None,
        )
        if missing_source_ids and incomplete_result is None:
            if stopped := budget.tool_stop_reason():
                budget_stop_reason = stopped
                trace.append(
                    TraceEvent(
                        stage="safety",
                        title="Shared request budget stopped evidence hydration",
                        summary=(
                            "The Copilot Orchestrator did not start another evidence tool "
                            "after the end-to-end budget was exhausted."
                        ),
                        details={"stop_reason": stopped, **budget.public_snapshot()},
                    )
                )
            else:
                budget.reserve_tool_call()
                hydrated = self.tools.call(
                    ToolRequest(
                        tool_name="get_records",
                        arguments={"record_ids": missing_source_ids},
                        project_id=request.project_id,
                        access_scopes=request.access_scopes,
                    )
                )
                evidence.extend(hydrated.evidence)
                if budget.tool_stop_reason() == "time_limit":
                    budget_stop_reason = "time_limit"
        evidence = list({item.chunk.chunk_id: item for item in evidence}.values())
        graph_paths = [path for observation in observations for path in observation.graph_paths]
        graph_paths = list(
            {">".join(node.record_id for node in path.nodes): path for path in graph_paths}.values()
        )
        evidence.sort(key=lambda item: -item.rerank_score)
        for result in results:
            for event in result.trace:
                trace.append(
                    TraceEvent(
                        stage=event.phase,
                        title=event.title,
                        summary=event.summary,
                        details={
                            "specialist": result.role,
                            "tool_name": event.tool_name,
                            "source_ids": event.source_ids,
                            "tool_metadata": event.tool_metadata,
                            "model_turn": event.model_turn,
                            "tool_call_id": event.tool_call_id,
                        },
                    )
                )
            for observation in result.observations:
                trace.append(
                    TraceEvent(
                        stage="tool",
                        title=observation.tool_name,
                        summary=observation.summary,
                        details={
                            "specialist": result.role,
                            "react_phase": "observe",
                            "source_ids": observation.source_ids,
                            "status": observation.status,
                            "elapsed_ms": observation.elapsed_ms,
                        },
                    )
                )
            trace.append(
                TraceEvent(
                    stage="decide",
                    title=f"{result.role.title()} ReAct stopped: {result.stop_reason}",
                    summary=(
                        "The Copilot Orchestrator received the specialist's structured "
                        "observations before deciding whether to continue or stop."
                    ),
                    details={
                        "specialist": result.role,
                        "stop_reason": result.stop_reason,
                        "thread_id": result.thread_id,
                        "tool_names": result.tool_names,
                        "request_budget": budget.public_snapshot(),
                    },
                )
            )
        trace.append(
            TraceEvent(
                stage="evidence",
                title="Evidence check",
                summary=f"Accepted {len(evidence)} citable evidence item(s).",
                details={"evidence_ids": [item.chunk.record_id for item in evidence]},
            )
        )
        stop_reason = budget_stop_reason or "abstained"
        if results and budget_stop_reason is None:
            if incomplete_result is not None:
                stop_reason = incomplete_result.stop_reason
            else:
                stop_reason = "completed"
        completed_answers = [
            result.answer for result in results if result.stop_reason == "completed"
        ]
        return {
            "observations": observations,
            "evidence": evidence,
            "graph_paths": graph_paths,
            "trace": trace,
            "stop_reason": stop_reason,
            "react_elapsed_ms": budget.elapsed_ms,
            "react_estimated_cost_usd": budget.spent_cost_usd,
            "react_answer": completed_answers[-1] if completed_answers else "",
        }

    def _answer(self, state: WorkflowState) -> WorkflowState:
        request = state["request"]
        evidence = state.get("evidence", [])
        stop_reason = state.get("stop_reason", "completed")
        if stop_reason != "completed":
            review_required = stop_reason == "human_review"
            trace = [*state.get("trace", [])]
            trace.append(
                TraceEvent(
                    stage="review" if review_required else "answer",
                    title=(
                        "Human review required"
                        if review_required
                        else "Bounded investigation safely stopped"
                    ),
                    summary=("No normal grounded answer was published after the control stop."),
                    details={
                        "stop_reason": stop_reason,
                        "review_required": review_required,
                    },
                )
            )
            response = ChatResponse(
                question=request.question,
                conversation_id=request.conversation_id,
                route=state["plan"].route,
                answer=public_stop_message(stop_reason),
                grounded=False,
                abstained=True,
                citations=[],
                trace=trace,
                evidence=evidence,
                graph_paths=state.get("graph_paths", []),
                applied_preferences=state.get("preferences", {}),
                evaluation={
                    "citation_coverage": 0.0,
                    "tool_steps": len(state.get("observations", [])),
                    "within_step_limit": (len(state.get("observations", [])) <= request.max_steps),
                    "stop_reason": stop_reason,
                    "review_required": review_required,
                    "elapsed_ms": state.get("react_elapsed_ms", 0),
                    "estimated_cost_usd": state.get("react_estimated_cost_usd", 0.0),
                },
            )
            return {"response": response, "trace": trace}
        answer_evidence = evidence
        if state["plan"].route == "graph_rag":
            direct_paths = [
                path for path in state.get("graph_paths", []) if path.depth == 1 and path.edges
            ]
            relationship_priority = {
                "AFFECTS": 0,
                "CHANGES_OR_CLARIFIES": 1,
                "REFERENCES": 2,
            }
            direct_paths.sort(
                key=lambda path: (
                    relationship_priority.get(path.edges[0].relationship_type, 99),
                    path.end_id,
                )
            )
            preferred_record_ids = list(
                dict.fromkeys(
                    [
                        *(path.start_id for path in direct_paths[:1]),
                        *(path.end_id for path in direct_paths),
                    ]
                )
            )
            evidence_by_record = {item.chunk.record_id: item for item in evidence}
            promoted = [
                evidence_by_record[record_id]
                for record_id in preferred_record_ids
                if record_id in evidence_by_record
            ]
            if promoted:
                promoted_chunks = {item.chunk.chunk_id for item in promoted}
                answer_evidence = [
                    *promoted,
                    *(item for item in evidence if item.chunk.chunk_id not in promoted_chunks),
                ]
        elif state["plan"].route == "rag":
            exact_evidence = [item for item in evidence if item.exact_id_match]
            if exact_evidence:
                answer_evidence = exact_evidence
        elif any(
            term in request.question.lower()
            for term in ("remain open", "open ncr", "quality", "blocked", "inspection")
        ):
            open_ncrs = sorted(
                (
                    item
                    for item in evidence
                    if item.chunk.metadata.get("record_type") == "ncr"
                    and item.chunk.metadata.get("status") == "open"
                ),
                key=lambda item: item.chunk.record_id,
            )
            if open_ncrs:
                answer_evidence = open_ncrs
        elif "activity" in request.question.lower():
            promoted_activity: EvidenceItem | None = None
            paths = sorted(state.get("graph_paths", []), key=lambda path: path.depth)
            retrieval_ranked = [
                item
                for item in evidence
                if any(
                    reason.startswith(("exact rank", "text rank", "dense rank", "model reranker:"))
                    for reason in item.reasons
                )
            ]
            activity_support = [
                *retrieval_ranked,
                *(item for item in evidence if item not in retrieval_ranked),
            ]
            for ranked_item in activity_support:
                for path in paths:
                    path_ids = {node.record_id for node in path.nodes}
                    if ranked_item.chunk.record_id not in path_ids:
                        continue
                    activity_ids = [
                        node.record_id
                        for node in path.nodes
                        if node.record_type == "schedule_activity"
                    ]
                    promoted_activity = next(
                        (item for item in evidence if item.chunk.record_id in activity_ids),
                        None,
                    )
                    if promoted_activity:
                        break
                if promoted_activity:
                    break
            if promoted_activity:
                answer_evidence = [
                    promoted_activity,
                    *(
                        item
                        for item in evidence
                        if item.chunk.chunk_id != promoted_activity.chunk.chunk_id
                    ),
                ]
        answer_style = state.get("preferences", {}).get("answer_style", "plain_language")
        statement_limits = {"concise": 2, "plain_language": 3, "detailed": 6}
        standards_observation = next(
            (
                observation
                for observation in state.get("observations", [])
                if observation.tool_name == "assess_standard_evidence"
                and observation.data.get("report")
            ),
            None,
        )
        if standards_observation is not None:
            result = standards_report_answer(
                StandardEvidenceReport.model_validate(standards_observation.data["report"])
            )
        else:
            result = self.answers.answer(
                EvidencePacket(
                    question=request.question,
                    evidence=answer_evidence,
                    retrieval_trace=RetrievalTrace(returned_evidence=len(answer_evidence)),
                ),
                max_statements=statement_limits.get(answer_style, 3),
            )
        trace = [*state.get("trace", [])]
        trace.append(
            TraceEvent(
                stage="answer",
                title="Grounded answer assembled",
                summary=(
                    "Every displayed claim is tied to a citation."
                    if not result.abstained
                    else "The workflow abstained because permitted evidence was insufficient."
                ),
                details={
                    "citation_count": len(result.citations),
                    "abstained": result.abstained,
                },
            )
        )
        response = ChatResponse(
            question=request.question,
            conversation_id=request.conversation_id,
            route=state["plan"].route,
            answer=result.answer,
            grounded=result.grounded,
            abstained=result.abstained,
            citations=result.citations,
            trace=trace,
            evidence=evidence,
            graph_paths=state.get("graph_paths", []),
            applied_preferences=state.get("preferences", {}),
            evaluation={
                "citation_coverage": 1.0 if result.grounded else 0.0,
                "tool_steps": len(state.get("observations", [])),
                "within_step_limit": len(state.get("observations", [])) <= request.max_steps,
                "stop_reason": state.get("stop_reason", "completed"),
                "elapsed_ms": state.get("react_elapsed_ms", 0),
                "estimated_cost_usd": state.get("react_estimated_cost_usd", 0.0),
                "review_required": False,
            },
        )
        return {"response": response, "trace": trace}

    def invoke(self, request: ChatRequest) -> ChatResponse:
        with self.tracing.run(
            "civil-copilot-workflow",
            {
                "question": request.question,
                "project_id": request.project_id,
                "user_id": request.user_id,
            },
        ) as trace_run:
            response = self._invoke_scoped(request)
        return response.model_copy(update={"trace_reference": trace_run.reference})

    def _invoke_scoped(self, request: ChatRequest) -> ChatResponse:
        trace: list[TraceEvent] = []
        preferences: dict[str, str] = {}
        try:
            preferences = self.memory.get(request.user_id, request.project_id)
            trace.append(
                TraceEvent(
                    stage="memory",
                    title="Loaded safe user preferences",
                    summary=f"Loaded {len(preferences)} allowlisted preference(s).",
                    details={"preferences": preferences},
                )
            )
        except Exception as error:
            trace.append(
                TraceEvent(
                    stage="memory",
                    title="Preference memory unavailable",
                    summary="Continued without saved preferences.",
                    details={"error_type": type(error).__name__},
                )
            )
        preferred_route = preferences.get("preferred_route")
        effective_request = request
        if not request.route_override and preferred_route and preferred_route != "auto":
            effective_request = request.model_copy(update={"route_override": preferred_route})
        with self.tracing.span(
            "civil-copilot-question",
            {
                "question": request.question,
                "project_id": request.project_id,
                "user_id": request.user_id,
            },
        ) as span:
            final = self.graph.invoke(
                {
                    "request": effective_request,
                    "preferences": preferences,
                    "trace": trace,
                }
            )
            response = final["response"]
            if span:
                span.update(
                    output=redact_trace_payload(
                        {
                            "route": response.route,
                            "grounded": response.grounded,
                            "abstained": response.abstained,
                            "citation_ids": [citation.record_id for citation in response.citations],
                        }
                    )
                )
        self.tracing.flush()
        return response
