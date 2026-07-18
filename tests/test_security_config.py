import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_chainlit_uses_local_safe_defaults():
    with (ROOT / ".chainlit" / "config.toml").open("rb") as handle:
        config = tomllib.load(handle)

    assert config["project"]["allow_origins"] == [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]
    assert config["features"]["unsafe_allow_html"] is False
    assert config["features"]["spontaneous_file_upload"]["enabled"] is False
    assert config["UI"]["cot"] == "tool_call"
    assert config["project"]["persist_user_env"] is False


def test_custom_elements_do_not_render_raw_html_or_receive_source_paths():
    citation = (ROOT / "public" / "elements" / "CitationCard.jsx").read_text(encoding="utf-8")
    key_form = (ROOT / "public" / "elements" / "ApiKeyForm.jsx").read_text(encoding="utf-8")

    assert "dangerouslySetInnerHTML" not in citation
    assert "source_file" not in citation
    assert "props.apiKey" not in key_form
    assert "submitElement({ apiKey: value })" in key_form
    assert 'type={show ? "text" : "password"}' in key_form


def test_graph_prompt_forbids_html_and_requires_source_ids():
    graph_source = (ROOT / "src" / "core" / "graph.py").read_text(encoding="utf-8")

    assert "Do not emit HTML" in graph_source
    assert "[[cite:SOURCE_ID]]" in graph_source
    assert "gemini-3.1-flash-lite-preview" not in graph_source
