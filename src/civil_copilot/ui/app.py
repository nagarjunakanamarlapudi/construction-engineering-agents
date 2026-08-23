"""ChatGPT-style demonstration UI with visible plans, tools, evidence, and evaluations."""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from civil_copilot.ui.theme import APP_CSS, ROUTE_LABELS

API_BASE = os.getenv("COPILOT_API_URL", "http://127.0.0.1:8001")
DEMO_USER_ID = "demo-presenter"

st.set_page_config(
    page_title="Civil Engineering Project Copilot",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(APP_CSS, unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_scenarios() -> list[dict[str, Any]]:
    try:
        return httpx.get(f"{API_BASE}/api/scenarios", timeout=5).json()
    except (httpx.HTTPError, ValueError):
        return []


def ask(question: str, route_override: str | None) -> dict[str, Any]:
    response = httpx.post(
        f"{API_BASE}/api/chat",
        json={
            "question": question,
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
    route = response["route"].replace("_", " ").title()
    st.markdown(f'<span class="route-badge">Route · {route}</span>', unsafe_allow_html=True)
    if response.get("applied_preferences"):
        preferences = ", ".join(
            f"{name.replace('_', ' ')}: {value}"
            for name, value in response["applied_preferences"].items()
        )
        st.caption(f"Preference Memory applied · {preferences}")
    st.markdown(response["answer"])
    if response.get("abstained"):
        st.warning("The Copilot stopped because the permitted sources did not support an answer.")

    trace_tab, evidence_tab, graph_tab, evaluation_tab = st.tabs(
        ["Plan & tool trace", "Evidence & citations", "Project graph", "Evaluation"]
    )
    with trace_tab:
        st.caption("Structured execution summary—not hidden chain-of-thought.")
        for event in response.get("trace", []):
            with st.expander(f"{event['stage'].upper()} · {event['title']}", expanded=True):
                st.write(event["summary"])
                if event.get("details"):
                    st.json(event["details"])

    with evidence_tab:
        if not response.get("citations"):
            st.info("No evidence was accepted for this answer.")
        for citation in response.get("citations", []):
            origin = citation["data_origin"]
            if origin == "synthetic_academic_demo":
                origin_label = "SYNTHETIC — ACADEMIC DEMO"
                css_class = "origin-synthetic"
            else:
                origin_label = "Official public preview"
                css_class = "origin-public"
            st.markdown(f"### {citation['record_id']} · {citation['title']}")
            st.markdown(f'<span class="{css_class}">{origin_label}</span>', unsafe_allow_html=True)
            source = citation.get("source_url") or (
                f"{API_BASE}/api/records/{citation['record_id']}"
            )
            st.markdown(f"Source: [{source}]({source})")
        if response.get("applied_preferences", {}).get("citation_detail") != "compact":
            with st.expander("Ranking and reranking evidence details"):
                st.json(response.get("evidence", []))

    with graph_tab:
        paths = response.get("graph_paths", [])
        if not paths:
            st.info("This route did not need a graph traversal.")
        for index, path in enumerate(paths[:12], start=1):
            node_chain = " → ".join(node["record_id"] for node in path["nodes"])
            relation_chain = " · ".join(edge["relationship_type"] for edge in path["edges"])
            st.markdown(f"**Path {index}:** `{node_chain}`")
            st.caption(f"Relationships: {relation_chain}")

    with evaluation_tab:
        evaluation = response.get("evaluation", {})
        columns = st.columns(max(len(evaluation), 1))
        for column, (name, value) in zip(columns, evaluation.items(), strict=False):
            column.metric(name.replace("_", " ").title(), value)


with st.sidebar:
    st.markdown("## 🏗️ Project Copilot")
    st.caption("Indian structural-steel academic demonstration")
    st.markdown("**Data in this demo**")
    st.markdown("🟠 SYNTHETIC — ACADEMIC DEMO project records")
    st.markdown("🟢 Official public preview and catalogue material")
    st.divider()
    route_choice = st.selectbox("Route", options=list(ROUTE_LABELS), format_func=ROUTE_LABELS.get)
    st.caption("Auto makes the routing decision visible. Overrides help compare approaches.")
    st.divider()
    with st.expander("Preference Memory", expanded=False):
        st.caption(
            "Mem0 stores only your display and route preferences—not project facts or answers."
        )
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
                st.success("Safe preferences saved. They will be shown on the next answer.")
            except httpx.HTTPError as error:
                st.error(f"Preference memory is unavailable: {error}")
    st.divider()
    st.markdown("### Try a guided scenario")
    selected_scenario = None
    for scenario in load_scenarios():
        if st.button(scenario.get("title") or scenario["scenario_id"], width="stretch"):
            selected_scenario = scenario["question"]

st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">EVIDENCE-FIRST PROJECT INTELLIGENCE</div>
      <h1>Civil Engineering Project Copilot</h1>
      <p>Ask what happened, what changed, what is connected, and why—then inspect the route,
      tools, project paths, and sources behind the answer.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

chat_tab, impact_tab, revision_tab, quality_tab = st.tabs(
    [
        "💬 Copilot Chat",
        "🕸️ Impact Explorer",
        "📝 Revision & Evidence Lab",
        "✅ Quality Control Room",
    ]
)

with chat_tab:
    st.subheader("Copilot Chat")
    st.caption("Ask freely or launch a guided scenario from the sidebar.")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                render_response(message["content"])
            else:
                st.markdown(message["content"])

    prompt = selected_scenario or st.chat_input(
        "Ask about an RFI, drawing change, delay, material, weld, NCR, or code register…"
    )
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                with st.spinner("Retrieving evidence and following the approved route…"):
                    selected_route = None if route_choice == "auto" else route_choice
                    result = ask(prompt, selected_route)
                render_response(result)
                st.session_state.messages.append({"role": "assistant", "content": result})
            except (httpx.HTTPError, ValueError) as error:
                st.error(f"The local API is unavailable or returned an invalid response: {error}")

with impact_tab:
    st.subheader("Impact Explorer")
    st.write(
        "Start from one project record, inspect its verified upstream and downstream links, "
        "then let Graph RAG assemble the evidence behind the path."
    )
    impact_root = st.selectbox(
        "Starting record",
        ["RFI-087", "ACT-STEEL-009", "PIECE-C001", "NCR-005"],
        key="impact_root",
    )
    inspect_column, investigate_column = st.columns(2)
    if inspect_column.button("Show verified paths", width="stretch"):
        try:
            st.session_state.impact_paths = get_json(f"/api/graph/{impact_root}?max_depth=3")
        except httpx.HTTPError as error:
            st.error(str(error))
    if investigate_column.button("Run Graph RAG investigation", width="stretch"):
        st.session_state.impact_answer = ask(
            f"Trace the upstream and downstream impact of {impact_root} and cite every "
            "supporting record.",
            "graph_rag",
        )
    if st.session_state.get("impact_paths"):
        paths = st.session_state.impact_paths["paths"]
        st.metric("Provenance-backed paths", len(paths))
        st.dataframe(
            [
                {
                    "path": " → ".join(node["record_id"] for node in path["nodes"]),
                    "relationships": " · ".join(
                        edge["relationship_type"] for edge in path["edges"]
                    ),
                    "depth": len(path["edges"]),
                }
                for path in paths
            ],
            width="stretch",
            hide_index=True,
        )
    if st.session_state.get("impact_answer"):
        render_response(st.session_state.impact_answer)

with revision_tab:
    st.subheader("Revision & Evidence Lab")
    st.write(
        "Compare controlled drawing revisions and ask the agent to connect the change back to "
        "the RFI, decision, calculation, and affected activity."
    )
    drawing_number = st.selectbox("Drawing", ["S-204", "S-201", "S-208"], key="drawing")
    try:
        comparison = get_json(f"/api/compare/{drawing_number}")
        st.dataframe(
            [
                {
                    "record": record["record_id"],
                    "revision": record["revision"],
                    "status": record["status"],
                    "effective": record["effective_date"],
                    "summary": record["content"],
                }
                for record in comparison["revisions"]
            ],
            width="stretch",
            hide_index=True,
        )
    except httpx.HTTPError as error:
        st.info(f"Start the local API to load revision records: {error}")
    if st.button("Explain this change with evidence", width="stretch"):
        st.session_state.revision_answer = ask(
            f"What changed between {drawing_number} Rev 3 and Rev 5, why, and what "
            "activity was affected?",
            "agentic_rag",
        )
    if st.session_state.get("revision_answer"):
        render_response(st.session_state.revision_answer)

with quality_tab:
    st.subheader("Quality Control Room")
    st.write(
        "Review open non-conformances, then let the agent follow each failed inspection, weld, "
        "repair, reinspection, activity impact, and closure record."
    )
    try:
        open_ncrs = get_json("/api/records?record_type=ncr&status=open")
        st.metric("Open NCRs", len(open_ncrs))
        st.dataframe(
            [
                {
                    "NCR": record["record_id"],
                    "status": record["status"],
                    "effective": record["effective_date"],
                    "disposition": record["metadata"].get("disposition"),
                }
                for record in open_ncrs
            ],
            width="stretch",
            hide_index=True,
        )
    except httpx.HTTPError as error:
        st.info(f"Start the local API to load quality records: {error}")
    if st.button("Investigate open NCR closure chains", width="stretch"):
        st.session_state.quality_answer = ask(
            "Which weld inspections raised NCRs, and which remain open pending reinspection?",
            "agentic_rag",
        )
    if st.session_state.get("quality_answer"):
        render_response(st.session_state.quality_answer)
