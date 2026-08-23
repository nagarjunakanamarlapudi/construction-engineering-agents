# Pilot Data Collection Register

## Purpose

Use this register to collect the complete data foundation for one India-based structural-steel work package. It identifies **what must be requested**, the likely owner/source, and the identifiers needed to correlate records.

This is the future **authorized-project** collection register. It is not evidence that a dataset has been obtained. The academic implementation first creates an equivalent, clearly labelled synthetic dataset. Update `Source confirmed`, `Owner`, `Coverage period`, `Delivery`, and `Status` only after a real pilot project supplies and validates the information.

## Pilot definition

| Field | Value |
|---|---|
| Project | To be selected |
| State/UT and ULB | To be confirmed |
| Asset | Steel-framed building |
| Pilot scope | One structural-steel work package with its foundations and interfaces |
| Coverage period | Prefer complete design-to-handover history; minimum current phase plus all referenced prior revisions |
| Project data date | To be confirmed |
| Project information manager | To be assigned |
| Structural/design approver | To be assigned |

## Status legend

- `Not requested`
- `Requested`
- `Sample received`
- `Profiled`
- `Full delivery received`
- `Reconciled`
- `Accepted`
- `Blocked`
- `Out of scope`

## Dataset register

| ID | Dataset to collect | Minimum required content | Candidate owner/source | Required correlation keys | Priority | Status |
|---|---|---|---|---|---|---|
| GOV-01 | Project master | Project ID/code, name, site, dates, phase, status, client and delivery parties | Client PMO / PMIS | `project_id`, organization IDs | P0 | Not requested |
| GOV-02 | Organization and responsibility | Companies, people, roles, RACI, approval/delegation matrix | PMO / CDE / contract admin | organization, person, role IDs | P0 | Not requested |
| GOV-03 | Naming and status rules | Document numbering, discipline/location codes, revision/status/purpose rules | Information manager / BEP / document control procedure | code lists and mappings | P0 | Not requested |
| GOV-04 | Project breakdown structures | WBS, CBS/cost codes, work packages, locations, systems and asset hierarchy | Planner, commercial team, BIM/information manager | WBS, cost, package, location, system and asset IDs | P0 | Not requested |
| REG-01 | Applicable-code register | Approved codes, editions, amendments, applicability, precedence and approval evidence | Lead designer / client / authority coordinator | `code_id`, clause, discipline, adoption evidence | P0 | Not requested |
| REG-02 | Licensed standards | Exact access-controlled copies adopted by the project | Client/design library | code, edition, amendment, checksum | P0 | Not requested |
| REG-03 | Statutory requirements | State/ULB bye-laws, sanctioned plans, permit/NOC conditions, fire and environmental approvals | Authority coordinator / client | approval ID, condition, location/system, dates | P0 | Not requested |
| CON-01 | Main contract and employer requirements | Agreement, scope, technical requirements, precedence and deliverables | Contract manager / EDMS | contract, clause, package, organization IDs | P0 | Not requested |
| CON-02 | Subcontracts and scope matrices | Structural steel/fabrication/erection scope, interfaces and exclusions | Commercial/contracts | subcontract, package, BOQ and vendor IDs | P1 | Not requested |
| CON-03 | Project specifications | Complete structural, materials, workmanship, testing and interface specifications with revisions | CDE / document control | document/revision, section/clause, package, discipline | P0 | Not requested |
| DES-01 | Basis of design and design criteria | Loads, combinations, materials, assumptions, codes, serviceability and durability criteria | Structural designer | document/revision, code clause, load case, element type | P0 | Not requested |
| DES-02 | Design calculations and reviews | Analysis/design reports, connection calculations, comments, approvals and superseded revisions | Structural designer / checker | calculation/revision, model/element, drawing, reviewer | P0 | Not requested |
| DES-03 | Drawing register | All structural/general arrangement/fabrication/erection drawings, status, revisions and dates | Document control / CDE | drawing number, revision, status, issue date | P0 | Not requested |
| DES-04 | Drawing files and revision history | Native/PDF files, mark-ups, issue packages, transmittals and superseded versions | CDE / design/fabrication teams | document/revision, transmittal, package, location | P0 | Not requested |
| DES-05 | BIM/model register and models | Authoring/federated models, version history, IFC exports, export settings and model coordinates | BIM manager / CDE | model/version, IFC GUID, asset, system, location | P1 | Not requested |
| DES-06 | Coordination and clash issues | Issue history, viewpoints/snapshots, comments, BCF references and resolution | BIM coordinator / CDE | issue ID, model version, IFC GUID, drawing/RFI | P1 | Not requested |
| WF-01 | RFI/TQ register and records | Question, response, status history, dates, references, attachments and participants | CDE / design manager | RFI ID, drawing/revision, spec clause, package, activity | P0 | Not requested |
| WF-02 | Submittal and material approval records | Register, workflow history, reviews, status, attachments, linked specification and supplier | CDE / QA/design/procurement | submittal ID, spec clause, material/item, vendor, package | P0 | Not requested |
| WF-03 | Shop drawings and fabrication documents | Fabrication/erection drawings, piece lists, revisions, approvals and transmittals | Fabricator / CDE | drawing/revision, piece mark, model GUID, package | P0 | Not requested |
| WF-04 | Method statements and ITPs | Approved execution methods, hold/witness points, acceptance criteria and revisions | Contractor QA/HSE / CDE | document/revision, activity, inspection/test type, code/spec clause | P0 | Not requested |
| COM-01 | Controlled correspondence | Letters, notices and approved email records relevant to pilot scope | EDMS / contract manager | communication ID, issue/change, organization, dates | P1 | Not requested |
| COM-02 | Meeting minutes and decisions | Design/progress/coordination minutes, actions, decisions, owners and due dates | PMO / CDE | meeting/action/decision ID, RFI/issue/package/activity | P1 | Not requested |
| SCH-01 | Current schedule | WBS, activities, relationships, constraints, calendars, resources and data date | Planner / P6 | activity, WBS, calendar, relationship, package/location | P0 | Not requested |
| SCH-02 | Baselines and update history | Approved baseline, revisions, periodic updates, narratives and data dates | Planner / P6 / EDMS | baseline/version, activity, reporting period | P0 | Not requested |
| SCH-03 | Look-aheads and work plans | Weekly/three- or six-week plans, constraints and commitments | Construction/planning team | activity, work front, location, crew, date | P1 | Not requested |
| PRG-01 | Progress and quantity measurement | Planned/earned/actual quantities, rules, installed quantities and approvals | Project controls / ERP / field system | BOQ item, activity, location, asset, reporting period | P0 | Not requested |
| CST-01 | BOQ/BOM and budget | Item descriptions, units, quantities, rates, budget and package mapping | Commercial / ERP | BOQ/item, cost code, package, asset/material | P0 | Not requested |
| CST-02 | Commitments, actuals and forecasts | Subcontracts/PO commitments, invoices, payment certificates, actual/forecast cost | Commercial / ERP | contract/PO, cost code, BOQ, reporting period | P1 | Not requested |
| CHG-01 | Changes and variation records | Change requests/orders, instructions, scope, reason, status, time/cost effect and approval | Change/contract system | change ID, RFI/decision, drawing, BOQ, activity, cost code | P0 | Not requested |
| CLM-01 | Notices, claims and delay events | Notices, cause/effect narrative, impacted periods/activities, evidence and determination | Contract/claims team | notice/claim/event, activity, change, communication, dates | P1 | Not requested |
| RSK-01 | Risk and opportunity register | Description, cause, effect, owner, probability/impact, response and status history | Risk manager / PMIS | risk ID, package, activity, cost/location/owner | P1 | Not requested |
| PRC-01 | Vendor and fabricator master | Approved vendors, fabricators, subcontractors, contacts and qualification status | Procurement / ERP / QA | vendor/organization ID, package, qualification | P0 | Not requested |
| PRC-02 | Requisitions, bids, POs and subcontracts | Items, quantities, dates, terms, revisions, suppliers and required-on-site dates | Procurement / ERP | requisition/PO/item, BOQ, package, vendor, activity | P0 | Not requested |
| PRC-03 | Fabrication and expediting status | Piece/lot status, planned/actual fabrication, inspection, dispatch and forecast | Fabricator / expediting system | piece/lot, drawing, PO item, milestone/activity | P0 | Not requested |
| PRC-04 | Logistics and receipt | Packing lists, shipments, dispatch, delivery, GRN, damage/shortage and storage | Logistics / stores / ERP | shipment/GRN, PO item, lot/piece, location, date | P0 | Not requested |
| MAT-01 | Material certificates and traceability | MTCs, heat/batch/lot, grade, section/plate, quantity and supplier | Fabricator / QA / ERP | heat/batch, PO item, material, piece mark | P0 | Not requested |
| FAB-01 | Fabrication piece and weld register | Piece marks, assemblies, weld IDs, joint details, welders and fabrication status | Fabricator / QMS | piece/weld, drawing/revision, model GUID, heat, WPS | P0 | Not requested |
| FAB-02 | WPS/PQR/WPQ | Approved procedures/qualifications, processes, ranges, welders and validity | Fabricator QA / QMS | WPS/PQR/WPQ/welder IDs, weld type/material | P0 | Not requested |
| FAB-03 | NDT and dimensional/coating records | NDT method/results, repair/retest, dimensional checks, surface preparation and coating | QA/NDT agency / QMS | weld/piece/lot, procedure, inspector, report, date | P0 | Not requested |
| FLD-01 | Daily reports and site diaries | Weather, work fronts, activities, labour, plant, quantities, delays, instructions and photos | Construction team / field app | date/shift, activity, location, crew/equipment, issue | P0 | Not requested |
| FLD-02 | Erection and installation records | Receipt/release, erection sequence, piece/assembly installed, bolting/welding and completion | Erection contractor / field/QMS | piece/assembly, asset/location, activity, drawing | P0 | Not requested |
| FLD-03 | Survey and as-built records | Control data, pre/post-erection survey, alignment/level/plumbness and final coordinates | Survey team | survey point, asset/piece, location, drawing, date | P1 | Not requested |
| QUA-01 | Inspection requests and checklists | Requests, ITP points, results, comments, approvals, attachments and status history | QA/QC / QMS | inspection ID, ITP point, piece/asset, drawing, activity | P0 | Not requested |
| QUA-02 | NCR and corrective-action records | Nonconformance, requirement, disposition, repair, reinspection, closure and approvals | QA/QC / QMS | NCR, inspection/test, piece/asset, activity, cost/change | P0 | Not requested |
| HSE-01 | HSE records for pilot scope | JSA/risk assessment, permit, observation/incident, corrective action and training where authorized | HSE platform | activity, location, contractor, hazard/control, date | P1 | Not requested |
| ENV-01 | Environmental conditions and monitoring | Applicable permit conditions, measurements, limits, exceedances and corrective action | EHS / authority records | condition, parameter, location, activity, date | P2 | Not requested |
| HND-01 | Punch, as-built and handover package | Punch items, closure, as-built drawings/models, test packs, manuals, warranties and acceptance | Commissioning/handover / CDE | asset/system, punch/test, drawing/model, package, approval | P0 | Not requested |

## Source confirmation record

Complete one row for every actual source system or repository discovered.

| Source system ID | Product/repository and environment | Business owner | Technical owner | Authoritative datasets/fields | Access/export method | Stable source keys | History/revisions available | ACL model | Completeness limitations | Coverage period | Last verified | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TBD |  |  |  |  |  |  |  |  |  |  |  | Not requested |

## Collection decisions

Record every inclusion, exclusion, precedence, and completeness decision.

| Decision ID | Date | Dataset/source | Decision | Rationale/evidence | Approved by | Review date |
|---|---|---|---|---|---|---|
| TBD |  |  |  |  |  |  |
