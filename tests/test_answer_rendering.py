from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.answer_rendering import render_semantic_answer  # noqa: E402
from core.citations import CitationRecord  # noqa: E402


QURAN: CitationRecord = {
    "id": "Q-2-255",
    "kind": "quran",
    "text": "Allah—there is no deity except Him, the Ever-Living, the Sustainer of existence.",
    "title": "Al-Baqarah",
    "locator": "Quran 2:255",
    "grading": None,
}
HADITH: CitationRecord = {
    "id": "H-bukhari-1",
    "kind": "hadith",
    "text": "Actions are judged by intentions, and every person will have what they intended.",
    "title": "Sahih al-Bukhari",
    "locator": "Hadith 1",
    "grading": "Sahih",
}


def test_preserves_order_and_builds_trusted_tag_free_fallback():
    answer = (
        "The sources teach both principles.\n\n"
        '<quran ref="Q-2-255">Allah—there is no deity except Him.</quran>\n\n'
        "Likewise:\n\n"
        "<hadith>Actions are judged by intentions.</hadith>"
    )

    rendered = render_semantic_answer(answer, [QURAN, HADITH])

    assert [block["kind"] for block in rendered["blocks"]] == [
        "markdown",
        "quran",
        "markdown",
        "hadith",
    ]
    assert rendered["blocks"][1]["title"] == "Al-Baqarah"
    assert rendered["blocks"][1]["locator"] == "Quran 2:255"
    assert rendered["blocks"][3]["title"] == "Sahih al-Bukhari"
    assert rendered["blocks"][3]["grading"] == "Sahih"
    assert rendered["has_cards"] is True
    assert "<quran" not in rendered["fallback_markdown"]
    assert "<hadith" not in rendered["fallback_markdown"]
    assert "> Allah—there is no deity except Him\\." in rendered["fallback_markdown"]
    assert r"Al\-Baqarah · Quran 2:255" in rendered["fallback_markdown"]
    assert r"Sahih al\-Bukhari · Hadith 1 · Sahih" in rendered["fallback_markdown"]


@pytest.mark.parametrize(
    "marker",
    ["-", "*", "+", "1.", "2)", ">", "> -", "  -"],
)
def test_marker_that_only_introduced_a_card_leaves_no_empty_bullet(marker: str):
    answer = (
        "The sources teach both principles.\n\n"
        f"{marker} <quran>Allah\u2014there is no deity except Him.</quran>\n"
        f"{marker} <hadith>Actions are judged by intentions.</hadith>"
    )

    rendered = render_semantic_answer(answer, [QURAN, HADITH])

    assert [block["kind"] for block in rendered["blocks"]] == [
        "markdown",
        "quran",
        "hadith",
    ]
    assert rendered["blocks"][0]["text"] == "The sources teach both principles."
    # A bare ``>`` is the quote renderer's own separator, so only list markers
    # can be judged orphaned by scanning the fallback.
    assert not [
        line
        for line in rendered["fallback_markdown"].splitlines()
        if line.strip() in {"-", "*", "+", "1.", "2)"}
    ]


def test_text_before_a_card_survives_marker_cleanup():
    answer = (
        "Prose.\n\n"
        "---\n\n"
        "- Divine ownership: <quran>Allah\u2014there is no deity except Him.</quran>\n"
        "As reported, <hadith>Actions are judged by intentions.</hadith>"
    )

    rendered = render_semantic_answer(answer, [QURAN, HADITH])

    assert [block["text"] for block in rendered["blocks"] if block["kind"] == "markdown"] == [
        "Prose.\n\n---\n\n- Divine ownership:",
        "As reported,",
    ]


def test_ref_must_match_kind_and_normalized_partial_excerpt():
    answer = '<hadith ref="Q-2-255">“ACTIONS” are judged by intentions!</hadith>'

    rendered = render_semantic_answer(answer, [QURAN, HADITH])

    # The wrong-kind ref is ignored; a unique normalized same-kind match wins.
    assert rendered["blocks"][0]["title"] == "Sahih al-Bukhari"
    assert rendered["blocks"][0]["locator"] == "Hadith 1"


