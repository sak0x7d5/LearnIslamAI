from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import ToolMessage

from core.source_manager import SourceManager


CitationKind = Literal["quran", "hadith"]


class CitationRecord(TypedDict):
    id: str
    kind: CitationKind
    text: str
    title: str
    locator: str
    grading: str | None


@dataclass(frozen=True)
class CitationValidation:
    valid: bool
    cited_ids: tuple[str, ...]
    unknown_ids: tuple[str, ...]
    reason: str | None = None


CITATION_MARKER_RE = re.compile(r"\[\[cite:([A-Za-z0-9._:-]+)\]\]")


def _slug(value: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return cleaned or "source"


def _number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _grading(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        grade = value.get("grade")
        author = value.get("name") or value.get("author")
        if grade and author:
            return f"{grade} — {author}"
        return str(grade or author) if grade or author else None
    if isinstance(value, list):
        values = [item for item in (_grading(item) for item in value) if item]
        return "; ".join(values) or None
    return str(value)


def citation_from_document(
    document: Document,
    *,
    kind: CitationKind,
    source_manager: SourceManager,
) -> CitationRecord:
    metadata = dict(document.metadata)
    text = source_manager.get_full_text(metadata) or document.page_content
    if kind == "quran":
        surah = _number(metadata.get("surah_number", "?"))
        ayah = _number(metadata.get("ayah_number", "?"))
        title = metadata.get("surah_name") or f"Surah {surah}"
        locator = f"Quran {surah}:{ayah}"
        citation_id = f"Q-{surah}-{ayah}"
        grading = None
    else:
        title = str(metadata.get("name") or Path(str(metadata.get("source_file", "Hadith"))).stem)
        hadith_number = _number(metadata.get("hadithnumber", "?"))
        locator = f"Hadith {hadith_number}"
        citation_id = f"H-{_slug(title)}-{_slug(hadith_number)}"
        grading = _grading(metadata.get("grades") or metadata.get("grading"))

    if "?" in citation_id:
        digest = hashlib.sha256(f"{kind}|{title}|{locator}|{text}".encode("utf-8")).hexdigest()[:12]
        citation_id = f"{kind[0].upper()}-{digest}"

    return {
        "id": citation_id,
        "kind": kind,
        "text": text.strip(),
        "title": str(title),
        "locator": locator,
        "grading": grading,
    }


def deduplicate_citations(records: list[CitationRecord]) -> list[CitationRecord]:
    output: list[CitationRecord] = []
    seen: set[str] = set()
    for record in records:
        if record["id"] not in seen:
            seen.add(record["id"])
            output.append(record)
    return output


def format_tool_content(records: list[CitationRecord]) -> str:
    if not records:
        return "No relevant source records were found."
    blocks = []
    for record in records:
        grading = f"\nGrading: {record['grading']}" if record["grading"] else ""
        blocks.append(
            f"Source ID: {record['id']}\n"
            f"Source: {record['title']} — {record['locator']}{grading}\n"
            f"Text: {record['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def collect_citations(messages: list[Any]) -> list[CitationRecord]:
    records: list[CitationRecord] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        artifact = getattr(message, "artifact", None)
        candidates = artifact.get("citations", []) if isinstance(artifact, dict) else artifact
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            required = {"id", "kind", "text", "title", "locator", "grading"}
            if required.issubset(candidate):
                records.append(candidate)  # type: ignore[arg-type]
    return deduplicate_citations(records)


def validate_citations(answer: str, records: list[CitationRecord]) -> CitationValidation:
    cited = tuple(dict.fromkeys(CITATION_MARKER_RE.findall(answer)))
    allowed = {record["id"] for record in records}
    unknown = tuple(identifier for identifier in cited if identifier not in allowed)
    if unknown:
        return CitationValidation(False, cited, unknown, "unknown citation IDs")
    if records and not cited:
        return CitationValidation(False, cited, (), "retrieved sources were not cited")
    return CitationValidation(True, cited, ())


def ordered_citations(answer: str, records: list[CitationRecord]) -> list[CitationRecord]:
    by_id = {record["id"]: record for record in records}
    return [
        by_id[item] for item in dict.fromkeys(CITATION_MARKER_RE.findall(answer)) if item in by_id
    ]


def render_citation_markers(answer: str, records: list[CitationRecord]) -> str:
    by_id = {record["id"]: record for record in records}

    def replace(match: re.Match[str]) -> str:
        record = by_id.get(match.group(1))
        if not record:
            return "[unverified source]"
        # The identifier is restricted by CITATION_MARKER_RE and therefore cannot
        # inject Markdown. Human-readable source details remain in the React card,
        # where string props are escaped by React.
        return f"[{record['id']}]"

    return CITATION_MARKER_RE.sub(replace, html.escape(answer, quote=False))
