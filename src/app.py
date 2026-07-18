from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.utils import utc_now
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from core.api_keys import ApiKeyService, EnvFileService, ValidationResult
from core.citations import (
    CitationRecord,
    collect_citations,
    ordered_citations,
    render_citation_markers,
)
from core.config import (
    CORPUS_UPDATE_MANIFEST_URL,
    DB_PATH,
    DB_URL,
    DEFAULT_LLM_MODEL,
    ROOT_DIR,
    logger,
)
from core.database import initialize_database
from core.graph import build_graph
from core.graph_events import collect_graph_run
from core.knowledge_base import (
    HttpCorpusUpdateClient,
    KnowledgeBaseService,
    ProgressEvent,
    UpdateStatus,
    build_staged_indexes,
)
from core.message_utils import extract_final_graph_answer
from core.tool_steps import ToolStepPresenter


_env_file = EnvFileService(ROOT_DIR / ".env")


def ensure_auth_secret() -> str:
    existing = _env_file.read_secret("CHAINLIT_AUTH_SECRET")
    if existing is None:
        existing = SecretStr(secrets.token_hex(32))
        _env_file.upsert_secret("CHAINLIT_AUTH_SECRET", existing)
    value = existing.get_secret_value()
    os.environ["CHAINLIT_AUTH_SECRET"] = value
    return value


async def validate_google_api_key(key: SecretStr) -> ValidationResult:
    """Make a minimal request and return only non-secret diagnostic text."""
    try:
        model = ChatGoogleGenerativeAI(
            model=DEFAULT_LLM_MODEL,
            temperature=0,
            google_api_key=key,
            max_retries=0,
        )
        await model.ainvoke([HumanMessage(content="Reply with the single word OK.")])
        return ValidationResult("valid", "Google API key validated.")
    except Exception as exc:  # provider exception types vary between SDK releases
        status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        safe_type = type(exc).__name__
        normalized = str(status_code).lower() if status_code is not None else ""
        if normalized in {"400", "401", "403", "unauthenticated", "permission_denied"}:
            return ValidationResult("invalid", "Google rejected this API key.")
        logger.warning("Google API-key validation was unavailable (%s).", safe_type)
        return ValidationResult(
            "unavailable",
            "The key could not be validated because Google was unavailable. Check the network and try again.",
        )


ensure_auth_secret()
initialize_database(str(DB_PATH))

_api_keys = ApiKeyService(_env_file, validate_google_api_key)
_knowledge_base = KnowledgeBaseService()
_runtime_lock = asyncio.Lock()
_runtime_graph: Any | None = None
_validated_key: SecretStr | None = None


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=DB_URL)


@cl.header_auth_callback
def header_auth_callback(headers: dict[str, str]):
    # Safe only because the supported launcher binds Chainlit to 127.0.0.1.
    return cl.User(identifier="local-user", metadata={"role": "local"})


class BootstrapProgress:
    def __init__(self) -> None:
        self.tasks = {
            "validating_corpus": cl.Task(
                title="Validate bundled corpus", status=cl.TaskStatus.READY
            ),
            "loading_embeddings": cl.Task(
                title="Load local embedding model", status=cl.TaskStatus.READY
            ),
            "index_quran": cl.Task(title="Build Quran index", status=cl.TaskStatus.READY),
            "index_hadith": cl.Task(title="Build Hadith index", status=cl.TaskStatus.READY),
        }
        self.task_list = cl.TaskList(status="Preparing local knowledge base")

    async def send(self) -> None:
        for task in self.tasks.values():
            await self.task_list.add_task(task)
        await self.task_list.send()

    async def __call__(self, event: ProgressEvent) -> None:
        if event.phase == "ready":
            for task in self.tasks.values():
                task.status = cl.TaskStatus.DONE
            self.task_list.status = "Ready"
            await self.task_list.update()
            return

        task = self.tasks.get(event.phase)
        if task is None:
            return
        task.status = cl.TaskStatus.RUNNING
        if event.total_items:
            base = task.title.split(" (", 1)[0]
            task.title = f"{base} ({event.current_item}/{event.total_items})"
        if event.phase == "index_quran":
            self.tasks["validating_corpus"].status = cl.TaskStatus.DONE
            self.tasks["loading_embeddings"].status = cl.TaskStatus.DONE
        elif event.phase == "index_hadith":
            self.tasks["index_quran"].status = cl.TaskStatus.DONE
        await self.task_list.update()

    async def fail(self) -> None:
        for task in self.tasks.values():
            if task.status == cl.TaskStatus.RUNNING:
                task.status = cl.TaskStatus.FAILED
        self.task_list.status = "Failed"
        await self.task_list.update()


