# Indian Standards and Regulatory Sources Register

## 1. Scope and operating rule

The Copilot is **India-first**, but IS 800 is not its only standard. The pilot activates the Indian standards and regulations applicable to its asset, disciplines, location, contract, approving authorities, and design date.

This document is a **seed catalogue**, not a certified compliance list. A competent project professional must approve the project-specific code register, exact editions, amendments, local adoption instruments, and order of precedence before code content becomes authoritative project data.

## 2. Standards hierarchy

Apply the following hierarchy; do not assume that a national model code automatically overrides local law or the contract:

1. Applicable legislation, statutory rules, authority conditions, permits, and NOCs.
2. State/UT and urban-local-body development control regulations and building bye-laws.
3. Contract, employer requirements, approved design basis, and project specifications.
4. National model codes and regulator publications, including NBC, ECBC, CEA, CPHEEO, CWC, CPCB/MoEFCC, IRC, and MoRTH material where applicable.
5. Applicable BIS Indian Standards and approved project-adopted international standards.

Conflicts must be surfaced for professional resolution; the Copilot must not invent a precedence decision.

## 3. Pilot building and structural modules

The exact published status and amendments must be checked in the BIS catalogue when the project register is approved. Drafts and standards under revision are tracked separately and never silently substituted for the published project edition.

| Module | Seed standards/source families | Why the project may activate them |
|---|---|---|
| Building baseline | NBC 2016 (`SP 7:2016`), relevant state/ULB bye-laws, fire authority conditions, sanctioned plans | Administration, development controls, fire/life safety, materials, structural design, services, construction safety, sustainability, and facilities |
| Structural steel design | IS 800; project design criteria; referenced connection, stability, fatigue, and execution requirements | Central module for a steel-framed building; IS 800 edition/status must be pinned to the contract and design basis |
| Structural steel materials and sections | IS 2062; IS 808; applicable hollow-section, plate, fastener, bolt, and foundation-bolt standards | Material grade, dimensional properties, procurement, fabrication, and traceability |
| Welding, fabrication, and erection | IS 816; IS 9595; IS 7215; applicable WPS/PQR/WPQ, NDT, tolerances, bolting, coating, and galvanizing standards | Shop and field acceptance, weld traceability, dimensional control, corrosion protection, and erection quality |
| Loads and combinations | IS 875 series and project-specific loading/design criteria | Dead, imposed, wind, snow where applicable, special loads, and load combinations |
| Earthquake resistance | Applicable IS 1893 parts; IS 13920 where applicable; NBC structural provisions | Seismic hazard, analysis, detailing, and project/location-specific requirements |
| Concrete and reinforcement | IS 456; IS 1343 where applicable; IS 10262; IS 383; IS 1786; IS 4926; IS 516 series | Foundations, slabs, pedestals, composite construction, mix design, materials, and testing |
| Soils and foundations | IS 1904; IS 6403; IS 2911 series; IS 2720 series; IS 2131; IS 8009 series; IS 3764 | Site investigation, soil tests, bearing capacity, piles, settlement, excavation, and foundation execution |
| Masonry and non-structural elements | Relevant NBC provisions and applicable masonry, partition, façade, glass, anchorage, and seismic-restraint standards | Building enclosure and non-structural safety where these elements are in project scope |
| Fire and life safety | NBC Part 4, applicable BIS fire standards, state/local fire rules, and approved fire NOC | Occupancy, egress, fire resistance, detection/suppression, and authority approval |
| Building services | NBC Parts 8 and 9, applicable National Electrical Code/BIS standards, CEA safety regulations, CPHEEO/local requirements | Electrical, HVAC, lifts, ICT, water supply, drainage, sanitation, and solid waste |
| Energy and sustainability | ECBC and its state adoption/amendments where applicable; NBC Part 11; project sustainability requirements | Building envelope, lighting, HVAC, electrical, renewable energy, and compliance documentation |
| Construction management and safety | NBC Part 7, applicable labour/construction safety legislation and rules, project HSE requirements | Site practice, temporary works, worker safety, quality, and construction management |
| Accessibility | NBC accessibility provisions, applicable national harmonised guidelines, and local approval requirements | Accessible site, circulation, facilities, and approval evidence |

### Known edition-status cautions for discovery

- The 2026 BIS programme material catalogued during research indicates revision activity for IS 800. Because publication status can change, the implementation must recheck the official catalogue and record the **published edition actually adopted by the project**, plus amendments, instead of assuming that a draft or forthcoming revision applies.
- IS 456:2000 has published amendments and revision activity. Store the base edition, every applicable amendment, and the project adoption date separately.
- IS 875 and IS 1893 are multipart families with part-specific editions and active revision activity. Never represent them as one undifferentiated document.

## 4. Wider Indian infrastructure catalogue

These modules are catalogued now but only activated when the pilot or a later project requires them.

