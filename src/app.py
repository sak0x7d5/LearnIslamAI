from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

import chainlit as cl
import chainlit.config as chainlit_config
from chainlit.utils import utc_now
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import SecretStr

from core.answer_rendering import render_semantic_answer
from core.api_keys import ApiKeyService, EnvFileService
from core.config import (
    CORPUS_UPDATE_MANIFEST_URL,
    CHAINLIT_FILES_DIR,
    DB_PATH,
    DB_URL,
    ROOT_DIR,
    logger,
)
from core.data_layer import IslamAIDataLayer
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
from core.llm import make_key_validator, resolve_model, resolve_provider
from core.message_utils import (
    extract_final_graph_answer,
    restore_conversation_messages,
)
from core.startup_status import StartupStatus, describe_failure
from core.tool_steps import ToolStepPresenter


_env_file = EnvFileService(ROOT_DIR / ".env")
_provider = resolve_provider(_env_file.read_secret)
_model_name = resolve_model(_provider)

# Hoisted so a copy edit cannot silently drop the provider label.
VALIDATING_NEW_KEY = "Validating your {label} API key\u2026"
VALIDATING_SAVED_KEY = "Validating the saved {label} API key\u2026"


def ensure_auth_secret() -> str:
    existing = _env_file.read_secret("CHAINLIT_AUTH_SECRET")
    if existing is None:
        existing = SecretStr(secrets.token_hex(32))
        _env_file.upsert_secret("CHAINLIT_AUTH_SECRET", existing)
    value = existing.get_secret_value()
    os.environ["CHAINLIT_AUTH_SECRET"] = value
    return value


ensure_auth_secret()
initialize_database(str(DB_PATH))
CHAINLIT_FILES_DIR.mkdir(parents=True, exist_ok=True)
chainlit_config.FILES_DIRECTORY = CHAINLIT_FILES_DIR

_api_keys = ApiKeyService(_env_file, make_key_validator(_provider, _model_name), _provider.key_env)
_knowledge_base = KnowledgeBaseService()
_knowledge_base_task_lock = asyncio.Lock()
_corpus_update_flow_lock = asyncio.Lock()
_runtime_lock = asyncio.Lock()
_knowledge_base_task: asyncio.Task[Any] | None = None
_knowledge_base_ready = False
_runtime_graph: Any | None = None
_validated_key: SecretStr | None = None
_startup_status = StartupStatus()

INTERNAL_MESSAGE_METADATA = {"islamai_internal": True}


def _internal(message: Any) -> Any:
    """Mark setup/status UI so it is never restored into model history."""
    message.metadata = dict(INTERNAL_MESSAGE_METADATA)
    return message


def _consume_task_result(task: asyncio.Task[Any]) -> None:
    """Retrieve detached task failures without exposing exception text."""
    if task.cancelled():
        return
    try:
        failure = task.exception()
    except Exception as exc:
        logger.warning("Detached startup observer failed (%s).", type(exc).__name__)
        return
    if failure is not None:
        logger.warning("Background knowledge-base setup failed (%s).", describe_failure(failure))


@cl.data_layer
def get_data_layer():
    return IslamAIDataLayer(conninfo=DB_URL)


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
            await self.complete()
            return

        task = self.tasks.get(event.phase)
        if task is None:
            return
        task.status = cl.TaskStatus.RUNNING
        if event.total_items:
            base = task.title.split(" (", 1)[0]
            task.title = f"{base} ({event.current_item}/{event.total_items})"
            if event.detail:
                task.title += f" — {event.detail}"
        if event.phase == "index_quran":
            self.tasks["validating_corpus"].status = cl.TaskStatus.DONE
            self.tasks["loading_embeddings"].status = cl.TaskStatus.DONE
        elif event.phase == "index_hadith":
            self.tasks["index_quran"].status = cl.TaskStatus.DONE
        await self.task_list.update()

    async def complete(self) -> None:
        for task in self.tasks.values():
            task.status = cl.TaskStatus.DONE
        self.task_list.status = "Ready"
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
            if event.detail:
                task.title += f" — {event.detail}"
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