class UpdateProgress:
    def __init__(self) -> None:
        self.tasks = {
            "checking_update": cl.Task(title="Check update metadata", status=cl.TaskStatus.READY),
            "downloading_corpus": cl.Task(
                title="Download validated corpus files", status=cl.TaskStatus.READY
            ),
            "building_indexes": cl.Task(title="Build updated indexes", status=cl.TaskStatus.READY),
            "update_ready": cl.Task(title="Activate update", status=cl.TaskStatus.READY),
        }
        self.task_list = cl.TaskList(status="Checking corpus update")

    async def send(self) -> None:
        for task in self.tasks.values():
            await self.task_list.add_task(task)
        await self.task_list.send()

    async def __call__(self, event: ProgressEvent) -> None:
        task = self.tasks.get(event.phase)
        if task is None:
            return
        task.status = cl.TaskStatus.RUNNING
        if event.total_items:
            base = task.title.split(" (", 1)[0]
            task.title = f"{base} ({event.current_item}/{event.total_items})"
        order = list(self.tasks)
        current_index = order.index(event.phase)
        for earlier in order[:current_index]:
            self.tasks[earlier].status = cl.TaskStatus.DONE
        if event.phase == "update_ready":
            for item in self.tasks.values():
                item.status = cl.TaskStatus.DONE
            self.task_list.status = "Update ready"
        await self.task_list.update()

    async def fail(self) -> None:
        for task in self.tasks.values():
            if task.status == cl.TaskStatus.RUNNING:
                task.status = cl.TaskStatus.FAILED
        self.task_list.status = "Update failed; current corpus retained"
        await self.task_list.update()


async def _request_google_key() -> SecretStr | None:
    for _ in range(3):
        response = await cl.AskElementMessage(
            content="A Google Gemini API key is required for answer generation.",
            element=cl.CustomElement(
                name="ApiKeyForm",
                display="inline",
                props={"purpose": "Gemini answer generation"},
            ),
            timeout=300,
            raise_on_timeout=False,
        ).send()
        if not response or not response.get("submitted"):
            return None
        raw_key = response.pop("apiKey", None)
        if not isinstance(raw_key, str) or not raw_key.strip():
            await cl.Message(content="No API key was submitted.").send()
            continue
        key = SecretStr(raw_key.strip())
        del raw_key
        result = await _api_keys.validate_and_save(key)
        if result.is_valid:
            await cl.Message(content="Google API key validated and saved locally.").send()
            return key
        await cl.Message(content=result.message).send()
        if result.status == "unavailable":
            return None
    return None


async def _ensure_google_key() -> SecretStr | None:
    global _validated_key
    if _validated_key is not None:
        return _validated_key
    existing = _api_keys.read()
    if existing is not None:
        result = await _api_keys.validate(existing)
        if result.is_valid:
            _validated_key = existing
            return existing
        await cl.Message(content=result.message).send()
        if result.status == "unavailable":
            return None
    _validated_key = await _request_google_key()
    return _validated_key


async def _maybe_check_corpus_update() -> None:
    if not CORPUS_UPDATE_MANIFEST_URL or not _knowledge_base.update_prompt_due():
        return
    response = await cl.AskActionMessage(
        content=(
            "Check for and install a newer English Quran/Hadith corpus? "
            "Choosing Later makes no network request."
        ),
        actions=[
            cl.Action(name="check_corpus_update", label="Check now", payload={"approved": True}),
            cl.Action(name="defer_corpus_update", label="Later", payload={"approved": False}),
        ],
        timeout=90,
        raise_on_timeout=False,
    ).send()
    approved = bool(response and response.get("payload", {}).get("approved"))
    try:
        client = HttpCorpusUpdateClient(CORPUS_UPDATE_MANIFEST_URL)
    except ValueError:
        logger.error("ISLAMAI_CORPUS_MANIFEST_URL must be an HTTPS URL.")
        return

    progress = UpdateProgress() if approved else None
    if progress is not None:
        await progress.send()
    try:
        result = await _knowledge_base.check_for_updates(
            approved=approved,
            client=client,
            index_builder=build_staged_indexes,
            progress=progress,
        )
    except Exception as exc:
        logger.exception("Corpus update failed; retaining active corpus (%s).", type(exc).__name__)
        if progress is not None:
            await progress.fail()
        await cl.Message(
            content="The corpus update failed. IslamAI will use the last valid local corpus."
        ).send()
        return
    if result.status == UpdateStatus.UP_TO_DATE:
        await cl.Message(content="The local corpus is already up to date.").send()
    elif result.status == UpdateStatus.INSTALLED:
        await cl.Message(
            content=f"Corpus {result.active_version} was validated and activated."
        ).send()


