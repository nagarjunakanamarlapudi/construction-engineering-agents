# Civil Engineering Project Copilot — Data Foundation

## 1. Purpose

The implemented **correlated academic data foundation** combines the public material already collected with one clearly labelled synthetic project, normalizes identifiers, and proves that related records can be connected with defensible provenance. It now supports Direct RAG, Graph RAG, and bounded Agentic RAG through the shared production modules.

The initial vertical slice is one **synthetic India-based steel-framed building project or structural-steel work package**. This makes IS 800 highly relevant while still exercising concrete/foundations, loads, seismic, fire, project controls, procurement, field execution, quality, and local approval information where applicable. Every synthetic record remains visibly marked as academic demonstration data.

Direct RAG follows the data-readiness gates in this document. The completed pilot also includes several read-only agentic investigations so the course submission can compare routes and tools. Authorized project data remains a later real-world validation step.

The operating documents are:

- [Pilot Data Collection Register](DATA_COLLECTION_REGISTER.md)
- [Structural-Steel Correlation Matrix](CORRELATION_MATRIX.md)
- [Pilot Data Handoff Checklist](PILOT_DATA_HANDOFF.md)
- [Indian Standards and Regulatory Sources Register](INDIAN_STANDARDS_REGISTER.md)
- [Public Data Catalogue](PUBLIC_DATA_CATALOG.md)

## 2. Important distinction: information domains vs source systems

- An **information domain** is what the record means: drawing, RFI, schedule activity, purchase order, inspection, or code provision.
- A **source system** is where that record is managed: Autodesk Construction Cloud, Procore, SharePoint, Primavera P6, an ERP, an email archive, or a controlled folder.
- An **ingestion method** is how an authorized copy is obtained: API, webhook, native export, database view, or controlled file drop.

The same domain may exist in several systems, but the project must name exactly one authoritative source—or an explicit precedence rule—for each record type.

## 3. Project information inventory

This is a discovery checklist. The actual system of record, owner, cadence, retention, and access rules must be confirmed with the pilot project.

