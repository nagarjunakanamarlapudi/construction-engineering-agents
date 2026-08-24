# Demo Story — From One Project Question to Verifiable Evidence

This script is designed for an 8–12 minute academic demonstration. It works for a construction professional, software reviewer, sponsor, or Agentic AI course evaluator.

## Before the audience arrives

```bash
make services-up
make observability-up
make ingest
make health
make api
```

Run `make ui` in a second terminal and open <http://127.0.0.1:8501>. Keep Langfuse open at <http://127.0.0.1:3000> in another tab.

## 1. Set the scene — 45 seconds

Say:

> A construction project is not one document. A drawing revision may answer an RFI, block a schedule activity, change a fabricated piece, and later appear in an inspection or handover record. This Copilot finds the evidence and follows those links. It never hides whether the source is public or synthetic.

Point to the two source labels in the sidebar:

- green means official public preview/catalogue or sample material;
- orange means `SYNTHETIC — ACADEMIC DEMO` project data.

Explain that BIS public previews are useful research inputs but are not presented as complete Indian Standards.

## 2. Direct RAG — one question, one lookup — 60 seconds

In **Copilot Chat**, leave the route on **Auto** and click **Exact record lookup**.

Question:

> What did RFI-087 decide, and which drawing revision contains the decision?

Expected result:

- route: `RAG`;
- one tool: `search_documents`;
- the answer states that plate PL-17B was required and incorporated into S-204 Rev 5;
- citation: RFI-087.

Open **Investigation details**, then **Plan & tool trace**, and say:

> The model proposed a route, but a guardrail reduced this to the smallest sufficient path: one search. The display is a structured execution summary, not hidden chain-of-thought.

Return to **Supporting evidence** to show the origin label and source link. Ranking details remain
available in **Investigation details → Evidence & citations**.

## 3. Graph RAG — follow the impact — 75 seconds

Open **Impact Explorer**, select `RFI-087`, and click **Run impact investigation**.

Expected result:

- a short **What we found** impact statement;
- a plain-language **Why** explanation;
- connected drawing and activity records under **What is affected**; and
- cited sources, with all verified paths available in the collapsed technical section.

Say:

> Similarity search can find documents that mention the RFI. Graph RAG answers a different question: what is connected to it, and through which verified relationship?

## 4. Agentic RAG — investigate a delay — 90 seconds

Return to **Copilot Chat** and click **Delay investigation**.

Question:

> Why is ACT-STEEL-009 delayed, and which records support the explanation?

Expected result:

- route: `Agentic RAG`;
- a conclusion-first answer stating why the activity was blocked;
- a bounded plan;
- schedule activity lookup;
- graph path traversal;
- drawing revision comparison;
- retrieved evidence and citations.

Say:

> One retrieval is not enough here. The workflow reads the named activity, follows its causes, compares the referenced revision, and answers only after checking the observations. Each tool is read-only and cannot alter the project.

## 5. Revision & Evidence Lab — show a non-chat experience — 75 seconds

Open **Revision & Evidence Lab** and select S-204. Review the two readable revision cards, then
click **Explain this revision with evidence**.

Expected result:

- Rev 3 and Rev 5 are displayed separately;
- the revision tool shows what changed;
- the investigation connects the change to RFI-087 and ACT-STEEL-009;
- the answer cites the affected records.

Say:

> Agentic capability does not have to look like a chatbot. Here the UI begins with a document-control task, but it still uses the same route, tools, graph, and evidence services.

## 6. Quality Control Room — investigate closure evidence — 75 seconds

Open **Quality Control Room**, review the open NCR cards, and click
**Investigate open NCR closure chains**.

Expected result:

- open NCR-005 and NCR-006 appear first;
- the tool trace is `query_quality_records` → `find_graph_paths` → `get_records`;
- the answer explains that repair and repeat inspections INSP-RECHECK-005 and INSP-RECHECK-006 are required;
- no accepted weld is presented as the unresolved problem.

Say:

> This scenario demonstrates why connected data matters. The answer must join an NCR, the rejected inspection, the weld, and the required reinspection. The test suite protects this ordering so accepted welds cannot accidentally lead the answer.

## 7. Standards Evidence — compare without overclaiming — 75 seconds

Stay in **Quality Control Room**, choose **IS 800:2007**, and click
**Run standards evidence review**.

Expected result:

- the matrix separates `Evidenced`, `Needs review`, and `Not evidenced` topics;
- every row cites synthetic project records and an official BIS preview chunk;
- the tool trace shows one bounded `assess_standard_evidence` action; and
- the page says plainly that a public preview cannot establish full compliance.

Say:

> This is an evidence comparison, not an engineering approval. The tool checks only the seven topics supported by the indexed IS 800 preview and our project records. Missing evidence means a reviewer should look for the record; it does not prove that the practice was not followed.

## 8. Memory — preferences, not project facts — 45 seconds

Open **Preference Memory** in the sidebar. Save `concise` as the answer style, then repeat a question.

Expected result:

- the UI says the preference was applied;
- the answer becomes shorter;
- project evidence still comes from the current databases and citations.

Say:

> Mem0 remembers how this reviewer prefers to see answers. It is deliberately blocked from storing project facts, retrieved passages, or old answers.

## 9. Evaluation and observability — 60 seconds

Open the answer's **Evaluation** tab, then switch to Langfuse.

Show:

- route and tool spans;
- number of evidence items and citations;
- latency and safe masked inputs;
- the seven-scenario evaluation report, including the IS 800 evidence comparison.

Say:

> A fluent answer is not enough. We test whether the correct evidence was retrieved, whether the route and tools were appropriate, whether every claim has a citation, and whether the system abstains when evidence is missing.

## 10. Close — 30 seconds

> The main result is not a general chatbot. It is a reproducible investigation system over a connected, clearly labelled civil-engineering dataset: fast RAG for simple questions, Graph RAG for relationships, and bounded Agentic RAG for multi-step work.

## Questions an evaluator may ask

**Why synthetic data?**  
Public standards metadata and IFC samples do not share one project's RFIs, schedule, materials, inspections, and revisions. The labelled synthetic layer provides that correlation without pretending unrelated public files belong together.

**Why not use the agent for every question?**  
Extra steps add time, cost, and opportunities for error. The router selects the smallest sufficient method.

**Where is “reasoning” shown?**  
The UI shows the route, concise plan, tool inputs, observations, evidence check, and final citations. Private chain-of-thought is neither required nor displayed.

**Can it write to a project system?**  
No. The academic MVP tools are read-only. Any future write operation would require a preview, explicit approval, and an audit record.

**Is IS 800 fully indexed?**  
The repository indexes official public catalogue/preview content with explicit scope labels. It does not claim to store the complete standard. A licensed project copy would require authorized access and a project adoption record.

## Backup if an external API is unavailable

- Run `make eval` to demonstrate the deterministic offline routes, tools, evidence, and scores.
- Use the five executed notebooks to show each concept separately.
- The API falls back to deterministic routing when live model planning is unavailable; database-backed project evidence remains testable locally.