async def _initialize_runtime() -> bool:
    global _runtime_graph
    if _runtime_graph is not None:
        cl.user_session.set("runtime_ready", True)
        return True

    async with _runtime_lock:
        if _runtime_graph is not None:
            cl.user_session.set("runtime_ready", True)
            return True

        key = await _ensure_google_key()
        if key is None:
            cl.user_session.set("runtime_ready", False)
            return False

        await _maybe_check_corpus_update()

        progress = BootstrapProgress()
        await progress.send()
        try:
            await _knowledge_base.ensure_ready(progress)
        except Exception as exc:
            logger.exception("Knowledge-base initialization failed: %s", type(exc).__name__)
            await progress.fail()
            response = await cl.AskActionMessage(
                content="The local knowledge base could not be prepared.",
                actions=[cl.Action(name="retry_bootstrap", label="Retry", payload={"retry": True})],
                timeout=120,
                raise_on_timeout=False,
            ).send()
            if not response or not response.get("payload", {}).get("retry"):
                cl.user_session.set("runtime_ready", False)
                return False
            try:
                await _knowledge_base.ensure_ready(progress)
            except Exception as retry_exc:
                logger.exception("Knowledge-base retry failed: %s", type(retry_exc).__name__)
                await progress.fail()
                cl.user_session.set("runtime_ready", False)
                return False

        _runtime_graph = build_graph(
            api_key=key,
            coordinator=_knowledge_base.coordinator,
            model_name=DEFAULT_LLM_MODEL,
        )
        cl.user_session.set("runtime_ready", True)
        return True


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="The Companion with doubled testimony",
            message=(
                "Which Companion had his testimony counted as equal to two witnesses, "
                "and how did that distinction matter during compilation of the Quran?"
            ),
            icon="/public/quran_icon.svg",
        )
    ]


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("messages", [])
    await _initialize_runtime()


@cl.on_chat_resume
async def on_chat_resume(thread: dict[str, Any]):
    messages: list[HumanMessage | AIMessage] = []
    for step in thread.get("steps", []):
        output = step.get("output")
        if not isinstance(output, str) or not output:
            continue
        if step.get("type") == "user_message":
            messages.append(HumanMessage(content=output))
        elif step.get("type") == "assistant_message":
            messages.append(AIMessage(content=output))
    cl.user_session.set("messages", messages)
    await _initialize_runtime()


def _citation_elements(records: list[CitationRecord]) -> list[cl.CustomElement]:
    return [
        cl.CustomElement(name="CitationCard", display="inline", props=dict(record))
        for record in records
    ]


@cl.on_message
async def on_message(message: cl.Message):
    global _runtime_graph, _validated_key

    if not cl.user_session.get("runtime_ready") and not await _initialize_runtime():
        await cl.Message(
            content="IslamAI is not ready. Restart the chat when the API key or local corpus issue is resolved."
        ).send()
        return

    messages = list(cl.user_session.get("messages") or [])
    messages.append(HumanMessage(content=message.content))
    presenter = ToolStepPresenter(lambda **kwargs: cl.Step(**kwargs), utc_now)
    run = await collect_graph_run(_runtime_graph, {"messages": messages}, presenter)
    root_output = run.output

    if run.failed:
        # Force a fresh provider-key validation before another graph run. This
        # recovers from a revoked key without retaining a broken graph client.
        _runtime_graph = None
        _validated_key = None
        await cl.Message(
            content="I’m sorry, the answer service failed safely. Please try again later."
        ).send()
        return

    if root_output is None:
        logger.error("LangGraph completed without an authoritative root result.")
        await presenter.fail_all("The search ended before a verified answer was available.")
        await cl.Message(
            content="I’m sorry, I couldn’t generate a verified answer. Please try again."
        ).send()
        return

    final_answer = extract_final_graph_answer(root_output)
    graph_messages = root_output.get("messages", [])
    records = collect_citations(graph_messages if isinstance(graph_messages, list) else [])
    cited_records = ordered_citations(final_answer, records)
    if not final_answer:
        await cl.Message(
            content="I’m sorry, I couldn’t generate a verified answer. Please try again."
        ).send()
        return

    rendered = render_citation_markers(final_answer, records)
    await cl.Message(content=rendered, elements=_citation_elements(cited_records)).send()
    messages.append(AIMessage(content=rendered))
    cl.user_session.set("messages", messages)