async def _request_provider_key() -> SecretStr | None:
    for _ in range(3):
        prompt = _internal(
            cl.AskElementMessage(
                content=f"A {_provider.label} API key is required to answer this question.",
                element=cl.CustomElement(
                    name="ApiKeyForm",
                    display="inline",
                    props={
                        "provider": _provider.label,
                        "placeholder": _provider.key_placeholder,
                        "consoleUrl": _provider.console_url,
                        "envVar": _provider.key_env,
                    },
                ),
                timeout=300,
                raise_on_timeout=False,
            )
        )
        response = await prompt.send()
        if not response or not response.get("submitted"):
            return None
        raw_key = response.pop("apiKey", None)
        if not isinstance(raw_key, str) or not raw_key.strip():
            prompt.content = "No API key was submitted. Enter a non-empty key to continue."
            await prompt.update()
            continue
        key = SecretStr(raw_key.strip())
        del raw_key
        prompt.content = VALIDATING_NEW_KEY.format(label=_provider.label)
        await prompt.update()
        result = await _api_keys.validate_and_save(key)
        if result.is_valid:
            prompt.content = f"{_provider.label} API key validated and saved locally."
            await prompt.update()
            return key
        prompt.content = result.message
        await prompt.update()
        if result.status == "unavailable":
            return None
    return None


async def _ensure_provider_key() -> SecretStr | None:
    global _validated_key
    if _validated_key is not None:
        return _validated_key
    existing = _api_keys.read()
    if existing is not None:
        status_message = _internal(
            cl.Message(content=VALIDATING_SAVED_KEY.format(label=_provider.label))
        )
        await status_message.send()
        result = await _api_keys.validate(existing)
        if result.is_valid:
            status_message.content = f"Saved {_provider.label} API key validated."
            await status_message.update()
            _validated_key = existing
            return existing
        status_message.content = result.message
        await status_message.update()
        if result.status == "unavailable":
            return None
    _validated_key = await _request_provider_key()
    return _validated_key


async def _maybe_check_corpus_update() -> bool:
    global _knowledge_base_ready, _knowledge_base_task

    if not CORPUS_UPDATE_MANIFEST_URL:
        return False

    if _corpus_update_flow_lock.locked():
        await _internal(
            cl.Message(content="Another chat is finishing the corpus-update choice…")
        ).send()

    async with _corpus_update_flow_lock:
        if not _knowledge_base.update_prompt_due():
            return False

        # Claim the daily prompt before displaying it so two tabs cannot both
        # open an update interaction. check_for_updates records the final choice.
        _knowledge_base.manifest_tracker.record_update_prompt()
        update_prompt = _internal(
            cl.AskActionMessage(
                content=(
                    "Check for and install a newer English Quran/Hadith corpus? "
                    "Choosing Later makes no network request."
                ),
                actions=[
                    cl.Action(
                        name="check_corpus_update",
                        label="Check now",
                        payload={"approved": True},
                    ),
                    cl.Action(
                        name="defer_corpus_update", label="Later", payload={"approved": False}
                    ),
                ],
                timeout=90,
                raise_on_timeout=False,
            )
        )
        response = await update_prompt.send()
        approved = bool(response and response.get("payload", {}).get("approved"))
        try:
            client = HttpCorpusUpdateClient(CORPUS_UPDATE_MANIFEST_URL)
        except ValueError:
            logger.error("ISLAMAI_CORPUS_MANIFEST_URL must be an HTTPS URL.")
            return False

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
            logger.exception(
                "Corpus update failed; retaining active corpus (%s).", type(exc).__name__
            )
            if progress is not None:
                await progress.fail()
            await _internal(
                cl.Message(
                    content=(
                        "The corpus update failed. IslamAI will use the last valid local corpus."
                    )
                )
            ).send()
            return False
        if result.status == UpdateStatus.UP_TO_DATE:
            await _internal(cl.Message(content="The local corpus is already up to date.")).send()
        elif result.status == UpdateStatus.INSTALLED:
            _knowledge_base_ready = False
            _knowledge_base_task = None
            await _internal(
                cl.Message(content=f"Corpus {result.active_version} was validated and activated.")
            ).send()
            return True
        return False


