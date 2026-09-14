import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.knowledge_base import ProgressEvent  # noqa: E402
from core.startup_status import StartupStatus, describe_failure  # noqa: E402


def test_startup_status_replays_specific_progress_and_ready_state():
    status = StartupStatus()
    status.begin()
    first = status.snapshot()
    status.record(ProgressEvent("index_hadith", 4, 10, "eng-malik.json"))
    indexing = status.snapshot()
    replayed = status.snapshot()
    status.record(ProgressEvent("ready", 1, 1, "bundled-0.1"))
    ready = status.snapshot()

    assert first.state == "running"
    assert "Starting" not in first.render()
    assert "Building the Hadith search index (4/10) — eng-malik.json" in indexing.render()
    assert replayed == indexing
    assert ready.render() == "**Local Quran and Hadith search is ready.**"
    assert first.version < indexing.version < ready.version


def test_startup_status_failure_is_safe_and_actionable():
    status = StartupStatus()
    status.begin()
    status.fail("The last valid local corpus was retained. Restart the chat to retry.")

    rendered = status.snapshot().render()

    assert "failed safely" in rendered
    assert "last valid local corpus was retained" in rendered


def test_describe_failure_names_only_corpus_manifest_details():
    from core.corpus_manifest import CorpusManifestError

    manifest_failure = CorpusManifestError("SHA-256 mismatch for quran/metadata/surah.json")
    other_failure = RuntimeError("secret=abc123 must never appear")

    assert describe_failure(manifest_failure) == (
        "CorpusManifestError: SHA-256 mismatch for quran/metadata/surah.json"
    )
    assert describe_failure(other_failure) == "RuntimeError"


def test_bootstrap_failure_surfaces_the_corpus_problem_in_chat():
    app_source = (PROJECT_ROOT / "src" / "app.py").read_text(encoding="utf-8")

    assert 'f"{describe_failure(exc)}' in app_source
    assert (
        "type(exc).__name__"
        not in app_source.split("_run_knowledge_base_bootstrap")[1].split("async def")[0]
    )
