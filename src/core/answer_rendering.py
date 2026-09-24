from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict, cast

from core.citations import CitationKind, CitationRecord
from core.message_utils import escape_model_markdown


AnswerBlockKind = Literal["markdown", "quran", "hadith"]


class AnswerBlock(TypedDict):
    """One ordered, safe-to-render part of a model answer.

    ``markdown`` text has model HTML escaped and may be rendered as native
    Markdown. Quran and Hadith text is plain component data; React must insert
    it as text, never as HTML.
    """

    kind: AnswerBlockKind
    text: str
    title: str | None
    locator: str | None
    grading: str | None


class RenderedAnswer(TypedDict):
    """Semantic blocks plus a persistence-friendly native-Markdown fallback."""

    blocks: list[AnswerBlock]
    fallback_markdown: str
    has_cards: bool


_TAG_TOKEN = re.compile(r"<[^<>]*>")
_TAGLIKE_START = re.compile(r"</?[A-Za-z]")
_OPEN_TAG = re.compile(
    r"<(?P<kind>quran|hadith)"
    r"(?:\s+ref\s*=\s*(?:\"(?P<double_ref>[^\"]*)\"|'(?P<single_ref>[^']*)'))?\s*>"
)
_CLOSE_TAG = re.compile(r"</(?P<kind>quran|hadith)\s*>")
_SEMANTIC_TAG = re.compile(r"</?(?:quran|hadith)\b[^<>]*>", re.IGNORECASE)
_MARKDOWN_LITERAL = re.compile(r"([\\`*_[\]{}()#+.!|>~-])")
_CARD_SCAFFOLD_LINE = re.compile(r"[ \t]*(?:>[ \t]*)*(?:[-*+]|\d{1,9}[.)])?[ \t]*")


def _normalize_for_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    words = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(words.split())


def _safe_citation(record: Mapping[str, object]) -> CitationRecord | None:
    kind = record.get("kind")
    citation_id = record.get("id")
    text = record.get("text")
    title = record.get("title")
    locator = record.get("locator")
    grading = record.get("grading")
    if (
        kind not in ("quran", "hadith")
        or not isinstance(citation_id, str)
        or not isinstance(text, str)
        or not isinstance(title, str)
        or not isinstance(locator, str)
        or (grading is not None and not isinstance(grading, str))
    ):
        return None
    return {
        "id": citation_id,
        "kind": cast(CitationKind, kind),
        "text": text,
        "title": title,
        "locator": locator,
        "grading": grading,
    }


