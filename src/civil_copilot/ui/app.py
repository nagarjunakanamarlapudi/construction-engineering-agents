"""Streamlit command center for the Civil Engineering Project Copilot."""

from __future__ import annotations

import html
from typing import Any
from uuid import uuid4

import httpx
import streamlit as st

from civil_copilot.api.principal import DEFAULT_DEMO_USER_ID
from civil_copilot.config import Settings
from civil_copilot.ui.presenters import (
    build_answer_presentation,
    build_revision_preview,
    build_standard_matrix_rows,
    clean_indexed_text,
    humanize_token,
    normalize_scenarios,
    route_label,
)
from civil_copilot.ui.theme import APP_CSS, ROUTE_LABELS

API_BASE = Settings().api_base_url
PUBLIC_API_BASE = Settings().public_api_base_url
DEMO_USER_ID = DEFAULT_DEMO_USER_ID

st.set_page_config(
    page_title="Civil Engineering Project Copilot",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = f"ui-{uuid4().hex}"


@st.cache_data(ttl=30)
def load_scenarios() -> list[dict[str, Any]]:
    try:
        response = httpx.get(f"{API_BASE}/api/scenarios", timeout=5)
        response.raise_for_status()
        return normalize_scenarios(response.json())
    except (httpx.HTTPError, ValueError):
        return []


def ask(question: str, route_override: str | None) -> dict[str, Any]:
    response = httpx.post(
        f"{API_BASE}/api/chat",
        json={
            "question": question,
            "conversation_id": st.session_state.conversation_id,
            "user_id": DEMO_USER_ID,
            "route_override": route_override,
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


def get_json(path: str) -> Any:
    response = httpx.get(f"{API_BASE}{path}", timeout=15)
    response.raise_for_status()
    return response.json()


def save_preference(preference_type: str, value: str) -> None:
    response = httpx.post(
        f"{API_BASE}/api/memory/{DEMO_USER_ID}",
        json={
            "project_id": "BLR-STEEL-DEMO",
            "preference_type": preference_type,
            "value": value,
        },
        timeout=30,
    )
    response.raise_for_status()


def render_response(response: dict[str, Any]) -> None:
    """Render the conclusion first and keep technical material available on demand."""

    presentation = build_answer_presentation(response)
    route = route_label(response["route"])
    source_label = f"{presentation.source_count} cited source"
    if presentation.source_count != 1:
        source_label += "s"
    status_label = "Grounded" if presentation.grounded else "Needs review"

    st.markdown(
        (
            '<div class="answer-status-row">'
            f'<span class="route-badge">{html.escape(route)}</span>'
            f'<span class="status-chip">✓ {status_label}</span>'
            f'<span class="status-chip">◇ {source_label}</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    if response.get("applied_preferences"):
        preferences = ", ".join(
            f"{name.replace('_', ' ')}: {value.replace('_', ' ')}"
            for name, value in response["applied_preferences"].items()
        )
        st.caption(f"Preference Memory applied · {preferences}")

    if presentation.abstained:
        st.warning(presentation.finding)
        st.caption("The Copilot stopped because the permitted sources did not support an answer.")
    else:
        st.markdown("#### What we found")
        st.markdown(
            f'<div class="finding-card">{html.escape(presentation.finding)}</div>',
            unsafe_allow_html=True,
        )

        if presentation.explanation:
            st.markdown("#### Why")
            st.write(presentation.explanation)

        st.markdown("#### What is affected")
        if presentation.connections:
            for connection in presentation.connections:
                st.markdown(f"- {connection}")
        else:
            st.caption("No verified downstream relationship was needed for this answer.")

    st.markdown("#### Supporting evidence")
    citations = response.get("citations", [])
    if not citations:
        st.info("No evidence was accepted for this answer.")
    else:
        evidence_columns = st.columns(min(len(citations), 3))
        for index, citation in enumerate(citations):
            origin = citation["data_origin"]
            is_synthetic = origin == "synthetic_academic_demo"
            origin_label = (
                "SYNTHETIC — ACADEMIC DEMO" if is_synthetic else "Official public preview"
            )
            css_class = "origin-synthetic" if is_synthetic else "origin-public"
            source = citation.get("source_url") or (
                f"{PUBLIC_API_BASE}/api/records/{citation['record_id']}"
            )
            title = clean_indexed_text(citation["title"])
            with evidence_columns[index % len(evidence_columns)]:
                st.markdown(
                    (
                        '<div class="evidence-card">'
                        f'<span class="{css_class}">{html.escape(origin_label)}</span>'
                        f'<div class="evidence-id">{html.escape(citation["record_id"])}</div>'
                        f'<div class="evidence-title">{html.escape(title)}</div>'
                        f'<a href="{html.escape(source)}" target="_blank">Open source record ↗</a>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

    with st.expander("Investigation details", expanded=False):
        st.caption(
            "This is a structured execution summary of routing and tool activity—not hidden "
            "chain-of-thought."
        )
        trace_tab, evidence_tab, graph_tab, evaluation_tab = st.tabs(
            ["Plan & tool trace", "Evidence & citations", "Project graph", "Evaluation"]
        )
        with trace_tab:
            for event in response.get("trace", []):
                icon = {
                    "memory": "◇",
                    "route": "↗",
                    "plan": "☷",
                    "tool": "⚙",
                    "evidence": "⌕",
                    "answer": "✓",
                    "safety": "⚑",
                }.get(event["stage"], "•")
                event_title = event["title"].replace("Rag", "RAG")
                with st.expander(f"{icon} {event_title}", expanded=False):
                    st.write(event["summary"])
                    if event.get("details"):
                        st.json(event["details"])

        with evidence_tab:
            if response.get("applied_preferences", {}).get("citation_detail") != "compact":
                st.caption("Ranking and reranking details used to select the displayed evidence.")
                st.json(response.get("evidence", []))
            else:
                st.caption("Detailed ranking evidence is hidden by your saved compact preference.")

        with graph_tab:
            paths = response.get("graph_paths", [])
            if not paths:
                st.info("This answer did not require a project-graph search.")
            for index, path in enumerate(paths[:8], start=1):
                node_chain = " → ".join(node["record_id"] for node in path["nodes"])
                relation_chain = " · ".join(
                    edge["relationship_type"].replace("_", " ").title() for edge in path["edges"]
                )
                st.markdown(f"**Connection {index}:** `{node_chain}`")
                st.caption(f"Relationship: {relation_chain}")

        with evaluation_tab:
            evaluation = response.get("evaluation", {})
            columns = st.columns(max(len(evaluation), 1))
            for column, (name, value) in zip(columns, evaluation.items(), strict=False):
                column.metric(name.replace("_", " ").title(), value)


scenarios = load_scenarios()

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
          <div class="brand-mark">CC</div>
          <div><strong>Project Copilot</strong><small>Command Center</small></div>
        </div>
        <div class="project-card">
          <span>Current project</span>
          <strong>Bengaluru Logistics Steel Building</strong>
          <small>Structural steel · Academic demonstration</small>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### Retrieval route")
    route_choice = st.selectbox(
        "Route",
        options=list(ROUTE_LABELS),
        format_func=ROUTE_LABELS.get,
        label_visibility="collapsed",
    )
    st.caption("Auto selects the simplest route that can answer with evidence.")

    st.markdown("##### Try a guided scenario")
    selected_scenario = None
    for scenario in scenarios:
        if st.button(
            scenario.get("title") or scenario["scenario_id"],
            key=f"scenario-{scenario['scenario_id']}",
            width="stretch",
        ):
            selected_scenario = scenario["question"]

    with st.expander("Preference Memory", expanded=False):
        st.caption("Mem0 stores only display and routing preferences—not project facts or answers.")
        with st.form("memory_preferences"):
            memory_style = st.selectbox(
                "Answer style",
                ["plain_language", "concise", "detailed"],
                format_func=lambda value: value.replace("_", " ").title(),
            )
            memory_citations = st.selectbox(
                "Citation detail", ["expanded", "compact"], format_func=str.title
            )
            memory_route = st.selectbox(
                "Preferred route",
                list(ROUTE_LABELS),
                format_func=ROUTE_LABELS.get,
                key="memory_route",
            )
            remember = st.form_submit_button("Remember preferences", width="stretch")
        if remember:
            try:
                save_preference("answer_style", memory_style)
                save_preference("citation_detail", memory_citations)
                save_preference("preferred_route", memory_route)
                st.success("Preferences saved for the next answer.")
            except httpx.HTTPError as error:
                st.error(f"Preference memory is unavailable: {error}")

    st.markdown(
        """
        <div class="data-legend">
          <strong>Data in this demonstration</strong>
          <div><i class="legend-dot synthetic"></i>SYNTHETIC — ACADEMIC DEMO project records</div>
          <div><i class="legend-dot public"></i>Official public preview and catalogue material</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="command-header">
      <div>
        <span class="command-eyebrow">Project Command Center</span>
        <h1>Civil Engineering Project Copilot</h1>
        <p>Ask a project question, see the conclusion first, and inspect the evidence behind it.</p>
      </div>
      <div class="header-status"><span></span>Local services connected</div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_a, metric_b, metric_c, metric_d = st.columns(4)
metric_a.metric("Guided investigations", len(scenarios), "Ready")
metric_b.metric("Retrieval approaches", 3, "RAG · Graph · Agentic")
metric_c.metric("Source types", 2, "Public + synthetic")
metric_d.metric("Answer policy", "Grounded", "Citations required")

st.markdown("### Project workspaces")
chat_tab, impact_tab, revision_tab, quality_tab = st.tabs(
    [
        "💬 Copilot Chat",
        "🕸️ Impact Explorer",
        "📝 Revision & Evidence Lab",
        "✅ Quality Control Room",
    ]
)

with chat_tab:
    st.markdown("## Copilot Chat")
    st.caption("Ask freely or select a guided investigation from the sidebar.")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        st.markdown(
            """
            <div class="empty-state">
              <strong>Start with a real project question</strong>
              <span>Try an RFI decision, a delayed activity, a drawing revision, material
              traceability, or an open quality issue.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_response(message["content"])
            else:
                st.markdown(message["content"])

    prompt = selected_scenario or st.chat_input(
        "Ask about an RFI, delay, drawing change, material, weld, NCR, or Indian code record…"
    )
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Finding and checking the supporting project records…"):
                    selected_route = None if route_choice == "auto" else route_choice
                    result = ask(prompt, selected_route)
                render_response(result)
                st.session_state.messages.append({"role": "assistant", "content": result})
            except (httpx.HTTPError, ValueError) as error:
                st.error(f"The local API is unavailable or returned an invalid response: {error}")

with impact_tab:
    st.markdown("## Impact Explorer")
    st.caption(
        "Choose one project record to see what it affects, why those items are connected, "
        "and which records prove the connection."
    )
    impact_root = st.selectbox(
        "Starting project record",
        ["RFI-087", "ACT-STEEL-009", "PIECE-C001", "NCR-005"],
        key="impact_root",
    )
    if st.button("Run impact investigation", type="primary", width="stretch"):
        try:
            with st.spinner("Following verified project connections…"):
                st.session_state.impact_paths = get_json(f"/api/graph/{impact_root}?max_depth=3")
                st.session_state.impact_answer = ask(
                    f"What is the impact of {impact_root}, why are those project items "
                    "affected, and which records support the conclusion?",
                    "graph_rag",
                )
        except httpx.HTTPError as error:
            st.error(f"The impact investigation could not run: {error}")

    if st.session_state.get("impact_answer"):
        render_response(st.session_state.impact_answer)
    else:
        st.info(
            "The result will start with the impact and its cause. Graph paths and raw records "
            "will remain available under Investigation details."
        )

    if st.session_state.get("impact_paths"):
        paths = st.session_state.impact_paths["paths"]
        with st.expander(f"View all {len(paths)} verified connection paths", expanded=False):
            st.dataframe(
                [
                    {
                        "Connected records": " → ".join(
                            node["record_id"] for node in path["nodes"]
                        ),
                        "Why they are connected": " · ".join(
                            edge["relationship_type"].replace("_", " ").title()
                            for edge in path["edges"]
                        ),
                        "Steps": len(path["edges"]),
                    }
                    for path in paths
                ],
                width="stretch",
                hide_index=True,
            )

with revision_tab:
    st.markdown("## Revision & Evidence Lab")
    st.caption(
        "Compare a superseded drawing with the current revision, then explain what changed, "
        "why it changed, and which activity was affected."
    )
    drawing_number = st.selectbox("Drawing", ["S-204", "S-201", "S-208"], key="drawing")
    st.markdown("#### What changed")
    try:
        comparison = get_json(f"/api/compare/{drawing_number}")
        previews = [build_revision_preview(record) for record in comparison["revisions"]]
        revision_columns = st.columns(max(len(previews), 1))
        for column, preview in zip(revision_columns, previews, strict=False):
            with column:
                st.markdown(
                    (
                        '<div class="revision-card">'
                        f"<span>Revision {html.escape(preview.revision)} · "
                        f"{html.escape(preview.status)}</span>"
                        f"<strong>{html.escape(preview.record_id)}</strong>"
                        f"<small>Effective {html.escape(preview.effective_date)}</small>"
                        f"<p>{html.escape(preview.summary)}</p>"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
    except httpx.HTTPError as error:
        st.info(f"Start the local API to load revision records: {error}")

    if st.button("Explain this revision with evidence", type="primary", width="stretch"):
        try:
            with st.spinner("Comparing revisions and checking linked project records…"):
                st.session_state.revision_answer = ask(
                    f"What changed between {drawing_number} Rev 3 and Rev 5, why did it "
                    "change, and what activity was affected?",
                    "agentic_rag",
                )
        except httpx.HTTPError as error:
            st.error(f"The revision investigation could not run: {error}")
    if st.session_state.get("revision_answer"):
        render_response(st.session_state.revision_answer)

with quality_tab:
    st.markdown("## Quality Control Room")
    st.caption(
        "Review open non-conformances and follow each issue through inspection, repair, "
        "reinspection, schedule impact, and closure evidence."
    )
    try:
        open_ncrs = get_json("/api/records?record_type=ncr&status=open")
        quality_metric, quality_context = st.columns([1, 3])
        quality_metric.metric("Open NCRs", len(open_ncrs))
        with quality_context:
            st.markdown(
                """
                <div class="quality-note"><strong>What the investigation answers</strong>
                Which inspection failed, what must happen next, what work is affected, and
                whether closure evidence exists.</div>
                """,
                unsafe_allow_html=True,
            )
        for record in open_ncrs:
            raw_disposition = record["metadata"].get("disposition")
            disposition = (
                humanize_token(raw_disposition) if raw_disposition else "Disposition pending"
            )
            st.markdown(
                (
                    '<div class="quality-row">'
                    f"<strong>{html.escape(record['record_id'])}</strong>"
                    f"<span>{html.escape(disposition)}</span>"
                    f"<small>Effective {html.escape(str(record['effective_date']))}</small>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
    except httpx.HTTPError as error:
        st.info(f"Start the local API to load quality records: {error}")

    if st.button("Investigate open NCR closure chains", type="primary", width="stretch"):
        try:
            with st.spinner("Checking inspections, NCRs, repair, and reinspection records…"):
                st.session_state.quality_answer = ask(
                    "Which weld inspections raised NCRs, which remain open, why are they "
                    "still open, and what work is affected?",
                    "agentic_rag",
                )
        except httpx.HTTPError as error:
            st.error(f"The quality investigation could not run: {error}")
    if st.session_state.get("quality_answer"):
        render_response(st.session_state.quality_answer)

    st.divider()
    st.markdown("### Standards Evidence Review")
    st.caption(
        "Compare the project records with topics that are actually visible in an official "
        "BIS public preview. This is an evidence check, not a compliance certificate."
    )
    selected_standard = st.selectbox(
        "Indian standard",
        ["IS 800:2007"],
        key="standards_evidence_standard",
    )
    st.markdown(
        "🟠 **Project evidence:** synthetic academic demo records &nbsp;&nbsp; "
        "🟢 **Standard source:** official BIS public preview"
    )
    if st.button("Run standards evidence review", type="primary", width="stretch"):
        try:
            with st.spinner("Comparing the project records with the indexed public preview…"):
                st.session_state.standards_report = get_json(
                    f"/api/standards/evidence?standard={selected_standard}"
                )
                st.session_state.standards_answer = ask(
                    "Compare this project's structural-steel practices with the indexed IS 800 "
                    "preview. What is evidenced, not evidenced, and needs review?",
                    "agentic_rag",
                )
        except httpx.HTTPError as error:
            st.error(f"The standards evidence review could not run: {error}")

    standards_report = st.session_state.get("standards_report")
    if standards_report:
        matrix_rows = build_standard_matrix_rows(standards_report)
        status_counts = {
            status: sum(row.status == status for row in matrix_rows)
            for status in ("Evidenced", "Needs review", "Not evidenced", "Not applicable")
        }
        status_columns = st.columns(4)
        for column, (status, count) in zip(status_columns, status_counts.items(), strict=True):
            column.metric(status, count)
        st.markdown("#### Evidence matrix")
        status_classes = {
            "Evidenced": "evidenced",
            "Needs review": "needs-review",
            "Not evidenced": "not-evidenced",
            "Not applicable": "not-applicable",
        }
        for row in matrix_rows:
            status_class = status_classes[row.status]
            st.markdown(
                (
                    '<div class="standards-row">'
                    '<div class="standards-row-heading">'
                    f'<span class="standards-status {status_class}">'
                    f"{html.escape(row.status)}</span>"
                    f"<strong>{html.escape(row.topic)}</strong>"
                    "</div>"
                    f'<div class="standards-reason">{html.escape(row.reason)}</div>'
                    '<div class="standards-sources">'
                    "<span>🟠 Project evidence (synthetic): "
                    f"{html.escape(', '.join(row.project_sources))}</span>"
                    "<span>🟢 BIS source (official preview): "
                    f"{html.escape(row.official_source)}</span>"
                    "</div></div>"
                ),
                unsafe_allow_html=True,
            )
        st.warning(standards_report["limitation"])
        if st.session_state.get("standards_answer"):
            with st.expander("View the agent investigation and citations", expanded=False):
                render_response(st.session_state.standards_answer)
