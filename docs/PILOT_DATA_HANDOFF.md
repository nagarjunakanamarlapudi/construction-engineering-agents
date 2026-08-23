# Pilot Data Handoff Checklist

## Goal

Obtain a future authorized, reproducible data delivery for one structural-steel work package without losing source identity, revision history, relationships, permissions, or legal restrictions. This checklist is for real-world validation after the synthetic academic pilot; it does not describe data already present in the repository.

## 1. Begin with a sample delivery

Before requesting the full project, collect a representative sample that includes:

- at least one current and superseded drawing/specification/calculation chain;
- one RFI with attachments, references, response and full status history;
- one submittal/shop-drawing approval chain;
- one schedule update plus approved baseline and activity relationships;
- one PO/item/material-certificate/heat/piece trace;
- one weld with WPS/welder/NDT/inspection evidence;
- one NCR with correction and reinspection; and
- the relevant master-data and permission records.

Use the sample to validate formats, source keys, revision handling, ACLs and correlation feasibility before accepting a bulk export.

## 2. Required handoff package

| Package | Required contents |
|---|---|
| `00_manifest` | File/record manifest, checksums, collection date, source system/environment, exporter, coverage period and known omissions |
| `01_governance` | Project master, organization/RACI, naming/status rules, WBS/CBS/package/location/asset mappings |
| `02_codes_and_approvals` | Approved applicable-code register, licensed-content locations, adoption evidence, permits/NOCs and approval conditions |
| `03_contract_and_specs` | Contracts/scope matrices, employer requirements, BOQ/BOM and project specifications with full revisions |
| `04_design` | Design basis, calculations/reviews, drawing register/files/revisions, models/IFC, coordination issues/BCF |
| `05_workflows` | RFIs, submittals, shop drawings, material approvals, method statements, ITPs, transmittals and decisions |
| `06_schedule_and_progress` | Current schedule, approved baselines, updates, relationships, calendars, look-aheads, narratives, progress and quantities |
| `07_cost_change_risk` | Budget/actual/forecast extracts, changes/variations, notices/claims/delay events and risk register |
| `08_procurement_materials` | Vendors, requisitions/POs, fabrication/expediting, logistics/GRNs, MTCs and heat/batch/piece traceability |
| `09_field_quality_hse` | Daily reports/photos, erection records, surveys, inspections/tests, welding/NDT, NCRs, HSE and environmental records |
| `10_handover` | Punch closure, as-builts, test packs, O&M manuals, warranties, asset/system register and acceptance evidence |
| `11_permissions` | Authorized access/ACL export or approved entitlement mapping for every delivered source |
| `12_reconciliation` | Source counts, revision/status totals, export logs and owner sign-off used to prove completeness |

Folder names are organizational guidance; preserve native export packages unchanged inside the relevant package.

## 3. Manifest fields

The manifest needs one row per file or structured export. Where a source produces record-level manifests, preserve those as well.

| Field | Required meaning |
|---|---|
| `delivery_id` | Stable identifier for the handoff |
| `source_system_id` | Source-system register identity |
| `source_environment` | Production project/site/database/library |
| `dataset_id` | ID from `DATA_COLLECTION_REGISTER.md` |
| `source_object_id` | Stable native file/export/object key |
| `path_or_export_name` | Delivered relative path or native export name |
| `format_and_version` | PDF, IFC4.3, P6 XML, XER, CSV schema version, etc. |
| `record_or_file_count` | Count expected in this item |
| `coverage_start` / `coverage_end` | Business-history coverage, not only export time |
| `exported_at` / `exported_by` | Collection audit information |
| `checksum` | SHA-256 or approved equivalent for delivered file identity |
| `classification` | Public, internal, confidential, restricted, safety/commercial, etc. |
| `acl_reference` | Permission mapping governing the delivered data |
| `license_reference` | Copyright/licence/contract restriction where applicable |
| `known_omissions` | Missing history, fields, attachments, deleted records or modules |
| `authoritative_scope` | What truth this item represents |
| `supersedes_delivery_item` | Earlier export/file replaced by this item, if any |

## 4. Source-specific collection requirements

### Documents and CDE/PMIS

- Export registers and structured metadata in addition to document files.
- Include stable source IDs, custom fields, folder/project identity, status/revision history, transmittals, workflow audit, attachments and references.
- Preserve current, superseded, void and review versions.
- Obtain the permission model or an approved entitlement mapping; folder paths alone are insufficient.

