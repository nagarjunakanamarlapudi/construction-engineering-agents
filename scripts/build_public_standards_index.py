#!/usr/bin/env python3
"""Download official BIS public previews and build a labelled academic text index."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

BIS_BASE_URL = "https://standardsbis.bsbedge.com/"
SEARCH_URL = BIS_BASE_URL + "BIS_SearchStandard.aspx?Standard_Number={query}&id=0"
USER_AGENT = "civil-engineering-agents-academic-research/1.0"


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.ignored_depth += 1
        elif self.ignored_depth == 0 and tag.lower() in {
            "p",
            "br",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.ignored_depth = max(0, self.ignored_depth - 1)
        elif self.ignored_depth == 0 and tag.lower() in {"p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            self.parts.append(data)


def visible_text(document: str) -> str:
    parser = VisibleTextParser()
    parser.feed(document)
    lines = []
    for raw_line in "".join(parser.parts).splitlines():
        normalized = re.sub(r"\s+", " ", html.unescape(raw_line)).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def clean_fragment(fragment: str) -> str:
    return re.sub(r"\s+", " ", visible_text(fragment)).strip()


def first_match(pattern: str, document: str) -> str:
    match = re.search(pattern, document, flags=re.IGNORECASE | re.DOTALL)
    return clean_fragment(match.group(1)) if match else ""


def parse_search_entries(document: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for block in re.findall(r"<li\b.*?</li>", document, flags=re.IGNORECASE | re.DOTALL):
        preview_id = first_match(r'href=["\']BIS_Preview\.aspx\?id=([^"\'&]+)', block)
        designation = first_match(
            r'<span[^>]*id=["\'][^"\']*lblstdno_rptr[^"\']*["\'][^>]*>(.*?)</span>',
            block,
        )
        if not preview_id or not designation:
            continue
        title = first_match(r'<span[^>]*class=["\']standard-title["\'][^>]*>(.*?)</span>', block)
        if not title:
            title = first_match(
                r'<span[^>]*style=["\'][^"\']*font-size\s*:\s*15px[^"\']*["\'][^>]*>(.*?)</span>',
                block,
            )
        status = first_match(
            r'<span[^>]*id=["\'][^"\']*lblstatus[^"\']*["\'][^>]*>(.*?)</span>', block
        )
        reaffirmed = first_match(r'<span[^>]*id=["\'][^"\']*lblreaff["\'][^>]*>(.*?)</span>', block)
        committee_match = re.search(
            r"Technical Committee\s*:\s*</span>\s*([^<\r\n]+)", block, flags=re.IGNORECASE
        )
        committee = re.sub(r"\s+", " ", committee_match.group(1)).strip() if committee_match else ""
        amendment_count = first_match(
            r'<a[^>]*id=["\'][^"\']*noanmds[^"\']*["\'][^>]*>(.*?)</a>', block
        )
        entries.append(
            {
                "preview_id": preview_id,
                "designation": designation,
                "title": title,
                "status": status,
                "reaffirmed": reaffirmed,
                "technical_committee": committee,
                "amendment_count": amendment_count,
            }
        )
    return entries


def chunk_text(text: str, maximum_words: int = 220, overlap_words: int = 30) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + maximum_words)
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def fetch_bytes(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "standardsbis.bsbedge.com":
        raise ValueError(f"Refusing non-BIS or non-HTTPS URL: {url}")
    request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urlopen(request, timeout=45) as response:  # noqa: S310
        return response.read()


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    serialized = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(serialized, encoding="utf-8")


def build_index(sources_path: Path, output_dir: Path, fixture_dir: Path | None) -> tuple[int, int]:
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    manifest: list[dict[str, object]] = []
    index: list[dict[str, object]] = []
    retrieved_at = datetime.now(UTC).isoformat()

    for family in sources:
        family_id = family["family_id"]
        query = family["query"]
        designation_pattern = re.compile(family["designation_regex"], flags=re.IGNORECASE)
        search_url = SEARCH_URL.format(query=quote_plus(query))

        if fixture_dir:
            search_document = (fixture_dir / f"{family_id}-search.html").read_text(encoding="utf-8")
        else:
            search_bytes = fetch_bytes(search_url)
            search_document = search_bytes.decode("utf-8", errors="replace")
            (raw_dir / f"{family_id}-search.html").write_bytes(search_bytes)

        matching_entries = [
            entry
            for entry in parse_search_entries(search_document)
            if designation_pattern.search(entry["designation"])
        ]
        if not matching_entries:
            raise ValueError(f"No matching BIS entry for configured family {family_id}")

        for entry in matching_entries:
            preview_id = entry["preview_id"]
            preview_url = urljoin(BIS_BASE_URL, f"BIS_Preview.aspx?id={preview_id}")
            if fixture_dir:
                fixture_path = fixture_dir / f"{preview_id}-preview.html"
                preview_bytes = fixture_path.read_bytes()
            else:
                preview_bytes = fetch_bytes(preview_url)

            raw_path = raw_dir / f"{preview_id}-preview.html"
            raw_path.write_bytes(preview_bytes)
            checksum = hashlib.sha256(preview_bytes).hexdigest()
            extracted_text = visible_text(preview_bytes.decode("utf-8", errors="replace"))
            chunks = chunk_text(extracted_text)
            source_id = "bis-" + re.sub(r"[^a-z0-9]+", "-", preview_id.lower()).strip("-")

            record: dict[str, object] = {
                "source_id": source_id,
                "family_id": family_id,
                "pilot_module": family["pilot_module"],
                "publisher": "Bureau of Indian Standards",
                "designation": entry["designation"],
                "title": entry["title"],
                "status": entry["status"],
                "reaffirmed": entry["reaffirmed"],
                "technical_committee": entry["technical_committee"],
                "amendment_count": entry["amendment_count"],
                "source_url": preview_url,
                "catalogue_url": search_url,
                "data_origin": "public_official",
                "usage": "academic_noncommercial",
                "access_type": "official_public_preview",
                "content_scope": "public_preview_or_metadata_not_full_standard",
                "retrieved_at": retrieved_at,
                "bytes": len(preview_bytes),
                "sha256": checksum,
                "raw_path": str(raw_path.relative_to(output_dir)),
                "text_characters": len(extracted_text),
                "chunk_count": len(chunks),
            }
            manifest.append(record)

            for number, text in enumerate(chunks, start=1):
                index.append(
                    {
                        "chunk_id": f"{source_id}-chunk-{number:04d}",
                        "source_id": source_id,
                        "family_id": family_id,
                        "pilot_module": family["pilot_module"],
                        "publisher": "Bureau of Indian Standards",
                        "designation": entry["designation"],
                        "title": entry["title"],
                        "status": entry["status"],
                        "source_url": preview_url,
                        "data_origin": "public_official",
                        "usage": "academic_noncommercial",
                        "access_type": "official_public_preview",
                        "content_scope": "public_preview_or_metadata_not_full_standard",
                        "sha256": checksum,
                        "text": text,
                    }
                )

    write_jsonl(output_dir / "MANIFEST.jsonl", manifest)
    write_jsonl(output_dir / "INDEX.jsonl", index)
    return len(manifest), len(index)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--fixture-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        source_count, chunk_count = build_index(
            arguments.sources, arguments.output_dir, arguments.fixture_dir
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(
        json.dumps({"indexed_sources": source_count, "indexed_chunks": chunk_count}, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
