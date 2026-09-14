import ast
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
    assert config["features"]["spontaneous_file_upload"]["accept"] == ["text/plain"]
    assert config["UI"]["cot"] == "tool_call"
    assert config["UI"]["custom_css"] == ("/public/stylesheet.css?v=0.1.0-answer-view-3")
    assert config["project"]["persist_user_env"] is False


def test_custom_elements_do_not_render_raw_html_or_receive_source_paths():
    key_form = (ROOT / "public" / "elements" / "ApiKeyForm.jsx").read_text(encoding="utf-8")
    answer_view = (ROOT / "public" / "elements" / "AnswerView.jsx").read_text(encoding="utf-8")

    assert not (ROOT / "public" / "elements" / "CitationCard.jsx").exists()
    assert "props.apiKey" not in key_form
    assert "props?.apiKey" not in key_form
    assert "submitElement({ apiKey: value })" in key_form
    assert 'type={show ? "text" : "password"}' in key_form
    # Provider-neutral: the label comes from a prop, never a baked-in vendor name.
    assert "props?.provider" in key_form
    assert "props?.placeholder" in key_form
    assert "Google Gemini" not in key_form
    assert 'rel="noreferrer noopener"' in key_form
    assert "dangerouslySetInnerHTML" not in answer_view
    assert "<Markdown allowHtml={false} renderMarkdown={true}>" in answer_view


def test_app_uses_permissive_semantic_rendering_and_local_element_persistence():
    app_source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")

    assert "IslamAIDataLayer(conninfo=DB_URL)" in app_source
    assert "render_semantic_answer(final_answer, run.tool_artifacts)" in app_source
    assert 'name="AnswerView"' in app_source
    assert 'props={"blocks": rendered["blocks"]}' in app_source
    assert "validate_citation_markers" not in app_source
    assert "repair" not in _called_functions(app_source, "on_message")


def test_graph_prompt_allows_only_semantic_source_tags():
    graph_source = (ROOT / "src" / "core" / "graph.py").read_text(encoding="utf-8")

    assert '<quran ref="SOURCE_ID">...</quran>' in graph_source
    assert '<hadith ref="SOURCE_ID">...</hadith>' in graph_source
    assert "do not emit any other HTML" in graph_source
    assert "ordinary Markdown" in graph_source
    assert "Quote only the relevant portion" in graph_source
    assert "[[cite:" not in graph_source
    assert "make_validation_node" not in graph_source
    assert "gemini-3.1-flash-lite-preview" not in graph_source


def test_graph_holds_no_provider_specific_code():
    """Provider choice lives in core.llm so graph.py stays vendor-neutral."""

    graph_source = (ROOT / "src" / "core" / "graph.py").read_text(encoding="utf-8")

    assert "ChatGoogleGenerativeAI" not in graph_source
    assert "langchain_openai" not in graph_source
    assert "gemini" not in graph_source.lower()


def test_provider_sdks_are_not_imported_at_module_scope():
    """Lazy SDK imports keep core.llm importable without every provider installed."""

    tree = ast.parse((ROOT / "src" / "core" / "llm.py").read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)

    assert "langchain_google_genai" not in top_level
    assert "langchain_openai" not in top_level


def test_key_validation_probe_is_bounded_and_forces_a_tool_call():
    """A model that cannot call tools must be rejected before it can answer."""

    llm_source = (ROOT / "src" / "core" / "llm.py").read_text(encoding="utf-8")

    assert "asyncio.wait_for" in llm_source
    assert 'tool_choice="any"' in llm_source
    assert "PROBE_TIMEOUT_SECONDS" in llm_source


def _function_node(source: str, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )


def _calls_in_node(function: ast.AST) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def _called_functions(source: str, function_name: str) -> set[str]:
    return _calls_in_node(_function_node(source, function_name))


def test_api_key_form_waits_for_a_real_user_message():
    app_source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")

    chat_start = _function_node(app_source, "on_chat_start")
    chat_start_calls = _called_functions(app_source, "on_chat_start")
    knowledge_base_calls = _called_functions(app_source, "_ensure_knowledge_base")
    runtime_calls = _called_functions(app_source, "_ensure_runtime")
    message_calls = _called_functions(app_source, "on_message")
    resume_calls = _called_functions(app_source, "on_chat_resume")
    resume_observer_calls = _called_functions(app_source, "_resume_knowledge_base_observer")
    runtime = _function_node(app_source, "_ensure_runtime")

    startup_call = next(
        node
        for node in ast.walk(chat_start)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ensure_knowledge_base"
    )
    interactive_retry = next(
        keyword.value for keyword in startup_call.keywords if keyword.arg == "interactive_retry"
    )

    assert "_ensure_knowledge_base" in chat_start_calls
    assert "_ensure_runtime" not in chat_start_calls
    assert "_ensure_provider_key" not in chat_start_calls
    assert isinstance(interactive_retry, ast.Constant) and interactive_retry.value is False
    assert "_maybe_check_corpus_update" not in knowledge_base_calls
    assert "_ensure_provider_key" not in knowledge_base_calls
    assert "_maybe_check_corpus_update" in runtime_calls
    assert "_ensure_provider_key" in runtime_calls
    assert "_ensure_runtime" in message_calls
    assert "create_task" in resume_calls
    assert "_resume_knowledge_base_observer" in resume_calls
    assert "_ensure_knowledge_base" in resume_observer_calls
    assert "_ensure_runtime" not in resume_calls
    assert "VALIDATING_NEW_KEY" in app_source
    assert "VALIDATING_SAVED_KEY" in app_source
    assert "_provider.label" in app_source
    assert "Gemini" not in app_source

    runtime_lock = next(
        node
        for node in ast.walk(runtime)
        if isinstance(node, ast.AsyncWith)
        and any(
            isinstance(item.context_expr, ast.Name) and item.context_expr.id == "_runtime_lock"
            for item in node.items
        )
    )
    assert _calls_in_node(runtime_lock) == {"build_graph"}
