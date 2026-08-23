# Public Data Catalogue for the India Building Pilot

## 1. Purpose

This catalogue identifies actual data that can support the project before a private pilot dataset is available. It distinguishes:

- **Downloaded reusable data:** licence is sufficiently clear for local retention and testing.
- **Downloaded official academic reference:** public authority pages are preserved and prepared as labelled text with their source, access type, content scope, and academic-use label.
- **Link-only reference data:** publicly accessible, but copyright, project-purpose, or redistribution limits mean the repository stores only metadata and URLs.
- **Pilot-required data:** no sufficiently complete public source was found; an authorized project extract is necessary.

Public data is useful for developing parsers, metadata conventions, document-aware chunking, model identity, and cross-reference tests. It cannot prove the complete design-to-handover correlation chain.

## 2. Recommended public reference project

### Guwahati ICCC Building tender package

| Attribute | Finding |
|---|---|
| Authority | Guwahati Smart City Limited, Government of Assam |
| Project | Design, construction, commissioning, handover, five-year facilities management and O&M of an Integrated Command and Control Centre Building at Panjabari, Guwahati |
| Procurement basis | Design, Build and Operate |
| Publication | July 2020 tender package |
| Available data | NIT/bid data, RFP Volume I, 887-page Volume II scope and technical specifications, Volume III contract conditions, Volume IV/BOQ, and Volume V tender drawings split into eight files |
| Shared identifiers | Project title, volume/schedule references, drawing register and drawing numbers such as `TCE.10477A-CV-1007-RC-1001`, discipline codes, floors/locations and BOQ/specification structure |
| Structural system | Predominantly RCC rather than the intended steel-frame pilot |
| Correlation value | High for contract -> scope/specification -> BOQ -> drawing-register/drawing relationships; useful for revision/status and temporal-regulation exercises |
| Missing lifecycle data | Design calculations, native BIM, RFIs, submittal workflow, baseline/current schedule exports, procurement transactions, daily progress, material traceability, inspections, NCRs and handover records |
| Repository treatment | **Link only.** Tender drawings state that proprietary rights belong to the consulting engineer and restrict use to the stated project/purpose |