| Domain | Information to collect | Typical systems/formats | High-value correlations |
|---|---|---|---|
| Project governance | Project charter, scope, parties, organization, RACI, approval matrix, project calendar, naming rules | PMIS, CDE, SharePoint, PDF/XLSX | Project, organization, person, role, contract, package |
| Project breakdowns | WBS, CBS/cost codes, work packages, location breakdown, asset/system hierarchy | P6, ERP, BIM, spreadsheets | Common spine joining schedule, cost, location, asset, and responsibility |
| Regulatory and codes | Applicable-code list, licensed standards, local bye-laws, permits, NOCs, approval conditions, design criteria | BIS/licensed library, authority portals, CDE, PDF/register | Requirement to design object, document, approval, inspection, and evidence |
| Contract and scope | Main contract, subcontracts, employer requirements, scope matrices, specifications, BOQ/BOM | ERP, contract system, CDE, PDF/XLSX | Contract clause to package, specification, BOQ item, change, cost, and party |
| Design basis and calculations | Basis of design, design criteria, assumptions, calculations, analysis reports, technical notes | CDE, analysis tools, PDF/DOCX/XLSX | Code clause to assumption, load case, element, calculation, reviewer, and revision |
| Drawings and document control | Drawing register, drawings, revision history, status/purpose, transmittals, document register | ACC/Procore/SharePoint/CDE, PDF/DWG/DGN | Drawing to revision, model, RFI, submittal, activity, location, and asset |
| BIM and coordination | Federated/discipline models, IFC exports, object properties, clash and coordination issues, BCF topics | Revit/Tekla/Navisworks, IFC, BCF, native model exports | Model GUID to drawing, asset, location, issue, quantity, and installation record |
| Technical workflows | RFIs/TQs, submittals, shop drawings, material approvals, method statements, ITPs | PMIS/CDE, API/CSV/PDF | Record to specification clause, drawing revision, package, activity, supplier, and decision |
| Correspondence and decisions | Letters, controlled email, meeting minutes, action logs, decisions, commitments | EDMS, email archive, PMIS, MSG/EML/PDF | Communication to issue, decision, responsible party, due date, and affected record |
| Planning and schedule | WBS, activities, relationships, baselines, updates, calendars, constraints, milestones, resources, look-aheads | Primavera P6 XER/XML/API, MSP XML, XLSX | Activity to work package, location, asset, RFI, procurement, progress, cost, and delay event |
| Progress and production | Planned/actual quantities, installed quantities, progress measurement, daily/weekly reports, productivity | Field app, ERP, P6, XLSX, PDF | Quantity and progress to BOQ item, activity, crew, location, drawing, and date |
| Cost and commercial | Estimate, budget, commitments, actuals, forecasts, earned value, invoices, payment certificates | ERP/cost platform, API/CSV/XLSX | Cost code to WBS, BOQ, package, contract, change, activity, and asset |
| Change, claims, and risk | Change requests/orders, variations, notices, claims, delay events, risk register, mitigations | Contract/PMIS/risk system, PDF/XLSX | Cause to decision, changed scope, time impact, cost impact, responsible party, and evidence |
| Procurement and logistics | Vendor register, requisitions, bids, POs, subcontracts, fabrication, expediting, shipping, delivery, GRNs | ERP/procurement platform, API/CSV/PDF | Item to approved submittal, BOQ, supplier, asset, package, need date, activity, and receipt |
| Materials and traceability | Material certificates, heat/batch numbers, mill test certificates, weld consumables, storage and issue records | ERP/QMS, barcode/RFID system, PDF/CSV | Material lot to PO, supplier, test, weld/element, installation location, and inspection |
| Field execution | Work fronts, daily diaries, manpower, plant/equipment, permits to work, site instructions, photos | Field app, PMIS, mobile forms, JPG/PDF/CSV | Daily event to location, activity, crew, equipment, issue, weather, and installed asset |
| Quality management | ITPs, inspection requests, checklists, test reports, NCRs, corrective actions, punch/snag lists | QMS/PMIS/lab system, PDF/CSV | Inspection/test to acceptance criterion, material, drawing, asset, location, NCR, and approver |
| Welding and steel fabrication | WPS/PQR/WPQ, weld maps, NDT reports, fabrication drawings, piece marks, dimensional checks, coating records | Fabricator/QMS/CDE, PDF/CSV | Piece mark/weld to model GUID, drawing, material heat, welder, WPS, NDT, coating, and erection |
| Health and safety | HSE plan, risk assessments/JSA, permits, observations, incidents, training, corrective actions | HSE platform, forms, PDF/CSV | Event to activity, location, contractor, hazard, control, and corrective action |
| Survey, GIS, and ground | Control points, topographic/as-built surveys, utility surveys, GIS layers, boreholes, lab tests, groundwater | GIS/survey tools, LandXML, GeoJSON, SHP, CSV, PDF | Coordinates/location to asset, foundation, drawing, test, condition, and observation date |
| Environmental | Consent conditions, monitoring, waste, dust/noise/water records, environmental incidents | Regulatory portal, EHS system, CSV/PDF | Condition to location, activity, measurement, limit, exceedance, and corrective action |
| Commissioning and handover | System boundaries, test packs, pre-commissioning/commissioning results, punch closure, as-builts, O&M manuals, warranties | CDE/commissioning/asset platform, PDF/CSV/IFC | Asset/system to installation, tests, defects, acceptance, manual, warranty, and owner |

## 4. Source-system and connector register

For every discovered source, record the following fields before building a connector:

| Field | Meaning |
|---|---|
| `source_system_id` | Stable internal identifier for the system or repository |
| `business_owner` / `technical_owner` | Who defines the truth and who grants technical access |
| `domains_and_record_types` | Information provided by the source |
| `authoritative_scope` | Which records/fields this system governs; precedence if multiple systems overlap |
| `access_method` | API, webhook, database view, native export, or controlled file drop |
| `native_formats` | Exact export and attachment formats, including version |
| `stable_source_keys` | IDs that survive renames and exports |
| `revision_and_status_model` | How current, superseded, void, approved, and as-built states are represented |
| `history_available` | Whether event/status history and deleted records can be obtained |
| `sync_cadence` | Event-driven, hourly, daily, weekly, or one-time |
| `permissions` | Project, company, role, folder, document, and field-level restrictions |
| `data_residency_and_license` | Contractual, privacy, copyright, and residency constraints |
| `completeness_limits` | Known export/API omissions and attachment limitations |
| `sample_and_volume` | Representative sample plus expected record/file volume |
| `last_verified_at` | When access, schema, and completeness were last checked |

