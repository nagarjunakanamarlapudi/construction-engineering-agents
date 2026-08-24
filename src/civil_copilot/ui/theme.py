"""Visual system for the Streamlit Project Command Center."""

APP_CSS = """
<style>
  :root {
    --navy-950: #0b1728;
    --navy-900: #102139;
    --slate-900: #172033;
    --slate-700: #344054;
    --slate-500: #667085;
    --line: #dce3ec;
    --canvas: #f4f7fb;
    --blue: #2767d8;
    --blue-soft: #eaf1ff;
    --green-soft: #e9f7f1;
    --orange-soft: #fff2d8;
  }

  .stApp { background: var(--canvas); }
  [data-testid="stHeader"] { background: rgba(244, 247, 251, .92); }
  [data-testid="stMainBlockContainer"] { max-width: 1480px; padding-top: 1.3rem; }
  [data-testid="stAppViewContainer"] { color: var(--slate-900); }
  [data-testid="stAppViewContainer"] h1,
  [data-testid="stAppViewContainer"] h2,
  [data-testid="stAppViewContainer"] h3,
  [data-testid="stAppViewContainer"] h4,
  [data-testid="stAppViewContainer"] p,
  [data-testid="stAppViewContainer"] label,
  [data-testid="stAppViewContainer"] [data-baseweb="tab"] { color: var(--slate-900); }

  [data-testid="stSidebar"] { background: var(--navy-950); }
  [data-testid="stSidebarContent"] { padding-top: .8rem; }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] h4,
  [data-testid="stSidebar"] h5,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label { color: #e8eef7 !important; }
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #aebbd0 !important; }
  [data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: #cbd5e1 !important;
  }
  [data-testid="stSidebar"] [data-baseweb="select"] span,
  [data-testid="stSidebar"] [data-baseweb="select"] input,
  [data-testid="stSidebar"] [data-baseweb="select"] svg { color: var(--slate-900) !important; }
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    min-height: 2.55rem;
    justify-content: flex-start;
    text-align: left;
    background: #ffffff;
    border: 1px solid #d6deea;
    color: var(--slate-900) !important;
    border-radius: 10px;
  }
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] p {
    color: var(--slate-900) !important;
    font-weight: 650;
  }
  [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
    background: var(--blue-soft);
    border-color: #79a2ed;
  }
  [data-testid="stSidebar"] details {
    border: 1px solid #253953;
    background: var(--navy-900);
    border-radius: 10px;
  }
  [data-testid="stSidebar"] details summary,
  [data-testid="stSidebar"] details summary p,
  [data-testid="stSidebar"] details summary svg { color: #f4f7fb !important; }
  [data-testid="stSidebar"] [data-testid="stForm"] { border: 0; padding: .25rem; }

  .sidebar-brand { display: flex; align-items: center; gap: .7rem;
    margin-bottom: 1rem; color: #fff; }
  .sidebar-brand strong { display: block; font-size: 1.05rem; }
  .sidebar-brand small { display: block; color: #9eb0c8; font-size: .76rem; margin-top: .1rem; }
  .brand-mark { width: 2.35rem; height: 2.35rem; border-radius: .7rem; display: flex;
    align-items: center; justify-content: center; background: #ffb12c; color: #15233a;
    font-weight: 900; box-shadow: 0 7px 18px rgba(245,158,11,.22); }
  .project-card { padding: .85rem; margin: 0 0 1.15rem; border-radius: .75rem;
    background: var(--navy-900); border: 1px solid #253953; }
  .project-card span { display:block; color:#8fa3be; font-size:.68rem; text-transform:uppercase;
    letter-spacing:.07em; font-weight:750; }
  .project-card strong { display:block; color:#fff; font-size:.86rem;
    line-height:1.35; margin:.35rem 0; }
  .project-card small { display:block; color:#adbbcd; font-size:.72rem; }
  .data-legend { border-top: 1px solid #25364d; margin-top: 1.2rem; padding-top: 1rem;
    color: #c4cfde; font-size: .72rem; line-height: 1.5; }
  .data-legend strong { display:block; color:#fff; font-size:.78rem; margin-bottom:.55rem; }
  .data-legend div { margin: .42rem 0; }
  .legend-dot { width:.48rem; height:.48rem; border-radius:50%;
    display:inline-block; margin-right:.45rem; }
  .legend-dot.synthetic { background:#f59e0b; }
  .legend-dot.public { background:#22c55e; }

  .command-header { display:flex; align-items:center; justify-content:space-between; gap:2rem;
    padding: 1.25rem 1.45rem; background: linear-gradient(125deg, #ffffff 0%, #f7faff 100%);
    border: 1px solid var(--line); border-radius: 18px; box-shadow:0 8px 28px rgba(16,33,57,.06); }
  .command-header h1 { margin:.22rem 0 .3rem; font-size:2rem; letter-spacing:-.035em; }
  .command-header p { margin:0; color:var(--slate-500) !important; }
  .command-eyebrow { color:var(--blue); font-size:.72rem; letter-spacing:.1em; font-weight:850;
    text-transform:uppercase; }
  .header-status { white-space:nowrap; padding:.5rem .7rem; background:var(--green-soft);
    color:#0e6c4b; border-radius:999px; font-size:.76rem; font-weight:750; }
  .header-status span { display:inline-block; width:.5rem; height:.5rem; border-radius:50%;
    background:#19a66a; margin-right:.35rem; box-shadow:0 0 0 3px rgba(25,166,106,.13); }

  [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:13px;
    padding:.75rem .85rem; box-shadow:0 3px 14px rgba(16,33,57,.035); }
  [data-testid="stMetricLabel"] p { color:var(--slate-500) !important; font-size:.75rem; }
  [data-testid="stMetricValue"] { color:var(--slate-900); font-weight:800; }
  [data-testid="stMetricDelta"] { font-size:.68rem; }
  [data-testid="stTabs"] [role="tablist"] { gap:.25rem; border-bottom:1px solid var(--line); }
  [data-testid="stTabs"] [role="tab"] { padding:.7rem .85rem; font-weight:700; }

  [data-testid="stMain"] [data-testid="stBaseButton-primary"] {
    background:var(--blue); border-color:var(--blue); border-radius:10px; font-weight:750; }
  [data-testid="stMain"] [data-testid="stBaseButton-primary"] p {
    color:#fff !important; }
  [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {
    background:#fff; border-color:#cbd5e1; color:var(--slate-900) !important; border-radius:10px; }
  [data-testid="stMain"] [data-testid="stBaseButton-secondary"] p {
    color:var(--slate-900) !important; }
  [data-testid="stMain"] [data-baseweb="select"] > div { background:#fff; border-color:#cbd5e1; }

  .empty-state { display:flex; flex-direction:column; gap:.35rem;
    align-items:center; text-align:center;
    padding:2.5rem 1rem; margin:.75rem 0 1rem; background:#fff; border:1px dashed #bdc9d9;
    border-radius:14px; color:var(--slate-500); }
  .empty-state strong { color:var(--slate-900); font-size:1rem; }
  .empty-state span { max-width:620px; font-size:.86rem; }
  .answer-status-row { display:flex; flex-wrap:wrap; gap:.45rem;
    align-items:center; margin:.2rem 0 .6rem; }
  .route-badge, .status-chip { display:inline-flex; align-items:center; padding:.34rem .62rem;
    border-radius:999px; font-size:.72rem; font-weight:750; }
  .route-badge { color:#244f99; background:var(--blue-soft); }
  .status-chip { color:#475467; background:#eef2f6; }
  .finding-card { padding:1rem 1.05rem; background:#fff; border:1px solid #cfd9e7;
    border-left:4px solid var(--blue); border-radius:10px; color:#243148; font-size:.96rem;
    line-height:1.58; box-shadow:0 4px 16px rgba(16,33,57,.04); }
  .evidence-card { min-height:132px; padding:.85rem; margin:.2rem 0 .65rem; background:#fff;
    border:1px solid var(--line); border-radius:11px; }
  .origin-public, .origin-synthetic { display:inline-block; font-size:.62rem; font-weight:850;
    letter-spacing:.05em; padding:.22rem .4rem; border-radius:999px; }
  .origin-public { color:#087443; background:var(--green-soft); }
  .origin-synthetic { color:#995b00; background:var(--orange-soft); }
  .evidence-id { color:var(--slate-900); font-size:.82rem;
    font-weight:850; margin:.55rem 0 .15rem; }
  .evidence-title { color:var(--slate-500); font-size:.74rem; line-height:1.4; min-height:2.1rem; }
  .evidence-card a { color:var(--blue); font-size:.72rem; font-weight:750; text-decoration:none; }

  [data-testid="stMain"] details { background:#fff;
    border:1px solid var(--line); border-radius:10px; }
  [data-testid="stMain"] details summary,
  [data-testid="stMain"] details summary p,
  [data-testid="stMain"] details summary span,
  [data-testid="stMain"] details summary svg { color:var(--slate-900) !important; }
  .revision-card { min-height:190px; padding:1rem; background:#fff; border:1px solid var(--line);
    border-radius:12px; box-shadow:0 4px 16px rgba(16,33,57,.04); }
  .revision-card span { display:block; color:var(--blue); font-size:.7rem; font-weight:800;
    text-transform:uppercase; letter-spacing:.04em; }
  .revision-card strong { display:block; margin:.35rem 0; color:var(--slate-900); }
  .revision-card small { color:var(--slate-500); }
  .revision-card p { color:var(--slate-700) !important; font-size:.82rem; line-height:1.48; }
  .quality-note { padding:.85rem 1rem; background:#fff;
    border:1px solid var(--line); border-radius:11px;
    color:var(--slate-500); font-size:.8rem; line-height:1.45; }
  .quality-note strong { display:block; color:var(--slate-900); margin-bottom:.2rem; }
  .quality-row { display:grid; grid-template-columns:120px 1fr auto; gap:1rem; align-items:center;
    padding:.8rem 1rem; margin:.45rem 0; background:#fff;
    border:1px solid var(--line); border-radius:10px; }
  .quality-row strong { color:#a13f28; }
  .quality-row span { color:var(--slate-700); font-size:.82rem; }
  .quality-row small { color:var(--slate-500); }
  .standards-row { padding:1rem 1.05rem; margin:.65rem 0; background:#fff;
    border:1px solid var(--line); border-radius:11px; box-shadow:0 3px 12px rgba(16,33,57,.035); }
  .standards-row-heading { display:flex; flex-wrap:wrap; align-items:flex-start; gap:.65rem; }
  .standards-row-heading strong { flex:1; min-width:260px; color:var(--slate-900);
    font-size:.88rem; line-height:1.45; }
  .standards-status { display:inline-flex; align-items:center; white-space:nowrap;
    padding:.26rem .48rem; border-radius:999px; font-size:.67rem; font-weight:850; }
  .standards-status.evidenced { color:#087443; background:var(--green-soft); }
  .standards-status.needs-review { color:#8a5200; background:var(--orange-soft); }
  .standards-status.not-evidenced { color:#9f2d20; background:#fdecec; }
  .standards-status.not-applicable { color:#475467; background:#eef2f6; }
  .standards-reason { margin:.62rem 0; color:var(--slate-700); font-size:.82rem;
    line-height:1.55; }
  .standards-sources { display:flex; flex-wrap:wrap; gap:.45rem 1.1rem; color:var(--slate-500);
    font-size:.72rem; line-height:1.45; }

  @media (max-width: 900px) {
    .command-header { align-items:flex-start; flex-direction:column; gap:.8rem; }
    .command-header h1 { font-size:1.6rem; }
    .quality-row { grid-template-columns:1fr; gap:.2rem; }
  }
</style>
"""

ROUTE_LABELS = {
    "auto": "Auto — choose the simplest sufficient route",
    "rag": "RAG — find relevant passages",
    "graph_rag": "Graph RAG — follow project connections",
    "agentic_rag": "Agentic RAG — plan and use several tools",
}
