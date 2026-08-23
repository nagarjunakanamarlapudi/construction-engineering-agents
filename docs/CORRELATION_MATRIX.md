# Structural-Steel Pilot Correlation Matrix

## Purpose

This matrix defines the relationships required to connect the pilot’s technical, schedule, commercial, procurement, field, quality, and handover records. It is a validation contract for the data foundation—not an agent knowledge graph design. The academic implementation uses synthetic ground truth first; a future authorized pilot must validate the same relationships against real source records.

## Trust policy

1. Prefer an explicit relationship stored by an authoritative system.
2. Otherwise use approved crosswalks and exact normalized identifiers.
3. Use multi-field rules only when their precision is measured and ambiguous cases are reviewed.
4. Treat semantic or model-suggested links as review candidates, never trusted project facts.
5. Store provenance, method, confidence, temporal validity, and confirmation for every published relationship.

## Master-data crosswalks

These crosswalks must be governed before record-level correlations are published.

| Crosswalk | Source A | Source B | Required mapping | Owner | Acceptance test |
|---|---|---|---|---|---|
| Organization | Contract/PMIS organization IDs | ERP/CDE/vendor IDs | One canonical organization per legal/project party; aliases retained | Project controls/contracts | No unmapped in-scope party; duplicates reviewed |
| Person and role | CDE/PMIS users | contract RACI/approval roles | Person identity separated from project role and company | Information manager | Approval history resolves to a person, role and company |
| WBS/package | P6 WBS/activity codes | contract/procurement/work-package codes | Canonical work package linked to schedule scope | Planner/contracts | Every pilot activity maps to one approved WBS and package |
| CBS/BOQ | ERP cost code/BOQ item | P6/work-package codes | Approved cost-to-scope crosswalk | Commercial/project controls | Package totals reconcile; unmapped values reported |
| Location | CDE/BIM location | schedule/field/QMS location | Canonical site/building/level/zone hierarchy | BIM/construction | In-scope field and quality records resolve to governed locations |
| Asset/system | BIM GUID/type/system | commissioning/field/ERP asset IDs | Asset identity with version-independent business key where possible | BIM/handover | Installed and handed-over items resolve to design objects or approved exceptions |
| Document identity | CDE source ID/document number | transmittal/RFI/submittal references | Canonical document plus separate revisions/status events | Document control | Register counts and current/superseded states reconcile |
| Material/item | BOQ/PO item | material grade/heat/piece mark | Item-to-material-to-fabricated-piece chain | Procurement/QA | Sampled pieces trace back to approved item, PO and certificate |

## Required record relationships