### Primavera P6

- Request current project data, approved baselines, periodic update snapshots, data dates, calendars, constraints, activity codes, UDFs, WBS, relationships/lags, resources, costs/quantities where governed in P6, and schedule narratives.
- Do not accept one XER as proof of completeness. Oracle documents that XER does not export baselines and, for P6 EPPM, does not export risk data; XML supports baselines but is a subset.
- Use the approved combination of XER, XML, API/database/report extracts and separate risk data required by the pilot.
- Reconcile project/WBS/activity/relationship/baseline counts and the current data date with the planner.

### BIM and coordination

- Preserve native model identity and versions, plus a project-approved IFC export.
- Record authoring tool/version, IFC schema, model view definition/exporter/settings, coordinate system, units and omitted categories/properties.
- Test IFC GUID stability across relevant versions; retain business asset/piece IDs separately.
- Export BCF or equivalent issue data with topic history, status, comments, viewpoints, snapshots and referenced model version/GUIDs.

### ERP, procurement and cost

- Request code dictionaries and master data before transactional extracts.
- Preserve revision/change history, currency/unit, accounting/reporting period and document status.
- Include BOQ/PO line keys, vendor IDs, GRNs, MTC/heat/batch references and package/activity mappings.
- Reconcile item quantities and commercial totals with the responsible owner; redact banking/tax/personal data not required by the pilot.

### Fabrication, quality and field systems

- Preserve piece, weld, heat/batch, WPS/PQR/WPQ, welder, NDT, inspection, NCR and installation identities.
- Include status history, revisions, repair/retest/reinspection chains, approvers and attachments.
- Keep photographs with source metadata, capture time, author, referenced location/activity/asset and permissions where available.

### Indian codes and authority documents

- Supply the project-approved code register and adoption evidence before content.
- Record exact edition, part/section, amendments/corrigenda, project status and checksum.
- Store full standards only when the project has authorized/licensed access; retain them in an ACL-controlled location.
- Keep drafts and revision proposals separate from the published project edition.

## 5. Security and minimization

- Obtain written authorization for every source and delivery.
- Collect only the projects, packages, periods, people and fields required for the pilot.
- Exclude personal, payroll, banking, health, grievance, unrelated email and privileged legal material unless explicitly approved and necessary.
- Scan delivered files, encrypt in transit/at rest, restrict access and log all handling.
- Preserve source ACLs; do not make a broadly accessible copy of restricted records.
- Agree retention and deletion dates before ingestion.

## 6. Acceptance checklist

A delivery is accepted only when:

- the manifest and checksums cover every delivered file/export;
- the source owner confirms authoritative scope and known limitations;
- formats open and structured exports parse without silent record loss;
- stable keys, code dictionaries and revision/status definitions are supplied;
- source and delivery counts reconcile within an explained tolerance;
- current/superseded/void states and history are present where required;
- attachments and cross-references resolve or are listed as gaps;
- permission and licence mappings are complete;
- required time zones, units, currencies and coordinate systems are explicit; and
- the delivery can reproduce the priority correlation traces in `CORRELATION_MATRIX.md`.

## 7. Pilot-team sign-off

| Role | Name | Sign-off responsibility | Status/date |
|---|---|---|---|
| Client/project sponsor |  | Authorizes project and pilot scope |  |
| Information/document manager |  | Source inventory, document/revision completeness and ACLs |  |
| Structural design lead |  | Code register, calculations, drawings and technical relationships |  |
| BIM manager |  | Model/IFC/BCF identity, versions and coordinates |  |
| Planner |  | Schedule/baseline/update completeness and activity mappings |  |
| Commercial/procurement lead |  | BOQ/cost/change/PO/vendor/material mappings |  |
| Construction manager |  | Work fronts, progress, field and installation records |  |
| QA/QC lead |  | ITP, fabrication, material, inspection, NDT and NCR traceability |  |
| HSE/environment lead |  | Authorized safety/environment scope and restrictions |  |
| Information security/privacy |  | Access, minimization, retention and handling controls |  |

## 8. Immediate request to the pilot project

Ask the project team for three things first:

1. A completed source confirmation record from `DATA_COLLECTION_REGISTER.md`.
2. One representative sample chain covering code-to-design-to-field-to-quality.
3. The master-data crosswalks from `CORRELATION_MATRIX.md`.

Do not request a bulk dump until these three items show that source authority, permissions, revisions and identifiers are understood.