async def _run_knowledge_base_bootstrap() -> Any:
    global _knowledge_base_ready
    try:
        report = await _knowledge_base.ensure_ready(_startup_status.record)
    except Exception as exc:
        _startup_status.fail(
            f"{describe_failure(exc)}\n\n"
            "The previous valid local corpus and indexes were retained. Restart the chat to retry."
        )
        raise
    _knowledge_base_ready = True
    return report


async def _get_or_start_knowledge_base_task() -> asyncio.Task[Any] | None:
    global _knowledge_base_task
    if _knowledge_base_ready:
        return None
    async with _knowledge_base_task_lock:
        if _knowledge_base_ready:
            return None
        if _knowledge_base_task is None or _knowledge_base_task.done():
            _startup_status.begin()
            _knowledge_base_task = asyncio.create_task(_run_knowledge_base_bootstrap())
            _knowledge_base_task.add_done_callback(_consume_task_result)
        return _knowledge_base_task


async def _follow_knowledge_base_task(task: asyncio.Task[Any]) -> bool:
    progress = BootstrapProgress()
    await progress.send()
    status_message = _internal(cl.Message(content=_startup_status.snapshot().render()))
    await status_message.send()
    last_version = -1

    while not task.done():
        snapshot = _startup_status.snapshot()
        if snapshot.version != last_version:
            if snapshot.event is not None:
                await progress(snapshot.event)
            status_message.content = snapshot.render()
            await status_message.update()
            last_version = snapshot.version
        await asyncio.wait({task}, timeout=0.25)

    snapshot = _startup_status.snapshot()
    if snapshot.version != last_version:
        if snapshot.event is not None:
            await progress(snapshot.event)
        status_message.content = snapshot.render()
        await status_message.update()

    try:
        await asyncio.shield(task)
    except Exception as exc:
        logger.error("Knowledge-base initialization failed (%s).", describe_failure(exc))
        await progress.fail()
        return False

    await progress.complete()
    status_message.content = _startup_status.snapshot().render()
    await status_message.update()
    cl.user_session.set("knowledge_base_ready", True)
    return True


async def _ensure_knowledge_base(*, interactive_retry: bool) -> bool:
    if _knowledge_base_ready:
        cl.user_session.set("knowledge_base_ready", True)
        return True

    owns_bootstrap_ui = not cl.user_session.get("bootstrap_ui_active")
    if owns_bootstrap_ui:
        # Claim this session's progress UI before the first await. A reconnect
        # observer and an immediate user message can otherwise create duplicates.
        cl.user_session.set("bootstrap_ui_active", True)

    try:
        attempts = 2 if interactive_retry and owns_bootstrap_ui else 1
        for attempt in range(attempts):
            task = await _get_or_start_knowledge_base_task()
            if task is None:
                cl.user_session.set("knowledge_base_ready", True)
                return True

            if owns_bootstrap_ui:
                if await _follow_knowledge_base_task(task):
                    return True
            else:
                try:
                    await asyncio.shield(task)
                except Exception as exc:
                    logger.error(
                        "Knowledge-base initialization failed (%s).", describe_failure(exc)
                    )
                else:
                    cl.user_session.set("knowledge_base_ready", True)
                    return True

            if attempt + 1 >= attempts:
                break

            retry_prompt = _internal(
                cl.AskActionMessage(
                    content="The local knowledge base could not be prepared.",
                    actions=[
                        cl.Action(name="retry_bootstrap", label="Retry", payload={"retry": True})
                    ],
                    timeout=120,
                    raise_on_timeout=False,
                )
            )
            response = await retry_prompt.send()
            if not response or not response.get("payload", {}).get("retry"):
                break
    finally:
        if owns_bootstrap_ui:
            cl.user_session.set("bootstrap_ui_active", False)

    cl.user_session.set("knowledge_base_ready", False)
    return False


