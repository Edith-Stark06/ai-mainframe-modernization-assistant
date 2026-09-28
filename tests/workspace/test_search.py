"""
Tests for :mod:`app.workspace.search` (task #stage47).

Purpose:
    Verify :class:`~app.workspace.search.WorkspaceSearcher` finds every
    matching line across a workspace's files, is case-insensitive by
    default, respects the per-file and total match caps, and never
    raises for an unreadable/oversized file.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.workspace.models import FileType, ScannedFile, WorkspaceInventory
from app.workspace.search import WorkspaceSearcher


def _scanned(path: Path) -> ScannedFile:
    data = path.read_bytes()
    return ScannedFile(
        path=str(path),
        filename=path.name,
        extension=path.suffix.lower(),
        sha256="0" * 64,
        size_bytes=len(data),
        file_type=FileType.COBOL,
        scanned_at=datetime.now(UTC),
    )


def _inventory(tmp_path: Path, files: dict[str, str]) -> WorkspaceInventory:
    scanned = []
    for name, content in files.items():
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        scanned.append(_scanned(p))
    return WorkspaceInventory(
        workspace_id="ws",
        files=scanned,
        total_files=len(scanned),
        scanned_at=datetime.now(UTC),
    )


class TestBasicSearch:
    def test_finds_a_match_with_line_and_snippet(self, tmp_path: Path) -> None:
        inv = _inventory(
            tmp_path, {"a.cbl": "IDENTIFICATION DIVISION.\nMOVE X TO Y.\n"}
        )
        result = WorkspaceSearcher().search(inv, "MOVE X")
        assert len(result.matches) == 1
        assert result.matches[0].line == 2
        assert result.matches[0].filename == "a.cbl"
        assert "MOVE X TO Y" in result.matches[0].snippet

    def test_no_match_returns_empty_result(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "IDENTIFICATION DIVISION.\n"})
        result = WorkspaceSearcher().search(inv, "NOWHERE-TO-BE-FOUND")
        assert result.matches == ()
        assert result.files_matched == 0
        assert result.files_searched == 1

    def test_blank_query_matches_nothing(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "ANYTHING AT ALL\n"})
        result = WorkspaceSearcher().search(inv, "   ")
        assert result.matches == ()
        assert result.files_searched == 0

    def test_matches_across_multiple_files(self, tmp_path: Path) -> None:
        inv = _inventory(
            tmp_path,
            {
                "a.cbl": "CUSTOMER-BALANCE PIC 9(7)V99.\n",
                "b.cbl": "MOVE CUSTOMER-BALANCE TO WS-X.\n",
                "c.cbl": "NOTHING RELEVANT HERE.\n",
            },
        )
        result = WorkspaceSearcher().search(inv, "CUSTOMER-BALANCE")
        assert result.files_matched == 2
        assert {m.filename for m in result.matches} == {"a.cbl", "b.cbl"}

    def test_multiple_matches_within_one_file(self, tmp_path: Path) -> None:
        inv = _inventory(
            tmp_path,
            {"a.cbl": "MOVE X TO Y.\nDISPLAY X.\nMOVE X TO Z.\n"},
        )
        result = WorkspaceSearcher().search(inv, "MOVE X")
        assert len(result.matches) == 2
        assert [m.line for m in result.matches] == [1, 3]


class TestCaseSensitivity:
    def test_case_insensitive_by_default(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "move x to y.\n"})
        result = WorkspaceSearcher().search(inv, "MOVE X")
        assert len(result.matches) == 1

    def test_case_sensitive_when_requested(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "move x to y.\n"})
        result = WorkspaceSearcher().search(inv, "MOVE X", case_sensitive=True)
        assert result.matches == ()


class TestCaps:
    def test_max_matches_per_file(self, tmp_path: Path) -> None:
        content = "\n".join(f"MOVE {i} TO Y." for i in range(50)) + "\n"
        inv = _inventory(tmp_path, {"a.cbl": content})
        result = WorkspaceSearcher().search(inv, "MOVE", max_matches_per_file=5)
        assert len(result.matches) == 5

    def test_max_total_matches_sets_truncated(self, tmp_path: Path) -> None:
        content = "\n".join(f"MOVE {i} TO Y." for i in range(50)) + "\n"
        inv = _inventory(tmp_path, {"a.cbl": content})
        result = WorkspaceSearcher().search(
            inv, "MOVE", max_matches_per_file=100, max_total_matches=10
        )
        assert len(result.matches) == 10
        assert result.truncated is True

    def test_not_truncated_when_under_the_cap(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "MOVE X TO Y.\n"})
        result = WorkspaceSearcher().search(inv, "MOVE")
        assert result.truncated is False


class TestSnippetTruncation:
    def test_short_line_is_not_truncated(self, tmp_path: Path) -> None:
        inv = _inventory(tmp_path, {"a.cbl": "MOVE X TO Y.\n"})
        result = WorkspaceSearcher().search(inv, "MOVE")
        assert result.matches[0].snippet == "MOVE X TO Y."

    def test_long_line_is_truncated_around_the_match(self, tmp_path: Path) -> None:
        line = "X" * 200 + "NEEDLE" + "Y" * 200
        inv = _inventory(tmp_path, {"a.cbl": line + "\n"})
        result = WorkspaceSearcher().search(inv, "NEEDLE")
        snippet = result.matches[0].snippet
        assert "NEEDLE" in snippet
        assert len(snippet) < len(line)
        assert snippet.startswith("...")
        assert snippet.endswith("...")


class TestGracefulDegradation:
    def test_oversized_file_is_skipped_not_scanned(self, tmp_path: Path) -> None:
        p = tmp_path / "huge.cbl"
        p.write_text("NEEDLE\n", encoding="utf-8")
        scanned = _scanned(p)
        # Lie about the size to simulate an oversized file without
        # actually writing megabytes of content to disk.
        oversized = scanned.model_copy(update={"size_bytes": 10 * 1024 * 1024})
        inv = WorkspaceInventory(
            workspace_id="ws",
            files=[oversized],
            total_files=1,
            scanned_at=datetime.now(UTC),
        )
        result = WorkspaceSearcher().search(inv, "NEEDLE")
        assert result.matches == ()
        assert result.files_searched == 0

    def test_undecodable_file_is_skipped_not_raised(self, tmp_path: Path) -> None:
        p = tmp_path / "binary.cbl"
        p.write_bytes(b"\xff\xfe\x00\x01NEEDLE")
        scanned = _scanned(p)
        inv = WorkspaceInventory(
            workspace_id="ws",
            files=[scanned],
            total_files=1,
            scanned_at=datetime.now(UTC),
        )
        result = WorkspaceSearcher().search(inv, "NEEDLE")
        assert result.matches == ()

    def test_missing_file_is_skipped_not_raised(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.cbl"
        scanned = ScannedFile(
            path=str(missing),
            filename="gone.cbl",
            extension=".cbl",
            sha256="0" * 64,
            size_bytes=10,
            file_type=FileType.COBOL,
            scanned_at=datetime.now(UTC),
        )
        inv = WorkspaceInventory(
            workspace_id="ws",
            files=[scanned],
            total_files=1,
            scanned_at=datetime.now(UTC),
        )
        result = WorkspaceSearcher().search(inv, "ANYTHING")
        assert result.matches == ()
        assert result.files_searched == 0

    def test_empty_inventory_produces_empty_result(self, tmp_path: Path) -> None:
        inv = WorkspaceInventory(
            workspace_id="ws", files=[], total_files=0, scanned_at=datetime.now(UTC)
        )
        result = WorkspaceSearcher().search(inv, "ANYTHING")
        assert result.matches == ()
        assert result.files_searched == 0
