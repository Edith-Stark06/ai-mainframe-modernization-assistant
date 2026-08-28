import hashlib
from typing import Any

from app.rag.models import KnowledgeChunk, KnowledgeDocument


class DocumentChunker:
    """
    Deterministically splits a KnowledgeDocument into KnowledgeChunk instances.
    """

    def __init__(self, chunk_size: int = 1000, overlap: int = 200) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be >= 0 and < chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        """
        Chunks a KnowledgeDocument based on its document_type.
        """
        code_types = {
            "cobol",
            "python",
            "java",
            "c",
            "cpp",
            "csharp",
            "go",
            "javascript",
            "typescript",
            "jcl",
            "bms",
            "sql",
        }
        is_code = document.document_type.lower() in code_types

        if is_code:
            return self._chunk_code(document)
        else:
            return self._chunk_text(document)

    def _generate_chunk_id(
        self, document_id: str, chunk_index: int, content: str
    ) -> str:
        """
        Generates a deterministic ID for a chunk.
        """
        h = hashlib.sha256(f"{document_id}:{chunk_index}:{content}".encode("utf-8"))
        return f"{document_id}-{h.hexdigest()[:16]}"

    def _create_chunk(
        self,
        document: KnowledgeDocument,
        chunk_index: int,
        start_char: int,
        end_char: int,
        content: str,
    ) -> KnowledgeChunk | None:
        if not content.strip():
            return None

        chunk_id = self._generate_chunk_id(document.id, chunk_index, content)
        metadata: dict[str, Any] = {
            "source_id": document.id,
            "source_name": document.source_name,
            "source_path": document.source_path,
            "document_type": document.document_type,
            "chunk_size": self.chunk_size,
            "overlap": self.overlap,
            "chunk_index": chunk_index,
            "start_char": start_char,
            "end_char": end_char,
        }

        return KnowledgeChunk(
            id=chunk_id,
            document_id=document.id,
            content=content,
            chunk_index=chunk_index,
            metadata=metadata,
        )

    def _chunk_text(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        text = document.content
        text_len = len(text)

        if text_len == 0:
            return ()

        cursor = 0
        chunk_index = 0

        while cursor < text_len:
            end = min(cursor + self.chunk_size, text_len)
            content = text[cursor:end]

            chunk = self._create_chunk(document, chunk_index, cursor, end, content)
            if chunk:
                chunks.append(chunk)
                chunk_index += 1

            if end == text_len:
                break

            cursor = end - self.overlap

        return tuple(chunks)

    def _chunk_code(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        chunks: list[KnowledgeChunk] = []
        text = document.content
        text_len = len(text)

        if text_len == 0:
            return ()

        cursor = 0
        chunk_index = 0

        while cursor < text_len:
            end = min(cursor + self.chunk_size, text_len)

            if end < text_len:
                last_newline = text.rfind("\n", cursor, end)
                if last_newline != -1:
                    end = last_newline + 1

            content = text[cursor:end]
            chunk = self._create_chunk(document, chunk_index, cursor, end, content)
            if chunk:
                chunks.append(chunk)
                chunk_index += 1

            if end == text_len:
                break

            overlap_cursor = max(cursor + 1, end - self.overlap)
            prev_newline = text.rfind("\n", cursor, overlap_cursor)

            if prev_newline != -1:
                next_cursor = prev_newline + 1
            else:
                next_newline = text.find("\n", overlap_cursor, end)
                if next_newline != -1 and next_newline < end - 1:
                    next_cursor = next_newline + 1
                else:
                    next_cursor = overlap_cursor

            cursor = next_cursor

        return tuple(chunks)
