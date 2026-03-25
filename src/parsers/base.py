from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from langchain_core.documents import Document

class BaseProcessor(ABC):
    """
    Abstract base class for data processors.
    """
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    @abstractmethod
    def to_chunks(self, text_splitter) -> List[Document]:
        """
        Reads the data file, extracts the text and metadata, 
        and splits it into chunks using the provided text_splitter.
        Returns a list of Document objects ready for embedding.
        """
        pass