def test_invalid_ref_falls_back_to_unique_same_kind_excerpt_match():
    rendered = render_semantic_answer(
        '<quran ref="Q-does-not-exist">the Ever Living, the Sustainer</quran>',
        [QURAN, HADITH],
    )

    assert rendered["blocks"][0]["title"] == "Al-Baqarah"
    assert rendered["blocks"][0]["locator"] == "Quran 2:255"


def test_ambiguous_excerpt_never_invents_a_footer():
    second = dict(HADITH)
    second["id"] = "H-muslim-2"
    second["title"] = "Sahih Muslim"

    rendered = render_semantic_answer("<hadith>Actions are judged</hadith>", [HADITH, second])

    assert rendered["blocks"][0]["title"] is None
    assert rendered["blocks"][0]["locator"] is None
    assert "Sahih al-Bukhari" not in rendered["fallback_markdown"]
    assert "Sahih Muslim" not in rendered["fallback_markdown"]


def test_ref_with_nonmatching_excerpt_cannot_force_footer():
    rendered = render_semantic_answer(
        '<hadith ref="H-bukhari-1">A sentence Gemini invented.</hadith>',
        [HADITH],
    )

    assert rendered["blocks"][0]["title"] is None
    assert rendered["blocks"][0]["locator"] is None
    assert "Hadith 1" not in rendered["fallback_markdown"]


@pytest.mark.parametrize(
    "answer",
    [
        "<Hadith>Actions are judged by intentions.</Hadith>",
        '<hadith class="pretty">Actions are judged by intentions.</hadith>',
        "<hadith>outer <quran>inner</quran></hadith>",
        "<hadith>mismatched</quran>",
        "<hadith>unclosed",
        "<unknown>model HTML</unknown>",
    ],
)
def test_invalid_or_unknown_markup_degrades_without_rejection(answer: str):
    rendered = render_semantic_answer(answer, [HADITH, QURAN])

    assert rendered["has_cards"] is False
    assert all(block["kind"] == "markdown" for block in rendered["blocks"])
    assert "<hadith" not in rendered["fallback_markdown"].lower()
    assert "<quran" not in rendered["fallback_markdown"].lower()


def test_unknown_model_html_is_inert_and_plain_markdown_survives():
    answer = '<script>alert("x")</script> **A normal answer**\n> a quote'

    rendered = render_semantic_answer(answer)

    assert rendered["has_cards"] is False
    assert "<script>" not in rendered["fallback_markdown"]
    assert "&lt;script>" in rendered["fallback_markdown"]
    assert rendered["blocks"][0]["text"] == rendered["fallback_markdown"]
    assert "**A normal answer**" in rendered["fallback_markdown"]
    assert "\n> a quote" in rendered["fallback_markdown"]


def test_artifact_is_allowlisted_and_does_not_leak_local_paths():
    artifact = {
        **HADITH,
        "source_file": r"C:\\Users\\person\\private\\hadith.json",
        "metadata": {"secret": "not for the client"},
    }

    rendered = render_semantic_answer(
        "<hadith>Actions are judged by intentions.</hadith>",
        [artifact],  # type: ignore[list-item]
    )

    block = rendered["blocks"][0]
    assert block == {
        "kind": "hadith",
        "text": "Actions are judged by intentions.",
        "title": "Sahih al-Bukhari",
        "locator": "Hadith 1",
        "grading": "Sahih",
    }
    assert "source_file" not in block
    assert "id" not in block
    assert r"C:\\Users" not in str(rendered)


def test_empty_ref_is_treated_as_absent_and_matches_unique_excerpt():
    rendered = render_semantic_answer(
        '<hadith ref="">Actions are judged by intentions.</hadith>',
        [HADITH],
    )

    assert rendered["blocks"][0]["title"] == "Sahih al-Bukhari"