def _current_citations(records: Sequence[CitationRecord]) -> list[CitationRecord]:
    safe: list[CitationRecord] = []
    seen: set[tuple[str, CitationKind]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        citation = _safe_citation(record)
        if citation is None:
            continue
        key = (citation["id"], citation["kind"])
        if key in seen:
            continue
        seen.add(key)
        safe.append(citation)
    return safe


def _contains_excerpt(record: CitationRecord, excerpt: str) -> bool:
    normalized_excerpt = _normalize_for_match(excerpt)
    normalized_source = _normalize_for_match(record["text"])
    return bool(normalized_excerpt) and normalized_excerpt in normalized_source


def _match_citation(
    kind: CitationKind,
    excerpt: str,
    requested_ref: str | None,
    citations: Sequence[CitationRecord],
) -> CitationRecord | None:
    same_kind = [record for record in citations if record["kind"] == kind]
    if requested_ref:
        referenced = next(
            (record for record in same_kind if record["id"] == requested_ref),
            None,
        )
        if referenced is not None and _contains_excerpt(referenced, excerpt):
            return referenced

    matches = [record for record in same_kind if _contains_excerpt(record, excerpt)]
    return matches[0] if len(matches) == 1 else None


def _without_dangling_scaffold(text: str) -> str:
    """Drop a trailing list or quote marker that only introduced a card.

    Models routinely give each excerpt its own list item. A card is lifted out
    of the list into a block of its own, so the marker that introduced it would
    otherwise be left behind alone and render as an empty bullet.
    """
    head, separator, last_line = text.rpartition("\n")
    if not _CARD_SCAFFOLD_LINE.fullmatch(last_line):
        return text
    return head if separator else ""


def _markdown_block(text: str) -> AnswerBlock | None:
    safe_text = escape_model_markdown(text).strip()
    if not safe_text:
        return None
    return {
        "kind": "markdown",
        "text": safe_text,
        "title": None,
        "locator": None,
        "grading": None,
    }


def _parse_blocks(
    text: str,
    citations: Sequence[CitationRecord],
) -> list[AnswerBlock] | None:
    blocks: list[AnswerBlock] = []
    active: tuple[CitationKind, str | None, int] | None = None
    cursor = 0
    token_spans: list[tuple[int, int]] = []

    for token_match in _TAG_TOKEN.finditer(text):
        token_spans.append(token_match.span())
        token = token_match.group(0)
        opening = _OPEN_TAG.fullmatch(token)
        closing = _CLOSE_TAG.fullmatch(token)

        if opening is not None:
            if active is not None:
                return None
            prose = _markdown_block(_without_dangling_scaffold(text[cursor : token_match.start()]))
            if prose is not None:
                blocks.append(prose)
            reference = opening.group("double_ref")
            if reference is None:
                reference = opening.group("single_ref")
            active = (
                cast(CitationKind, opening.group("kind")),
                reference.strip() if reference is not None else None,
                token_match.end(),
            )
            continue

        if closing is not None:
            if active is None or closing.group("kind") != active[0]:
                return None
            kind, reference, content_start = active
            excerpt = text[content_start : token_match.start()].strip()
            if not excerpt:
                return None
            citation = _match_citation(kind, excerpt, reference, citations)
            blocks.append(
                {
                    "kind": kind,
                    "text": excerpt,
                    "title": citation["title"] if citation is not None else None,
                    "locator": citation["locator"] if citation is not None else None,
                    "grading": citation["grading"] if citation is not None else None,
                }
            )
            active = None
            cursor = token_match.end()
            continue

        # Any element other than the two exact semantic tags invalidates the
        # semantic parse. It will be neutralized in the native-Markdown fallback.
        return None

    if active is not None:
        return None

    # Catch dangling constructs such as ``<hadith`` that have no closing angle
    # bracket and therefore were not captured as tokens above.
    residual_parts: list[str] = []
    residual_cursor = 0
    for start, end in token_spans:
        residual_parts.append(text[residual_cursor:start])
        residual_cursor = end
    residual_parts.append(text[residual_cursor:])
    if _TAGLIKE_START.search("".join(residual_parts)):
        return None

    tail = _markdown_block(text[cursor:])
    if tail is not None:
        blocks.append(tail)
    return blocks


def _literal_markdown(value: str) -> str:
    escaped_html = html.escape(value, quote=False)
    return _MARKDOWN_LITERAL.sub(r"\\\1", escaped_html)


def _quoted_markdown(block: AnswerBlock) -> str:
    literal = _literal_markdown(block["text"].strip())
    lines = literal.splitlines() or [literal]
    output = [f"> {line}" if line else ">" for line in lines]

    if block["title"] is not None and block["locator"] is not None:
        footer = [block["title"], block["locator"]]
        if block["grading"]:
            footer.append(block["grading"])
        trusted_footer = " · ".join(_literal_markdown(item) for item in footer)
        output.extend([">", f"> — *{trusted_footer}*"])
    return "\n".join(output)


def _fallback_from_blocks(blocks: Sequence[AnswerBlock]) -> str:
    sections: list[str] = []
    for block in blocks:
        if block["kind"] == "markdown":
            section = block["text"].strip()
        else:
            section = _quoted_markdown(block)
        if section:
            sections.append(section)
    return "\n\n".join(sections)


def _invalid_markup_fallback(text: str) -> str:
    # Remove only attempted semantic wrappers so users do not see internal
    # protocol tags. Other model HTML is escaped and displayed as inert text.
    without_semantic_wrappers = _SEMANTIC_TAG.sub("", text)
    return escape_model_markdown(without_semantic_wrappers).strip()


def render_semantic_answer(
    text: str,
    citations: Sequence[CitationRecord] = (),
) -> RenderedAnswer:
    """Parse IslamAI's tiny answer markup without executing model HTML.

    Only lowercase, non-nested ``quran`` and ``hadith`` elements are accepted.
    A sole optional ``ref`` attribute may select a current-run citation, but a
    trusted footer is added only when the quoted excerpt is found in that
    same-kind record. Invalid markup always degrades to escaped Markdown.
    """

    current_citations = _current_citations(citations)
    blocks = _parse_blocks(text, current_citations)
    if blocks is None:
        fallback = _invalid_markup_fallback(text)
        fallback_block: AnswerBlock | None = None
        if fallback:
            fallback_block = {
                "kind": "markdown",
                "text": fallback,
                "title": None,
                "locator": None,
                "grading": None,
            }
        return {
            "blocks": [fallback_block] if fallback_block is not None else [],
            "fallback_markdown": fallback,
            "has_cards": False,
        }

    fallback = _fallback_from_blocks(blocks)
    return {
        "blocks": blocks,
        "fallback_markdown": fallback,
        "has_cards": any(block["kind"] != "markdown" for block in blocks),
    }
