from __future__ import annotations

import json
from typing import Any

from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


ANSWER_VIEW_NAME = "AnswerView"
ANSWER_BLOCK_KINDS = {"markdown", "quran", "hadith"}


def sanitize_answer_view_props(props: Any) -> dict[str, list[dict[str, Any]]]:
    """Keep only the fixed, text-only AnswerView payload understood by the UI."""

    if not isinstance(props, dict) or not isinstance(props.get("blocks"), list):
        return {"blocks": []}

    blocks: list[dict[str, Any]] = []
    for candidate in props["blocks"]:
        if not isinstance(candidate, dict):
            continue
        kind = candidate.get("kind")
        text = candidate.get("text")
        if kind not in ANSWER_BLOCK_KINDS or not isinstance(text, str) or not text:
            continue

        block: dict[str, Any] = {"kind": kind, "text": text}
        if kind != "markdown":
            for field in ("title", "locator", "grading"):
                value = candidate.get(field)
                if isinstance(value, str) and value.strip():
                    block[field] = value.strip()
        blocks.append(block)

    return {"blocks": blocks}


class IslamAIDataLayer(SQLAlchemyDataLayer):
    """Persist the text-only AnswerView without requiring external blob storage."""

    def __init__(
        self,
        conninfo: str,
        connect_args: dict[str, Any] | None = None,
        *,
        user_thread_limit: int = 1000,
        show_logger: bool = False,
    ) -> None:
        # Chainlit 2.10.1 otherwise emits a misleading warning that no elements
        # are persisted whenever blob storage is absent. AnswerView is stored
        # directly as text-only JSON, so no blob provider is necessary.
        self._conninfo = conninfo
        self.user_thread_limit = user_thread_limit
        self.show_logger = show_logger
        self.storage_provider = None
        self.engine = create_async_engine(conninfo, connect_args=connect_args or {})
        self.async_session = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def create_element(self, element: Any) -> None:
        if getattr(element, "type", None) != "custom" or element.name != ANSWER_VIEW_NAME:
            await super().create_element(element)
            return
        if not element.for_id:
            return

        props = sanitize_answer_view_props(getattr(element, "props", None))
        if not props["blocks"]:
            return

        parameters = {
            "id": element.id,
            "threadId": element.thread_id,
            "type": "custom",
            "chainlitKey": getattr(element, "chainlit_key", None),
            "name": ANSWER_VIEW_NAME,
            "display": "inline",
            "forId": element.for_id,
            "mime": "application/json",
            "props": json.dumps(props, ensure_ascii=False),
        }
        query = """
            INSERT INTO elements (
                "id", "threadId", "type", "chainlitKey", "name", "display",
                "forId", "mime", "props"
            ) VALUES (
                :id, :threadId, :type, :chainlitKey, :name, :display,
                :forId, :mime, :props
            )
            ON CONFLICT ("id") DO UPDATE SET
                "threadId" = excluded."threadId",
                "type" = excluded."type",
                "chainlitKey" = excluded."chainlitKey",
                "name" = excluded."name",
                "display" = excluded."display",
                "forId" = excluded."forId",
                "mime" = excluded."mime",
                "props" = excluded."props"
        """
        await self.execute_sql(query=query, parameters=parameters)

    async def get_all_user_threads(
        self,
        user_id: str | None = None,
        thread_id: str | None = None,
    ):
        threads = await super().get_all_user_threads(user_id=user_id, thread_id=thread_id)
        if not threads:
            return threads

        for thread in threads:
            for element in thread.get("elements", []):
                if element.get("type") != "custom" or element.get("name") != ANSWER_VIEW_NAME:
                    continue
                raw_props = element.get("props")
                if isinstance(raw_props, str):
                    try:
                        raw_props = json.loads(raw_props)
                    except json.JSONDecodeError:
                        raw_props = {}
                element["props"] = sanitize_answer_view_props(raw_props)
        return threads
