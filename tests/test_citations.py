import json
import sys
from pathlib import Path

from langchain_core.documents import Document


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.citations import (  # noqa: E402
    citation_from_document,
    deduplicate_citations,
    format_tool_content,
)
from core.source_manager import SourceManager  # noqa: E402


def test_quran_citation_hydrates_actual_schema(tmp_path):
    source = tmp_path / "quran.json"
    source.write_text(
        json.dumps({"2:255": {"t": "Allah—there is no deity except Him."}}), encoding="utf-8"
    )
    manager = SourceManager(tmp_path, allowed_roots=(tmp_path,))
    doc = Document(
        page_content="chunk",
        metadata={
            "type": "quran",
            "source_file": str(source),
            "json_key": "2:255",
            "surah_number": 2,
            "ayah_number": 255,
            "surah_name": "Al-Baqarah",
        },
    )

    record = citation_from_document(doc, kind="quran", source_manager=manager)

    assert record["id"] == "Q-2-255"
    assert record["text"] == "Allah—there is no deity except Him."
    assert record["locator"] == "Quran 2:255"
    assert "source_file" not in record


def test_hadith_citation_has_deterministic_id_and_grading(tmp_path):
    source = tmp_path / "hadith.json"
    source.write_text(
        json.dumps({"hadiths": [{"text": "Actions are judged by intentions."}]}), encoding="utf-8"
    )
    manager = SourceManager(tmp_path, allowed_roots=(tmp_path,))
    doc = Document(
        page_content="chunk",
        metadata={
            "type": "hadith",
            "source_file": str(source),
            "array_index": 0,
            "name": "Sahih al-Bukhari",
            "hadithnumber": 1.0,
            "grades": [{"grade": "Sahih", "author": "Scholar"}],
        },
    )

    record = citation_from_document(doc, kind="hadith", source_manager=manager)

    assert record["id"] == "H-sahih-al-bukhari-1"
    assert record["grading"] == "Sahih — Scholar"


def test_tool_content_uses_human_readable_sources_without_internal_ids():
    first = {
        "id": "Q-2-255",
        "kind": "quran",
        "text": "Allah—there is no deity except Him.",
        "title": "Al-Baqarah",
        "locator": "Quran 2:255",
        "grading": None,
    }
    second = {
        "id": "H-muslim-1",
        "kind": "hadith",
        "text": "y",
        "title": "Sahih Muslim",
        "locator": "Hadith 1",
        "grading": "Sahih",
    }

    records = deduplicate_citations([first, second, first])
    content = format_tool_content(records)

    assert [item["id"] for item in records] == ["Q-2-255", "H-muslim-1"]
    assert "Source: Al-Baqarah — Quran 2:255" in content
    assert "Source: Sahih Muslim — Hadith 1" in content
    assert "Source ID:" not in content
    assert "source_file" not in content


def test_source_manager_rejects_path_traversal(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text('{"value": "do not read"}', encoding="utf-8")
    manager = SourceManager(root, allowed_roots=(root,))

    assert (
        manager.get_full_text({"type": "quran", "source_file": "../secret.json", "json_key": "1:1"})
        is None
    )


def test_source_manager_hydrates_stable_id_after_staging_move(tmp_path):
    staging_data = tmp_path / "staging" / "release" / "data"
    source = staging_data / "quran" / "english" / "quran.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"2:255": {"t": "Exact activated verse"}}), encoding="utf-8")
    stale_absolute_path = str(source)

    active_release = tmp_path / "versions" / "v2"
    active_release.parent.mkdir(parents=True)
    (tmp_path / "staging" / "release").replace(active_release)
    active_data = active_release / "data"
    manager = SourceManager(active_data, allowed_roots=(active_data,))

    hydrated = manager.get_full_text(
        {
            "type": "quran",
            "source_id": "quran/english/quran.json",
            "source_file": stale_absolute_path,
            "json_key": "2:255",
        }
    )

    assert hydrated == "Exact activated verse"
