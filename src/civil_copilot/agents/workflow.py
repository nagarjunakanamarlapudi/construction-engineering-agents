"""LangGraph orchestration with visible plans, bounded tools, and grounded answers."""

from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from civil_copilot.agents.router import QuestionRouter
from civil_copilot.agents.state import (
    ChatRequest,
    ChatResponse,
    RoutePlan,
    TraceEvent,
)
from civil_copilot.agents.tools import ProjectTools, ToolObservation, ToolRequest, identifiers_in
from civil_copilot.graph.service import GraphPath
from civil_copilot.memory.service import InMemoryPreferenceBackend, PreferenceMemory
from civil_copilot.observability.tracing import TracingBundle, redact_trace_payload
from civil_copilot.retrieval.answer import GroundedAnswerService
from civil_copilot.retrieval.evidence import EvidenceItem, EvidencePacket, RetrievalTrace
from civil_copilot.retrieval.rerank import rerank_score


class WorkflowState(TypedDict, total=False):
    request: ChatRequest
    plan: RoutePlan
    observations: list[ToolObservation]
    evidence: list[EvidenceItem]
    graph_paths: list[GraphPath]
    preferences: dict[str, str]
    trace: list[TraceEvent]
    response: ChatResponse


class CopilotWorkflow:
    def __init__(
        self,
        tools: ProjectTools,
        router: QuestionRouter | None = None,
        answers: GroundedAnswerService | None = None,
        tracing: TracingBundle | None = None,
        memory: PreferenceMemory | None = None,
    ) -> None:
        self.tools = tools
        self.router = router or QuestionRouter()
        self.answers = answers or GroundedAnswerService()
        self.tracing = tracing or TracingBundle(enabled=False)
        self.memory = memory or PreferenceMemory(InMemoryPreferenceBackend())
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
            return {"question": request.question, "top_k": 6}
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
                score, reasons = rerank_score(request.question, item.chunk, item.fused_score)
                evidence_by_chunk[item.chunk.chunk_id] = item.model_copy(
                    update={
                        "rerank_score": score,
                        "exact_id_match": item.chunk.record_id.upper() in request.question.upper(),
                        "reasons": list(dict.fromkeys([*item.reasons, *reasons])),
                    }
                )
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

    def _answer(self, state: WorkflowState) -> WorkflowState:
        request = state["request"]
        evidence = state.get("evidence", [])
        answer_evidence = evidence
        if state["plan"].route == "rag":
            exact_evidence = [item for item in evidence if item.exact_id_match]
            if exact_evidence:
                answer_evidence = exact_evidence
        elif "remain open" in request.question.lower() or "open ncr" in request.question.lower():
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
            for ranked_item in evidence:
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
                        (
                            item
                            for item in evidence
                            if item.chunk.record_id in activity_ids
                        ),
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
            },
        )
        return {"response": response, "trace": trace}

    def invoke(self, request: ChatRequest) -> ChatResponse:
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
                            "citation_ids": [
                                citation.record_id for citation in response.citations
                            ],
                        }
                    )
                )
        self.tracing.flush()
        return response
