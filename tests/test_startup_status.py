import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.knowledge_base import ProgressEvent  # noqa: E402
from core.startup_status import StartupStatus  # noqa: E402


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