Examples of connector candidates—not data domains—include Autodesk Construction Cloud, Procore, SharePoint/OneDrive, Primavera P6, Microsoft Project, ERP/QMS/HSE products, email archives, and controlled project folders.

## 5. Canonical correlation spine

Every normalized record should connect to as many of these governed identifiers as the evidence supports:

| Identifier | Examples |
|---|---|
| Project and organization | `project_id`, `organization_id`, `contract_id` |
| Scope and controls | `work_package_id`, `wbs_id`, `cost_code`, `boq_item_id` |
| Place and product | `location_id`, `asset_id`, `system_id`, `model_guid`, `piece_mark` |
| Controlled documents | `document_id`, `revision_id`, `drawing_number`, `spec_section` |
| Workflow records | `rfi_id`, `submittal_id`, `issue_id`, `change_id`, `ncr_id` |
| Time and execution | `activity_id`, `baseline_id`, `data_date`, `shift_id` |
| Procurement and material | `vendor_id`, `po_id`, `item_id`, `heat_or_batch_id` |
| Acceptance | `inspection_id`, `test_id`, `code_id`, `clause_id`, `approval_id` |
| People and responsibility | `person_id`, `role_id`, `responsible_organization_id` |

Source IDs are never discarded. Canonical IDs supplement them and make cross-system joins possible.

## 6. Correlation rules and trust levels

Correlations are evidence, not guesses. Store each as a relationship with `source_record_id`, `assertion_method`, `confidence`, `valid_from`, `valid_to`, `created_at`, and—when applicable—`confirmed_by`.

| Trust level | Method | Treatment |
|---|---|---|
| A — authoritative | Explicit source-system relationship, governed master-data key, or approved register | Publish automatically after referential-integrity checks |
| B — deterministic | Exact normalized identifier, controlled cross-reference, or approved mapping table | Publish with mapping rule and source provenance |
| C — rule-assisted | Combination of discipline, location, package, date, title, and other structured evidence | Queue ambiguous or high-impact links for review |
| D — suggested | Semantic similarity or model-proposed relationship | Never treat as project truth until a human or authoritative source confirms it |

### Priority relationship chains for the steel-building pilot

```text
Code clause -> project specification -> design criterion/calculation -> drawing revision
Drawing/model object -> RFI/submittal/shop drawing -> decision/approval -> change
BOQ/item -> approved material -> purchase order -> heat/batch -> fabrication piece -> installed asset
Work package/location -> schedule activity -> look-ahead -> daily progress -> inspection/test
Inspection/test -> NCR -> corrective action -> reinspection -> acceptance/handover
Issue/change -> affected activity -> time impact -> cost impact -> approval
```

## 7. Version, time, and provenance model

- Preserve the immutable original file or payload and its checksum.
- Treat every revision and status transition as a separate event; never overwrite history.
- Record `issued_at`, `received_at`, `effective_from`, `superseded_at`, and ingestion time separately.
- Resolve questions against an explicit `as_of_date`; “latest” means latest authoritative revision, not latest uploaded file.
- Record who asserted or approved a link and which record proves it.
- Propagate source permissions to every parsed chunk, normalized record, and relationship.
- Keep drafts, review copies, approved-for-construction records, as-builts, and void/superseded records distinguishable.

## 8. Collection and validation sequence

1. **Source census:** identify systems, owners, record types, authority, exports, permissions, and retention.
2. **Representative samples:** obtain small authorized samples including difficult scans, revisions, attachments, and history.
3. **Immutable landing zone:** preserve originals, payloads, manifests, checksums, export date, and collection method.
4. **Profiling:** measure missing IDs, duplicate records, inconsistent status/discipline/location values, and broken references.
5. **Master-data mapping:** agree project, organization, WBS/CBS, location, asset, and document identifiers.
6. **Normalize and correlate:** apply explicit and deterministic links first; queue uncertain links.
7. **Reconcile:** compare counts, revisions, statuses, totals, schedule relationships, and attachments against the source.
8. **Publish trusted datasets:** release only permission-aware, versioned records and provenance-backed relationships.