async def _ensure_runtime() -> bool:
    global _runtime_graph
    if _runtime_graph is not None:
        cl.user_session.set("runtime_ready", True)
        return True

    if not await _ensure_knowledge_base(interactive_retry=True):
        cl.user_session.set("runtime_ready", False)
        return False

    await _maybe_check_corpus_update()
    if not _knowledge_base_ready:
        if not await _ensure_knowledge_base(interactive_retry=True):
            cl.user_session.set("runtime_ready", False)
            return False

    key = await _ensure_provider_key()
    if key is None:
        cl.user_session.set("runtime_ready", False)
        return False

    async with _runtime_lock:
        if _runtime_graph is None:
            _runtime_graph = build_graph(
                api_key=key,
                coordinator=_knowledge_base.coordinator,
                provider=_provider,
                model_name=_model_name,
            )
    cl.user_session.set("runtime_ready", True)
    return True


async def _resume_knowledge_base_observer() -> None:
    # Chainlit emits the restored thread after on_chat_resume returns. Give that
    # payload a chance to land before replaying the latest startup snapshot.
    await asyncio.sleep(0.1)
    await _ensure_knowledge_base(interactive_retry=False)


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
    cl.user_session.set("runtime_ready", _runtime_graph is not None)
    await _ensure_knowledge_base(interactive_retry=False)


@cl.on_chat_resume
async def on_chat_resume(thread: dict[str, Any]):
    cl.user_session.set("messages", restore_conversation_messages(thread.get("steps", [])))
    cl.user_session.set("runtime_ready", _runtime_graph is not None)
    cl.user_session.set("knowledge_base_ready", _knowledge_base_ready)
    if not _knowledge_base_ready:
        observer = asyncio.create_task(_resume_knowledge_base_observer())
        observer.add_done_callback(_consume_task_result)


@cl.on_message
async def on_message(message: cl.Message):
    global _runtime_graph, _validated_key

    if not cl.user_session.get("knowledge_base_ready") and not await _ensure_knowledge_base(
        interactive_retry=True
    ):
        await _internal(
            cl.Message(
                content="IslamAI local search is not ready. Restart the chat to retry safely."
            )
        ).send()
        return

    if (
        _runtime_graph is None or not cl.user_session.get("runtime_ready")
    ) and not await _ensure_runtime():
        await _internal(
            cl.Message(
                content=(
                    f"IslamAI cannot answer yet. Retry when the {_provider.label} key or "
                    "local corpus issue is resolved."
                )
            )
        ).send()
        return

    messages = list(cl.user_session.get("messages") or [])
    messages.append(HumanMessage(content=message.content))
    current_run = cl.context.current_run
    presenter = ToolStepPresenter(
        lambda **kwargs: cl.Step(**kwargs),
        utc_now,
        parent_id=getattr(current_run, "id", None),
    )
    run = await collect_graph_run(_runtime_graph, {"messages": messages}, presenter)
    root_output = run.output

    if run.failed:
        # Force a fresh provider-key validation before another graph run. This
        # recovers from a revoked key without retaining a broken graph client.
        _runtime_graph = None
        _validated_key = None
        cl.user_session.set("runtime_ready", False)
        await cl.Message(
            content="I’m sorry, the answer service failed safely. Please try again later."
        ).send()
        return

    if root_output is None:
        logger.error("LangGraph completed without an authoritative root result.")
        await presenter.fail_all("The search ended before a final answer was available.")
        await cl.Message(
            content="I’m sorry, I couldn’t generate an answer. Please try again."
        ).send()
        return

    final_answer = extract_final_graph_answer(root_output)
    if not final_answer:
        await cl.Message(
            content="I’m sorry, I couldn’t generate an answer. Please try again."
        ).send()
        return

    rendered = render_semantic_answer(final_answer, run.tool_artifacts)
    fallback_markdown = rendered["fallback_markdown"]
    if not fallback_markdown:
        await cl.Message(
            content="I’m sorry, I couldn’t generate an answer. Please try again."
        ).send()
        return

    elements = []
    if rendered["has_cards"]:
        elements.append(
            cl.CustomElement(
                name="AnswerView",
                display="inline",
                props={"blocks": rendered["blocks"]},
            )
        )
    await cl.Message(content=fallback_markdown, elements=elements).send()
    messages.append(AIMessage(content=fallback_markdown))
    cl.user_session.set("messages", messages)
