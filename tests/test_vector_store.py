import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import DEFAULT_MODEL_INSTRUCTION  # noqa: E402
from core.vector_store import VectorStoreManager  # noqa: E402


class FakeIndex:
    def __init__(self):
        self.calls = []

    def similarity_search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return ["result"]


def test_search_applies_bge_query_instruction():
    manager = VectorStoreManager(SimpleNamespace(), index_path="unused")
    manager.vector_store = FakeIndex()

    result = manager.search(" signs of creation ", top_k=3, filter_dict={"type": "quran"})

    assert result == ["result"]
    query, kwargs = manager.vector_store.calls[0]
    assert query == DEFAULT_MODEL_INSTRUCTION + "signs of creation"
    assert kwargs == {"k": 3, "filter": {"type": "quran"}}