| ID | From | Relationship | To | Preferred evidence/join | Fallback rule | Priority | Validation |
|---|---|---|---|---|---|---|---|
| R-001 | Code edition/amendment | `ADOPTED_BY` | Project/design basis | Approved code register, contract or authority instrument | None; requires human approval | P0 | Every applicable code has adoption evidence and status |
| R-002 | Code clause | `IMPLEMENTED_BY` | Project specification clause | Explicit citation in specification | Exact code/clause reference in approved design criteria | P0 | Expert review of all pilot governing clauses |
| R-003 | Specification clause | `GOVERNS` | Design criterion/material/workmanship/test | Explicit section cross-reference | Approved mapping table | P0 | Sample against design and ITP requirements |
| R-004 | Design criterion/load case | `DERIVED_FROM` | Code/spec clause | Calculation/design-basis citation | Approved designer crosswalk | P0 | Structural reviewer confirms governing basis |
| R-005 | Calculation revision | `DESIGNS` | Member/connection/assembly | Element/piece/member IDs in calculation | Drawing/grid/mark plus approved crosswalk | P0 | Sampled elements trace to calculation and review status |
| R-006 | Calculation revision | `SUPPORTS` | Drawing revision | Drawing/calculation reference | Approved document mapping | P0 | Current AFC drawings link to approved calculations |
| R-007 | Drawing revision | `REVISES` / `SUPERSEDES` | Prior drawing revision | CDE revision chain/document register | Document number plus approved revision sequence | P0 | Full register and issue-package reconciliation |
| R-008 | Drawing revision | `REPRESENTS` | Model version/object | Model-drawing issue metadata and GUID references | Drawing/view/grid/mark mapping | P1 | BIM manager approves sampled links |
| R-009 | RFI/TQ | `REFERENCES` | Drawing revision/spec clause/model issue | Structured reference fields and attachments | Exact identifiers in controlled text | P0 | Referenced revision exists and was valid at RFI date |
| R-010 | RFI response/decision | `CHANGES_OR_CLARIFIES` | Requirement/drawing/model/scope | Approved response and resulting revision/change | Document-control mapping | P0 | Decision-to-implemented-revision closure verified |
| R-011 | Submittal/shop drawing | `SATISFIES` | Specification clause/BOQ item | Structured submittal section/item fields | Exact controlled identifiers | P0 | Accepted submittal traces to requirement and item |
| R-012 | Submittal revision | `APPROVED_BY` | Review event/person/role | Workflow audit history | Signed approval/transmittal | P0 | Status, approver, date and conditions reconcile |
| R-013 | Change/variation | `ORIGINATES_FROM` | RFI/decision/instruction | Structured source reference | Exact notice/RFI/document IDs | P0 | Change cause and approval chain verified |
| R-014 | Change/variation | `AFFECTS` | BOQ/cost/activity/drawing | Approved change breakdown | Approved mapping schedule | P0 | Time and cost effects reconcile to controls systems |
| R-015 | BOQ/BOM item | `PROCURED_BY` | Requisition/PO item | ERP item/cost/package keys | Approved item crosswalk | P0 | Quantity, unit, package and vendor reconcile |
| R-016 | PO item | `FULFILLED_BY` | Material heat/batch/lot | GRN/MTC/packing-list reference | Approved traceability register | P0 | Trace sampled receipts to PO and certificate |
| R-017 | Material heat/batch | `USED_IN` | Piece mark/assembly | Fabrication cut/piece/heat register | Approved fabricator mapping | P0 | Bidirectional heat-to-piece traceability |
| R-018 | Piece mark/assembly | `DEFINED_BY` | Fabrication drawing revision/model object | Piece list/model GUID | Exact mark plus approved model crosswalk | P0 | No duplicate active piece identity within scope |
| R-019 | Weld ID | `JOINS` | Piece marks/components | Weld map/fabrication record | None unless QA approves reconstruction | P0 | Weld map reconciles with piece register |
| R-020 | Weld ID | `USES` | WPS/welder/consumable | Weld log | Approved QA correction | P0 | Qualification validity checked at weld date |
| R-021 | NDT report/result | `TESTS` | Weld ID/piece/lot | Structured report references | Exact controlled IDs | P0 | Result, extent, procedure, inspector and date present |
| R-022 | Shipment/GRN | `DELIVERS` | PO item/piece/lot | Packing list and ERP receipt | Approved receipt crosswalk | P0 | Dispatch, receipt, shortage/damage and storage reconcile |
| R-023 | Schedule activity | `DELIVERS` | Work package/location/asset/quantity | Activity codes and controlled mapping | Approved planner crosswalk | P0 | Every pilot activity resolves to scope and location |
| R-024 | Activity | `DEPENDS_ON` | Predecessor activity | Authoritative P6 relationship | None | P0 | Relationship count/types/lags reconcile with export |
| R-025 | Procurement/fabrication milestone | `SUPPORTS_OR_BLOCKS` | Schedule activity | Integrated schedule/approved mapping | Need date plus reviewed rule | P0 | Long-lead chain reviewed with planner/procurement |
| R-026 | RFI/change/NCR | `AFFECTS_OR_BLOCKS` | Schedule activity | Explicit issue/activity mapping | Rule-assisted candidate requiring planner approval | P0 | High-impact links all reviewed |
| R-027 | Daily report/progress quantity | `EVIDENCES` | Activity/work package/location | Field activity/quantity codes | Date/location/crew rule with review | P0 | Period quantities and progress reconcile |
| R-028 | Installed piece/assembly | `INSTALLED_AT` | Asset/location/date/activity | Installation/erection register | Survey/inspection evidence | P0 | Sample against site, drawing and as-built data |
| R-029 | Inspection request | `VERIFIES` | Piece/assembly/activity/drawing/ITP point | Structured inspection references | Exact identifiers in form | P0 | Acceptance criterion and outcome trace to requirement |
| R-030 | Inspection/test | `RAISES` | NCR | QMS link | Exact inspection/report ID | P0 | All pilot NCRs trace to origin or approved exception |
| R-031 | NCR | `CORRECTED_BY` | Disposition/repair/reinspection | QMS workflow history | Approved closure package | P0 | Requirement, repair, reinspection and approver complete |
| R-032 | NCR/change/delay event | `IMPACTS` | Cost/activity/progress | Approved assessment | Candidate requiring controls approval | P1 | No inferred impact published without approval |
| R-033 | Meeting action/decision | `DISCUSSES_OR_RESOLVES` | RFI/issue/change/activity | Structured references/action log | Exact identifier in controlled minute | P1 | Owner, due date, status and source minute retained |
| R-034 | As-built drawing/model | `REPRESENTS` | Installed asset/piece/location | Handover/asset register | Approved exception mapping | P0 | Accepted asset has current as-built evidence |
| R-035 | Test pack/punch/warranty/manual | `HANDOVER_EVIDENCE_FOR` | Asset/system | Commissioning/handover register | Approved document-to-asset crosswalk | P0 | Required deliverables and acceptance status reconcile |

## Correlation acceptance report

Report quality by relationship type; do not publish only an overall average.

| Relationship ID/type | Source population | Eligible records | Links produced | Coverage | Expert-reviewed sample | Correct links | Precision | Ambiguous/unresolved | Trust level | Accepted by/date |
|---|---|---|---|---|---|---|---|---|---|---|
| TBD |  |  |  |  |  |  |  |  |  |  |

## Required end-to-end trace tests

The pilot should produce at least one independently verified trace for each path:

1. `Code -> specification -> calculation -> drawing -> member/connection`.
2. `RFI -> decision -> drawing/model revision -> change -> activity/cost impact`.
3. `BOQ -> approved submittal -> PO -> MTC/heat -> piece -> delivery -> installation`.
4. `Piece/weld -> WPS/welder -> NDT -> inspection -> acceptance`.
5. `Activity -> look-ahead -> daily report -> installed quantity -> progress update`.
6. `Inspection -> NCR -> correction -> reinspection -> closure`.
7. `Installed asset -> as-built -> test/punch closure -> manual/warranty -> handover`.

Every trace must show source records, versions, dates, permissions, and any unresolved gap.
