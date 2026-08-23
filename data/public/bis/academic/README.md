# BIS Public Academic Standards Corpus

This directory contains an academic snapshot of official public Bureau of Indian Standards (BIS) catalogue and preview pages for the India building/structural pilot.

## Snapshot summary

Retrieved on 22 August 2026:

- 28 configured standard families;
- 88 matching BIS standard or standard-part preview records;
- 138 searchable text chunks; and
- 116 preserved HTML files: 28 catalogue-search responses plus 88 public preview pages.

The selected families cover structural steel, steel materials and sections, welding, fabrication, erection, loads, earthquakes, concrete, reinforcement, concrete testing, soils, foundations, excavation safety, and the National Building Code family.

## Files

| Path | Purpose |
|---|---|
| `SOURCES.json` | The configured pilot families, BIS search terms, exact designation rules, and project modules |
| `raw/` | Unmodified public BIS catalogue-search and preview HTML retrieved by the script |
| `terms/` | Official BIS copyright-policy snapshot and standard-download guidance retained with the dataset |
| `MANIFEST.jsonl` | One provenance record for each prepared BIS preview page, including source URL, status, checksum, size, and chunk count |
| `INDEX.jsonl` | Searchable text chunks with their source and academic-use labels attached |

## Required labels

Every prepared chunk carries:

```text
data_origin: public_official
usage: academic_noncommercial
access_type: official_public_preview
content_scope: public_preview_or_metadata_not_full_standard
```

The last label is important. BIS public preview pages vary in length. This collection does not claim that a preview is the complete standard.

Publication status is stored exactly as returned by the BIS catalogue. A listed or active standard is not automatically applicable to a particular project. Project applicability still depends on the contract, location, design date, approving authority, amendments, and approved design basis.

## Rebuild

From the repository root:

```bash
python3 scripts/build_public_standards_index.py \
  --sources data/public/bis/academic/SOURCES.json \
  --output-dir data/public/bis/academic
```

The script uses only public BIS pages reachable without authentication or CAPTCHA bypass. It preserves the downloaded HTML, calculates a SHA-256 checksum, removes script/style content from searchable text, and writes labelled chunks.

Run the tests with:

```bash
python3 -m unittest discover -s tests -p 'test_public_standards_ingest.py' -v
```

## Simple local query

This command finds chunks mentioning hot-rolled steel and returns their standard, source URL, and text:

```bash
jq -r '
  select(.text | test("hot[ -]?rolled steel"; "i")) |
  [.designation, .source_url, .text] | @tsv
' data/public/bis/academic/INDEX.jsonl
```

`INDEX.jsonl` is a portable JSON Lines corpus for later exact, hybrid, and agentic retrieval demonstrations. The filename does not imply a running database: the selected Qdrant service, RAG application, and agent are not running.