Official source: [GSCL ICCC Building tender page](https://gscl.assam.gov.in/latest/notice-inviting-tender-for-iccc-building)

This package should be used as a public **document reference corpus**, not represented as a complete project digital twin and not merged with unrelated IFC files as if they describe the same building.

## 3. Downloaded reusable data

### buildingSMART multidisciplinary IFC sample scene

| Attribute | Finding |
|---|---|
| Publisher | buildingSMART International |
| Licence | CC BY 4.0; local licence copy retained |
| Local location | `data/public/buildingsmart/ifc-pcert/` |
| Files | Architecture, structural, HVAC and landscaping IFC4 discipline models |
| Shared project key | All four files use IFC project GlobalId `2Ndyd$OSX7s9A04nc4lyye` |
| Correlation value | Tests project identity, discipline federation, spatial containment, IFC GUID extraction, object/property/material relationships and cross-model scoping |
| Limitation | A playful certification sample—not an Indian project, detailed steel fabrication model or execution record |

Official source: [buildingSMART Certification Datasets](https://github.com/buildingSMART/Certification-datasets)

### buildingSMART BCF test case

| Attribute | Finding |
|---|---|
| Publisher | buildingSMART International |
| Licence | CC BY-ND 4.0; local licence copy retained |
| Local location | `data/public/buildingsmart/bcf-test-cases/` |
| File | BCF 3.0 archive containing two topics, markup, viewpoints, snapshots, project/extensions data and document references |
| Correlation value | Tests issue/topic identity, comments/metadata, viewpoint/component references, snapshots, and BCF archive structure |
| Limitation | Conformance test data; it is not tied to the downloaded PCERT IFC scene and must remain unmodified if redistributed |

Official source: [buildingSMART BCF-XML test cases](https://github.com/buildingSMART/BCF-XML/tree/release_3_0/Test%20Cases)

Checksums, source URLs and licences are recorded in [the public-data manifest](../data/public/MANIFEST.csv).

### BIS public academic standards corpus

| Attribute | Finding |
|---|---|
| Publisher | Bureau of Indian Standards |
| Local location | `data/public/bis/academic/` |
| Coverage | 28 building/structural standard families; 88 standard or standard-part public preview records |
| Search corpus | 138 labelled text chunks in `INDEX.jsonl` |
| Preserved sources | 28 catalogue-search pages and 88 public preview pages |
| Labels | `public_official`, `academic_noncommercial`, `official_public_preview` |
| Content boundary | Each record says `public_preview_or_metadata_not_full_standard`; no preview is silently represented as a complete standard |
| Correlation value | Standard family, designation, status, source URL and public preview text can be connected to the future synthetic project's adopted-code register and requirements |

The complete source list, regeneration command, and query example are in the [BIS dataset README](../data/public/bis/academic/README.md). Publication status is retained exactly as returned by BIS; catalogue presence does not establish project applicability.

## 4. India standards and regulatory sources

These are official metadata/content sources. Public BIS catalogue and preview content is now stored and prepared as a portable labelled corpus for the academic demonstration. A separately obtained project copy remains a distinct governed source and must preserve its own access and adoption evidence.

| Source | Relevant data | Correlation use | Access treatment |
|---|---|---|---|
| [BIS Know Your Standard](https://www.bis.gov.in/know-your-standard/?lang=en) | Standard identity, public preview, amendments, publication status and committee metadata | `code -> edition/amendment/status -> project adoption -> clause` | Official public catalogue/preview snapshot prepared; exact content scope recorded per source |
| [BIS NBC](https://www.bis.gov.in/standards/national-building-code/?lang=en) | National Building Code identity, structure and BIS publication status | Building requirement taxonomy and referenced-standard discovery | Public BIS preview/catalogue entries prepared and status preserved; project edition still requires adoption evidence |
| [BIS standards programme](https://www.services.bis.gov.in/) | Published standards, revision programmes, wide-circulation drafts and technical committees | Prevent draft/revision/published-status confusion | Metadata/status only unless content use is authorized |
| [GMC acts and bye-laws](https://gmc.assam.gov.in/documents/acts-bye-laws) | Guwahati/Assam building rules and amendments through 2026 | Jurisdiction and `as_of_date` applicability for the Guwahati reference project | Link-only official legal/regulatory source |
| [Assam Unified Building Byelaws 2022](https://dohua.assam.gov.in/documents-detail/assam-unified-building-byelaws-2022) | State building controls | Later state-wide applicability and temporal comparison | Link-only official source |
| [Assam ECBC Code 2020](https://cei.assam.gov.in/documents-detail/assam-ecbc-code-2020) | State energy-code content and adoption | Project location/occupancy/threshold to energy requirements | Link-only official source |
| [Assam fire NOC forms](https://police.assam.gov.in/documents-detail/forms) | NOC applications, compliance reports and renewals | Fire requirement/condition -> submission -> approval evidence | Link-only; project NOC still required |

### Temporal caution for the Guwahati corpus

The tender was issued in July 2020. Current 2024–2026 Assam amendments cannot be assumed to govern it. A research dataset must preserve the tender/design date and separately identify the rules adopted by the contract or authority at that time.

## 5. India cost, contract and procurement reference sources

| Source | Relevant data | Correlation value | Limitation/treatment |
|---|---|---|---|
| [CPWD circular/publication catalogue](https://cpwd.gov.in/Circulars.aspx) | DSR/DAR, specifications, GCC, quality, works manuals, indices and correction slips | Item code -> description/unit/rate analysis -> contract clause -> correction slip/effective date | Official link-only reference; exact edition/corrections must be pinned |
| [CPWD DSR 2023 correction-slip page](https://cpwd.gov.in/AllCirculars.aspx?Type=36) | DSR corrections, including later slips | Versioned rate/item metadata and temporal validity | Not a project BOQ; link with edition/correction status |
| [CPWD DAR 2023 Volume I](https://cpwd.gov.in/Publication/CPWD_DAR_Vol_I_14092023-Civil.pdf) | Resource/rate analysis supporting scheduled items | BOQ item -> materials/labour/plant composition | Regional/time limitations; not proof of actual project cost |
| [CPWD cost indices](https://cpwd.gov.in/CostindPublic/PreviewPage.aspx) | Location/year cost indices | Location/date -> index -> normalized cost comparison | Requires applicable PAR/state/district/year selection |
| [Central Public Procurement Portal](https://eprocure.gov.in/eprocure/app) | Tender metadata, notices, BOQs and attachments where download remains available | Tender ID/reference -> document set -> BOQ/drawings/corrigenda | Per-tender rights and download windows vary; catalogue before copying |
| [CPPP fabricated structural-steel tender](https://eprocure.gov.in/eprocure/app?component=%24DirectLink&page=FrontEndViewTender&service=direct&sp=SJK9sM5FfQg5r8iW1thdM0g%3D%3D) | Tender `2020_BandR_604996_1`, steel-fabrication scope, attachment names, BOQ and drawing-package metadata | Strong steel procurement document-set example | Tender was cancelled and download period ended; metadata only |

## 6. Open data that may enrich a real pilot

Activate these only after the pilot location and use case require them:

| Authority/source family | Potential data | Project correlation |
|---|---|---|
| Survey of India / authorized project survey | Project control, topography and coordinate reference | Site/location/asset geometry and as-built comparison |
| Geological Survey of India / project geotechnical investigation | Regional geology plus site boreholes/tests | Site/foundation/design assumption; public regional data cannot replace site investigation |
| India Meteorological Department / project weather station | Historical weather and daily observations | Daily report/date/location -> weather -> productivity/delay evidence |
| CPCB and Assam Pollution Control Board | Limits, consent conditions and monitoring | Permit condition -> parameter/location/date -> measurement/exceedance/action |
| Bhuvan/NRSC and state GIS portals | Basemaps, terrain and thematic layers subject to terms | Project coordinates -> administrative/environmental/spatial context |

Licensing, scale, resolution, update date and fitness for engineering use must be recorded for each selected dataset.

## 7. Public-data gap analysis

No official public corpus found in this research pass provides all of the following as one correlated project:

- complete drawing/model revision history;
- design calculations tied to member/connection identities;
- RFI and submittal workflow history;
- P6 baseline plus updates and relationships;
- BOQ/cost/change transactions;
- PO -> MTC/heat -> piece/weld traceability;
- daily progress and installed quantities;
- ITP/inspection/NDT/NCR closure; and
- as-built/commissioning/handover evidence.

These are normally confidential operational records. They should be obtained through the authorized sample and handoff process in [Pilot Data Handoff](PILOT_DATA_HANDOFF.md), not scraped from unrelated projects.

## 8. Recommended corpus layers

| Layer | Data | Purpose |
|---|---|---|
| A — reusable technical tests | Downloaded buildingSMART IFC and BCF files | Parsers, IDs, spatial/model relations and file validation |
| B — India public reference | Prepared BIS public previews, GSCL tender links, Assam regulations and CPWD references | India terminology, standard scope/status, document hierarchy, clauses, BOQ/drawing references and temporal applicability |
| C — authorized pilot sample | One real steel-work-package sample chain | Validate master IDs, revisions, ACLs and end-to-end correlations |
| D — authorized pilot bulk data | Full governed pilot collection | Data-quality baselines and later deterministic retrieval evaluation |

Never imply that Layers A and B describe the same project. Cross-layer links are test mappings or domain references, not project facts.