No agent is required for these steps. OCR, parsers, deterministic matching, and optional model-assisted suggestions may be evaluated as data-processing components, but suggested links remain untrusted until validated.

## 9. Data-readiness gates before agents

These gates governed the synthetic pilot and must be recalibrated for future authorized data:

- authoritative-source rules exist for every in-scope record type;
- 100% of published records retain source ID, source system, checksum/version, timestamps, and ACL scope;
- at least 95% of in-scope records have a valid project and document/workflow identity;
- at least 90% have the required WBS/package, discipline, and location fields where those fields apply;
- current and superseded revisions reconcile with the source registers;
- schedule activity and relationship counts reconcile with the authoritative export;
- high-value relationship chains have at least 90% expert-reviewed precision;
- no Trust-D suggested relationship enters the trusted graph automatically;
- cross-project and unauthorized-record leakage is zero in the test dataset; and
- licensed standards and restricted records remain access-controlled and auditable.

The synthetic corpus passes the applicable provenance, relationship, and access tests, so deterministic retrieval, graph traversal, and bounded agentic planning are now implemented. A future real-project pilot must pass the same gates before its records enter agentic investigations.

## 10. Pilot collection package

Select one structural-steel work package and collect:

1. Project, organization, WBS/CBS, location, asset/system, and naming registers.
2. Applicable-code register, licensed code copies, project specifications, and design criteria.
3. Design calculations, drawing register and revisions, structural drawings, BIM/IFC exports, and model issues.
4. RFIs, submittals, shop drawings, material approvals, method statements, ITPs, transmittals, and decisions.
5. Baseline and current schedule, activity relationships, look-aheads, and progress updates.
6. BOQ, package budget, changes, POs, vendor/fabricator records, delivery and material traceability.
7. WPS/PQR/WPQ, weld maps, NDT, dimensional, coating, inspection, NCR, and corrective-action records.
8. Daily reports, manpower/equipment, installed quantities, photographs, survey/as-built records, and handover evidence.

This package is intentionally broader than the first RAG corpus. Its purpose is to prove that the project’s technical, schedule, commercial, procurement, field, and quality stories can be joined end to end.

## 11. Official technical source references and collection cautions

| Source | Supported collection path | Important discovery check |
|---|---|---|
| Autodesk Construction Cloud / BIM 360 | [Autodesk Platform Services Data Management API](https://aps.autodesk.com/developer/overview/data-management-api) and relevant product APIs | Confirm which project modules, metadata, versions, relationships, history, and ACL details the customer’s entitlement exposes |
| Procore | [Procore developer documentation and API reference](https://developers.procore.com/documentation/introduction) | Inventory each enabled tool separately; verify pagination, attachments, custom fields, status history, webhooks, and company/project permissions |
| SharePoint / OneDrive | [Microsoft Graph SharePoint resources](https://learn.microsoft.com/en-us/graph/api/resources/sharepoint?view=graph-rest-1.0) and [file resources](https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0) | Preserve stable site/list/drive/item IDs, versions, list metadata, sharing/permissions, and retention labels rather than relying on file paths alone |
| Primavera P6 | [Oracle P6 Professional Importing and Exporting Guide](https://docs.oracle.com/cd/F25600_01/English/admin/p6_pro_importing_exporting/p6_pro_importing_exporting.pdf) | No single file should be assumed complete: XER does not export baselines or P6 risk data; XML supports baselines but represents a subset. Define the combination of exports/API needed for the pilot |
| BIM models | [buildingSMART IFC](https://technical.buildingsmart.org/standards/ifc/) | Record IFC schema/version, export settings, source model/version, GUID stability, property-set coverage, coordinates, and omitted native data |
| Model coordination issues | [buildingSMART BCF](https://technical.buildingsmart.org/standards/bcf/) | Preserve topic IDs, status/history, viewpoints, snapshots, IFC GUID references, comments, and the related IFC model version |

Native structured data is preferred over PDF. PDF/OCR remains necessary for signed, scanned, or human-readable evidence but should not replace richer source records when both exist.
