from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

from core.data_layer import IslamAIDataLayer, sanitize_answer_view_props
from core.database import SCHEMA


def test_answer_view_props_allow_only_fixed_text_fields():
    props = sanitize_answer_view_props(
        {
            "className": "attacker-controlled",
            "blocks": [
                {"kind": "markdown", "text": "Intro", "url": "file:///secret"},
                {
                    "kind": "hadith",
                    "text": "Quoted text",
                    "title": " Sahih Muslim ",
                    "locator": "Hadith 1",
                    "grading": "Sahih",
                    "className": "evil",
                    "html": "<script>alert(1)</script>",
                },
                {"kind": "video", "text": "ignored"},
                {"kind": "quran", "text": 255},
            ],
        }
    )

    assert props == {
        "blocks": [
            {"kind": "markdown", "text": "Intro"},
            {
                "kind": "hadith",
                "text": "Quoted text",
                "title": "Sahih Muslim",
                "locator": "Hadith 1",
                "grading": "Sahih",
            },
        ]
    }


def test_answer_view_is_persisted_and_restored_without_blob_storage(tmp_path):
    database = tmp_path / "threads.db"
    with sqlite3.connect(database) as connection:
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute(
            'INSERT INTO threads ("id", "createdAt", "name") VALUES (?, ?, ?)',
            ("thread-1", "2026-01-01T00:00:00Z", "Test"),
        )
        connection.execute(
            'INSERT INTO steps ("id", "name", "type", "threadId", "streaming", "output", "createdAt") '
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "message-1",
                "IslamAI",
                "assistant_message",
                "thread-1",
                False,
                "Fallback",
                "2026-01-01T00:00:01Z",
            ),
        )

    layer = IslamAIDataLayer(conninfo=f"sqlite+aiosqlite:///{database.as_posix()}")
    element = SimpleNamespace(
        id="element-1",
        thread_id="thread-1",
        type="custom",
        name="AnswerView",
        display="inline",
        for_id="message-1",
        chainlit_key=None,
        props={
            "blocks": [
                {"kind": "markdown", "text": "Intro"},
                {
                    "kind": "quran",
                    "text": "Allah—there is no deity except Him.",
                    "title": "Al-Baqarah",
                    "locator": "Quran 2:255",
                },
            ]
        },
    )

    async def scenario():
        await layer.create_element(element)
        restored = await layer.get_thread("thread-1")
        await layer.close()
        return restored

    restored = asyncio.run(scenario())

    assert restored is not None
    assert restored["elements"] == [
        {
            "id": "element-1",
            "threadId": "thread-1",
            "type": "custom",
            "chainlitKey": None,
            "url": None,
            "objectKey": None,
            "name": "AnswerView",
            "display": "inline",
            "size": None,
            "language": None,
            "autoPlay": None,
            "playerConfig": None,
            "page": None,
            "props": {
                "blocks": [
                    {"kind": "markdown", "text": "Intro"},
                    {
                        "kind": "quran",
                        "text": "Allah—there is no deity except Him.",
                        "title": "Al-Baqarah",
                        "locator": "Quran 2:255",
                    },
                ]
            },
            "forId": "message-1",
            "mime": "application/json",
        }
    ]
