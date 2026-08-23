# Submission Proposal — Diagram Prompts

## Shared art direction

Use a polished hand-drawn whiteboard infographic style on a clean white background. Landscape 16:9 composition, high resolution, generous spacing, large highly legible lettering, short labels, rounded cards, simple construction and document icons, restrained arrows, and no decorative clutter. The diagrams are for readers who may know neither civil engineering nor artificial intelligence.

Use the same color meaning in every image:

- blue: collecting and preparing information;
- green: search and supporting evidence;
- purple: assisted multi-step investigation;
- orange: approved lookups, comparisons, and calculations;
- gray: stored information, evidence, and safeguards; and
- teal: user preferences and conversation context.

Avoid small paragraphs, unexplained abbreviations, product logos, photorealism, three-dimensional effects, and dark backgrounds. Spell every label exactly as supplied. Keep all important text safely inside the image margins.

## 1. Capability roadmap

Target file: `submission-capability-roadmap.png`

Prompt:

> Create a landscape 16:9 hand-drawn whiteboard infographic titled “What the Civil Engineering Project Copilot Can Answer”. Show a clear left-to-right road with four large numbered stages.
>
> Stage 1, blue-gray, status label “AVAILABLE NOW”, heading “Information collected today”. Add two short question cards: “What sample building models are available?” and “Which Indian code sources are catalogued?” Add a small note: “Public samples and reference links—not a live project.”
>
> Stage 2, green, status label “REQUIRES AUTHORIZED PROJECT DATA”, heading “Project search with evidence”. Question cards: “What is the latest approved drawing?” and “What answer was approved for a design question?”
>
> Stage 3, green-orange, status label “REQUIRES AUTHORIZED PROJECT DATA”, heading “Connected records and calculations”. Question cards: “Which issue affects this work activity?” and “What changed between two drawing versions?”
>
> Stage 4, purple, status label “FUTURE ASSISTED INVESTIGATION”, heading “Several steps for one question”. Question cards: “Why is this work delayed?” and “What downstream work may be affected?”
>
> Add a prominent bottom note in a gray rounded banner: “Current repository status: data collection and design only. No agent has been built.” Use friendly icons: folders/models, magnifying glass with cited page, linked records with calculator, and a careful assistant checking several evidence cards. Make progression and status differences obvious at a glance. Do not add any other text.

## 2. Complete system architecture

Target file: `submission-system-architecture.png`

Prompt:

> Create a landscape 16:9 hand-drawn whiteboard infographic titled “Civil Engineering Project Copilot — How the System Fits Together”. Use two clearly separated horizontal lanes.
>
> Top lane title in blue: “A. PREPARE PROJECT INFORMATION — happens before questions are asked”. Show three large connected groups. First, “Construction information sources” with simple icons and short labels: “Indian codes”, “Drawings and versions”, “Design questions and approvals”, “Work schedule”, “Building model”, “Materials and purchasing”, “Site and quality records”. Second, “Collect and check” with four short items: “Keep originals”, “Read text and tables”, “Standardize names and dates”, “Check versions, links, and access”. Third, a gray repository called “Organized project knowledge” containing “Searchable documents”, “Structured records”, “Relationship map”, and “Source history”.
>
> Bottom lane title in green: “B. ANSWER A QUESTION — uses the prepared information”. Show “User question” flowing to a decision card “Use the simplest safe path”. The direct green path goes to “Project search with evidence” and then “Answer with source citations”. A second path uses orange cards “Approved lookup, comparison, or calculation”. Only a complex question may continue to a purple card “Assisted investigation: break the question into steps and choose approved operations”, then return to “Answer with source citations”. Beside the answer add an alternative gray card: “Not enough evidence”.
>
> Put a teal side card next to question handling: “Mem0 memory — approved preferences and conversation context only. Never project facts.” Put a gray safeguard strip across the bottom: “Permissions • current versions • source links • human review • quality checks”. Use arrows that make it clear the top preparation lane does not run every time a question is asked. No agent may connect directly to stored information; the purple card must point through the orange approved-operation cards. Do not add product logos or unexplained abbreviations.

## 3. Question routing

Target file: `submission-question-routing.png`

Prompt:

> Create a landscape 16:9 hand-drawn whiteboard infographic titled “Use the Simplest Safe Path for Each Question”. Split it into two equal panels.
>
> Left green panel heading: “SIMPLE QUESTION — ONE SEARCH PATH”. Example question: “What is the latest approved version of drawing S-204?” Flow: “Project and access check” → “Search exact number + meaning” → “Check status and date” → “Cited answer”. Add a small definition box: “RAG = search the project records first, then give the evidence to the AI before it answers.” Add a green check mark and note “Fast, direct, evidence-backed.”
>
> Right purple-orange panel heading: “COMPLEX QUESTION — SEVERAL CONTROLLED STEPS”. Example question: “Why is Level 4 steel erection delayed?” First purple card: “Break it into smaller questions”. Show three short sub-questions: “What does the schedule show?”, “Are design questions unresolved?”, “Are materials or inspections blocking work?” Then show orange cards named “Schedule check”, “Design-record search”, “Material and quality check”. Flow to “Review the returned evidence” → decision “Enough evidence?” → either “Cited explanation” or gray “Say what information is missing”. Add a large plain-language definition: “Agentic RAG = the AI plans the steps and chooses approved searches or calculations for a complex question.”
>
> Add a bottom safety strip: “Read-only investigation • no direct database access • people make engineering and approval decisions”. Use large lettering and minimal words. Do not use the terms LLM, BM25, vector database, or orchestration.

## 4. Responsibility map

Target file: `submission-responsibility-map.png`

Prompt:

> Create a landscape 16:9 hand-drawn whiteboard infographic titled “Each Part Has One Clear Job”. Use six large rounded cards arranged in two rows, with simple icons and clear arrows where necessary.
>
> Blue card “DATA COLLECTION”: “Brings records in, keeps originals, and checks versions and access.”
>
> Green card “PROJECT SEARCH — RAG”: “Finds relevant current records and returns supporting evidence.”
>
> Green card “RELATIONSHIP SEARCH — GRAPH RAG”: “Follows stored links, such as design question → drawing → work activity.”
>
> Orange card “TOOLS”: “Perform one approved lookup, comparison, relationship check, or calculation.”
>
> Purple card “AGENT — FUTURE”: “For a complex question, decides which approved tool to use next and when to stop.”
>
> Teal card “MEMORY — MEM0”: “Remembers approved preferences and conversation context, never project facts.”
>
> Show the agent calling tools; tools use project search or relationship search; search reads from a gray foundation labeled “SOURCE OF TRUTH: current authorized project records and preserved originals”. Memory may provide preferences to the agent or direct search, but draw a red blocked line from memory to the source-of-truth foundation and label it “not project truth”. End every valid path at a gray-green result box: “Cited answer—or clearly not enough evidence”. Add a bottom note: “Current work focuses on data. Agent and memory implementation come later.” Avoid unexplained abbreviations beyond RAG, Graph RAG, and Mem0, which are explained in their cards.

## Refinements applied to generated images

The following edit prompts are part of the final prompt record.

### Complete system architecture — correct the complex-question sequence

> Preserve the title, whiteboard style, high resolution, top preparation lane, colors, wording, source icons, organized project knowledge, memory boundary, and safeguards. Correct and simplify only the complex-question flow: user question → simplest safe path → assisted investigation → approved lookup, comparison, relationship check, or calculation → evidence returned. Loop returned evidence to the assisted investigation with “check evidence; continue if needed”. Allow the assisted investigation to finish at a cited answer or “not enough evidence”. Remove fixed step numbers from the loop. The assisted investigation must never connect directly to organized project knowledge.

### Complete system architecture — restore memory boundary

> Preserve the corrected infographic. Add a teal card beside question handling: “Mem0 memory — approved preferences and conversation context only. Never project facts.” Draw one dotted teal arrow toward the simplest-safe-path decision. Do not draw an arrow from memory to organized project knowledge.

### Question routing — solid preview background

> Preserve the entire infographic, including all wording, icons, panels, arrows, definitions, and safeguards. Replace every transparent, black, or empty-looking region with a solid white or very pale matching background. Maintain strong text contrast. Do not add, remove, or rewrite content.

### Responsibility map — correct component boundaries

> Preserve the six cards and all wording. Draw data collection directly to the source of truth. Draw the future agent to tools only. Draw tools to project search and relationship search. Connect both search services to the source of truth. Keep memory connected to user/agent context and keep the red blocked line to the source of truth labelled “not project truth”. No direct connection may exist from agent or memory to the source of truth.
