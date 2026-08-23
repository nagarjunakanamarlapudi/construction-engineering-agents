"""Small visual system for the Streamlit demonstration UI."""

APP_CSS = """
<style>
  .stApp { background: linear-gradient(145deg, #f8fbff 0%, #f7f4ff 55%, #f4fff9 100%); }
  [data-testid="stAppViewContainer"] { color: #172033; }
  [data-testid="stAppViewContainer"] h1,
  [data-testid="stAppViewContainer"] h2,
  [data-testid="stAppViewContainer"] h3,
  [data-testid="stAppViewContainer"] p,
  [data-testid="stAppViewContainer"] label,
  [data-testid="stAppViewContainer"] [data-baseweb="tab"] { color: #172033 !important; }
  [data-testid="stSidebar"] { background: #111827; color: #f8fafc; }
  [data-testid="stSidebar"] * { color: #f8fafc !important; }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] span { color: #f8fafc !important; }
  [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {
    background: #ffffff;
    border-color: #cbd5e1;
    color: #172033 !important;
  }
  [data-testid="stMain"] [data-testid="stBaseButton-secondary"] p {
    color: #172033 !important;
  }
  [data-testid="stMain"] [data-testid="stBaseButton-secondary"]:hover {
    background: #eef2ff;
    border-color: #818cf8;
  }
  [data-testid="stMain"] details summary,
  [data-testid="stMain"] details summary p,
  [data-testid="stMain"] details summary span { color: #f8fafc !important; }
  .hero { padding: 1.2rem 1.35rem; border: 1px solid #dbeafe; border-radius: 20px;
          background: rgba(255,255,255,.86); box-shadow: 0 12px 35px rgba(30,64,175,.08); }
  .hero h1 { color: #111827 !important; margin: .3rem 0 .45rem; }
  .hero p { color: #475569 !important; }
  .eyebrow { color: #6d28d9; font-weight: 750; letter-spacing: .08em; font-size: .78rem; }
  .route-badge { display: inline-block; padding: .3rem .65rem; border-radius: 999px;
                 color: #312e81; background: #e0e7ff; font-weight: 750; margin-bottom: .6rem; }
  .origin-public { color: #166534; font-weight: 700; }
  .origin-synthetic { color: #9a3412; font-weight: 700; }
  .metric-card { padding: .8rem; border-radius: 14px; background: white;
                 border: 1px solid #e5e7eb; }
  .small-note { color: #64748b; font-size: .88rem; }
</style>
"""

ROUTE_LABELS = {
    "auto": "Auto — choose the simplest sufficient route",
    "rag": "RAG — retrieve passages and answer",
    "graph_rag": "Graph RAG — follow project relationships",
    "agentic_rag": "Agentic RAG — plan and use several tools",
}