| Asset/domain | Primary Indian authority/source families | Data to register |
|---|---|---|
| Roads and bridges | Indian Roads Congress (IRC), MoRTH, BIS, state road authorities | Applicable IRC/MoRTH documents, revisions, contract adoption, drawings, pavement/bridge records, tests, traffic and asset data |
| Urban water, sewerage, stormwater, and solid waste | CPHEEO/MoHUA, BIS, state/ULB authorities, pollution-control boards | Manuals, local requirements, design criteria, hydraulic models, networks, tests, permits, and commissioning |
| Dams and water resources | Central Water Commission, dam-safety authorities, BIS, state water departments | Guidelines, design/flood/hydrology records, instrumentation, inspections, safety reviews, and emergency plans |
| Power infrastructure | Central Electricity Authority, BIS, Ministry of Power, state electrical inspectorates/utilities | Regulations, approvals, line/plant design records, tests, energization and safety evidence |
| Environmental compliance | MoEFCC, CPCB, state pollution-control boards, consent/clearance authorities | Clearances, consent conditions, standards, measurements, exceedances, waste and corrective actions |
| Rail and metro | Ministry of Railways, RDSO, Commissioner of Metro Railway Safety, relevant metro/rail owner standards, BIS | Project-adopted standards, approvals, systems assurance, civil/track/interface records, tests and commissioning |
| Airports | Ministry of Civil Aviation, DGCA, Airports Authority of India, Bureau of Civil Aviation Security, BIS | Site/airside requirements, obstacle/lighting/fire/security approvals, design and commissioning evidence |
| Ports and coastal works | Ministry of Ports, Shipping and Waterways, port authority, coastal/environmental regulators, BIS/IRC where adopted | Marine design criteria, metocean/geotechnical data, environmental approvals, dredging and asset records |

## 5. Code-register schema

Each code, regulation, manual, bye-law, permit condition, or project specification needs a governed record:

| Field | Purpose |
|---|---|
| `code_record_id` | Stable internal identifier |
| `authority` | BIS, ULB, state authority, NBC, BEE, IRC, MoRTH, CPHEEO, CEA, CWC, CPCB, MoEFCC, or project/client |
| `designation` / `title` | Exact document number, part/section, and official title |
| `edition` / `amendments` | Base publication and separately enumerated amendments/corrigenda |
| `publication_status` | Published, amended, reaffirmed, under review, draft, superseded, withdrawn, or unknown |
| `project_status` | Applicable, informative, excluded, pending review, or superseded for this project |
| `valid_from` / `valid_to` | Temporal applicability for `as_of_date` questions |
| `jurisdiction` | Country, state/UT, ULB/authority, site, or contract scope |
| `asset_types` / `disciplines` | Building, bridge, water, power, structural, fire, MEP, etc. |
| `activation_rule` | Conditions that make the document applicable |
| `adoption_evidence` | Contract clause, design-basis approval, bye-law, permit, NOC, or authority direction |
| `precedence_rank` | Project-approved precedence; unresolved conflicts remain flagged |
| `official_metadata_url` | Authority page used to verify designation and status |
| `licensed_content_uri` | Access-controlled location of the legally obtained content |
| `license_and_acl` | Copyright, user/project entitlements, retention, and citation limits |
| `checksum` | Identity of the exact licensed file ingested |
| `last_verified_at` / `verified_by` | Currency and professional approval trail |

## 6. Ingestion and correlation rules for standards

1. Preserve and prepare public official metadata, status, and preview/full content for the academic corpus, with an explicit content-scope label. Keep any separately supplied project copy under its own access and adoption controls.
2. Preserve code, part, section, edition, amendment, page, and clause hierarchy during parsing and chunking.
3. Link each project requirement to its adoption evidence; a code existing in the catalogue does not make it applicable.
4. Distinguish normative text, tables/figures, commentary, drafts, amendments, and withdrawn material.
5. Correlate `code clause -> project specification -> design criterion/calculation -> drawing/model object -> inspection/test evidence`.
6. Keep the official source URL and access label on every prepared chunk and answer. Do not present a public preview as the complete standard.
7. Require human review for conflicts, interpretations, compliance conclusions, and any change of project edition.

## 7. Official discovery sources

- [BIS National Building Code](https://www.bis.gov.in/standards/national-building-code/?lang=en)
- [BIS Know Your Standard](https://www.bis.gov.in/know-your-standard/?lang=en)
- [BIS standards and revision programme](https://www.services.bis.gov.in/)
- [BIS copyright policy](https://www.bis.gov.in/copyright-policy/?lang=en)
- [Indian Roads Congress](https://irc.nic.in/)
- [CPHEEO, Ministry of Housing and Urban Affairs](https://www.mohua.gov.in/ministry/our-division/details/cpheeo-QDM1IzMtQWa)
- [Central Electricity Authority](https://cea.nic.in/)
- [Central Water Commission guidelines](https://cwc.gov.in/publication/guidelines)
- [Bureau of Energy Efficiency](https://beeindia.gov.in/)
- [Central Pollution Control Board](https://cpcb.nic.in/)

Authority pages are discovery inputs, not substitutes for project-approved applicability and licensed content.
