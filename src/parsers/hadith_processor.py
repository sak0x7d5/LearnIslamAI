"""Hadith corpus parser."""

from __future__ import annotations

import json
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import SentenceTransformersTokenTextSplitter

from core.config import logger
from parsers.base import BaseProcessor


class HadithProcessor(BaseProcessor):
    """Convert one Hadith edition into token-safe documents."""

    def to_chunks(self, text_splitter: SentenceTransformersTokenTextSplitter) -> List[Document]:
        logger.info("Processing Hadith dataset: %s", self.file_path.name)
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read %s: %s", self.file_path, exc)
            return []

        if not isinstance(data, dict):
            logger.error("Hadith dataset must be a JSON object: %s", self.file_path)
            return []
        book_metadata = data.get("metadata")
        hadiths = data.get("hadiths")
        if not isinstance(book_metadata, dict) or not isinstance(hadiths, list):
            logger.error("Hadith dataset is missing metadata or hadiths: %s", self.file_path)
            return []

        sections = book_metadata.get("sections", {})
        if not isinstance(sections, dict):
            sections = {}
        name = str(book_metadata.get("name", self.file_path.stem))
        documents: list[Document] = []
        blank_records = 0

        for array_index, hadith_data in enumerate(hadiths):
            if not isinstance(hadith_data, dict):
                continue
            text = hadith_data.get("text", "")
            if not isinstance(text, str) or not text.strip():
                blank_records += 1
                continue

            reference = hadith_data.get("reference", {})
            if not isinstance(reference, dict):
                reference = {}
            book_number = reference.get("book")
            metadata = {
                "name": name,
                "section": sections.get(str(book_number), ""),
                "hadithnumber": hadith_data.get("hadithnumber"),
                "arabicnumber": hadith_data.get("arabicnumber"),
                "reference": reference,
                "type": "hadith",
                "source_id": f"hadith/english/{self.file_path.name}",
                "array_index": array_index,
            }
            grades = hadith_data.get("grades")
            if isinstance(grades, list) and grades:
                metadata["grades"] = grades
            documents.append(Document(page_content=text.strip(), metadata=metadata))

        if blank_records:
            logger.warning(
                "Skipped %s declared blank-text records in %s",
                blank_records,
                self.file_path.name,
            )

        if not documents:
            logger.warning("No valid Hadith found to embed in %s", self.file_path.name)
            return []

        logger.info("Chunking %s Hadith records for %s", len(documents), self.file_path.name)
        return text_splitter.split_documents(documents)
