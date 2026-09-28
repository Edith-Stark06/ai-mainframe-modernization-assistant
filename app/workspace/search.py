"""
Workspace Search (task #stage47).

Purpose:
    Provide a real, working text search across every file already
    discovered in a workspace inventory -- the backend the frontend's
    own topbar comment named as the reason no search box was rendered
    ("no backend search endpoint exists, and a non-functional search
    input would be a fake affordance", ``app/frontend/app.py``). This
    module is that backend.

    Search is deliberately plain substring/line matching over each
    file's raw text, not semantic/embedding-based retrieval: this
    project's own RAG stack (:mod:`app.rag`, :mod:`app.knowledge`) has
    no real embedding provider wired in today (only a deterministic
    fake, used solely by the chat endpoint) and nothing in ``app/``
    ever populates a vector index from workspace content. Shipping a
    search feature that silently returns nothing (or noise) because the
    embeddings behind it are fake would be exactly the kind of
    unhonest, fabricated capability this project's own conventions
    reject. Line-based text search has no such gap: it finds exactly
    what it claims to find.

Responsibilities:
    - :class:`WorkspaceSearcher` -- its :meth:`~WorkspaceSearcher.search`
      method searches every file in a
      :class:`~app.workspace.models.WorkspaceInventory` for a query
      string, returning line-level matches with surrounding context.
    - Skip files too large to be worth a full-text scan, and files that
      fail to decode as UTF-8 text (binary content), gracefully -- never
      raising for one bad file among many.

Non-responsibilities:
    - Semantic/embedding-based search (see Purpose above).
    - Persisting or caching search results across requests.
    - Searching inside a ZIP archive's own original bytes -- the
      inventory already expands archives to real files on disk, so
      those are searched like any other file, but this module has no
      archive-specific logic of its own.

Dependencies:
    - app.workspace.models -- WorkspaceInventory
    - loguru -- structured logging for skipped files
    - Python standard library (dataclasses, pathlib).

Examples:
    Searching a workspace inventory::

        from app.workspace.search import WorkspaceSearcher

        result = WorkspaceSearcher().search(inventory, "PERFORM")
        assert result.query == "PERFORM"

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.workspace.models import WorkspaceInventory

__all__ = ["SearchMatch", "SearchResult", "WorkspaceSearcher"]

#: Files larger than this are skipped rather than fully scanned -- a
#: generous ceiling for mainframe source (even a large COBOL program or
#: JCL job stream is a few hundred KB at most); avoids a pathological
#: full-text scan of an accidentally-included large binary/data file.
_MAX_SEARCHABLE_BYTES: int = 5 * 1024 * 1024

#: Characters of context kept on each side of a match within its line's
#: own snippet, when the line itself is long.
_SNIPPET_CONTEXT_CHARS: int = 60


@dataclass(frozen=True)
class SearchMatch:
    """
    One matching line within one file.

    Attributes:
        filename: The matching file's basename (e.g. ``"payroll.cbl"``).
        path: The matching file's absolute path.
        line: 1-based line number the match occurred on.
        snippet: The matching line's text, truncated around the match
            when the line is long (never the whole file, never more
            than one line).
    """

    filename: str
    path: str
    line: int
    snippet: str


@dataclass(frozen=True)
class SearchResult:
    """
    The outcome of one :meth:`WorkspaceSearcher.search` call.

    Attributes:
        query: The search query, exactly as given.
        matches: Every :class:`SearchMatch` found, in file-then-line
            order, capped at *max_total_matches*.
        files_searched: How many files were actually scanned (excludes
            those skipped as too large or undecodable).
        files_matched: How many distinct files contributed at least one
            match.
        truncated: ``True`` if the total match cap was hit -- more
            matches may exist beyond what ``matches`` shows.
    """

    query: str
    matches: tuple[SearchMatch, ...] = field(default_factory=tuple)
    files_searched: int = 0
    files_matched: int = 0
    truncated: bool = False


class WorkspaceSearcher:
    """Line-based text search over every file in a workspace inventory."""

    def search(
        self,
        inventory: WorkspaceInventory,
        query: str,
        *,
        case_sensitive: bool = False,
        max_matches_per_file: int = 20,
        max_total_matches: int = 200,
    ) -> SearchResult:
        """
        Search every file in *inventory* for *query*.

        Args:
            inventory: The workspace's file inventory (see
                :class:`~app.workspace.inventory.InventoryBuilder`).
            query: The text to search for. A blank/whitespace-only query
                matches nothing (returned as an empty result, not every
                line of every file).
            case_sensitive: When ``False`` (the default), matching
                ignores case -- COBOL/JCL source is conventionally
                uppercase but is not reliably typed that way by every
                author or tool.
            max_matches_per_file: Stop collecting matches from one file
                once it reaches this many, so one file with a very
                common term cannot crowd out every other file's results.
            max_total_matches: Stop collecting matches once the overall
                total reaches this many; :attr:`SearchResult.truncated`
                is set when this cap is what stopped the search.

        Returns:
            A :class:`SearchResult`. Never raises for a single
            unreadable/undecodable file -- that file is skipped and
            logged, not fatal to the whole search.
        """
        query_stripped = query.strip()
        if not query_stripped:
            return SearchResult(query=query)

        needle = query_stripped if case_sensitive else query_stripped.lower()
        matches: list[SearchMatch] = []
        files_searched = 0
        files_matched = 0
        truncated = False

        for scanned in inventory.files:
            if len(matches) >= max_total_matches:
                truncated = True
                break

            path = Path(scanned.path)
            if scanned.size_bytes > _MAX_SEARCHABLE_BYTES:
                logger.debug(
                    "WorkspaceSearcher: skipping '{}' ({} bytes, over the "
                    "searchable size limit).",
                    path,
                    scanned.size_bytes,
                )
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug(
                    "WorkspaceSearcher: skipping unreadable file '{}': {}.",
                    path,
                    exc,
                )
                continue

            files_searched += 1
            file_matches = 0
            matched_this_file = False
            for line_no, line in enumerate(text.splitlines(), start=1):
                if file_matches >= max_matches_per_file:
                    break
                if len(matches) >= max_total_matches:
                    truncated = True
                    break
                haystack = line if case_sensitive else line.lower()
                idx = haystack.find(needle)
                if idx == -1:
                    continue
                matched_this_file = True
                file_matches += 1
                matches.append(
                    SearchMatch(
                        filename=scanned.filename,
                        path=scanned.path,
                        line=line_no,
                        snippet=_make_snippet(line, idx, len(query_stripped)),
                    )
                )

            if matched_this_file:
                files_matched += 1

        logger.debug(
            "WorkspaceSearcher: query {!r} -> {} match(es) in {} of {} file(s) "
            "(truncated={}).",
            query_stripped,
            len(matches),
            files_matched,
            files_searched,
            truncated,
        )
        return SearchResult(
            query=query,
            matches=tuple(matches),
            files_searched=files_searched,
            files_matched=files_matched,
            truncated=truncated,
        )


def _make_snippet(line: str, match_index: int, match_length: int) -> str:
    """
    Return *line*, truncated with a leading/trailing ``"..."`` when it
    is long, keeping the match itself (at *match_index*, *match_length*
    characters) visible with :data:`_SNIPPET_CONTEXT_CHARS` of context
    on each side.
    """
    if len(line) <= 2 * _SNIPPET_CONTEXT_CHARS + match_length:
        return line
    start = max(0, match_index - _SNIPPET_CONTEXT_CHARS)
    end = min(len(line), match_index + match_length + _SNIPPET_CONTEXT_CHARS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(line) else ""
    return f"{prefix}{line[start:end]}{suffix}"
