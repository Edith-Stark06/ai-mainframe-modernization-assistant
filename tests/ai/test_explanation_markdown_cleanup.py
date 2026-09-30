"""Dangling ``**`` markers around section labels must not leak into answers."""

from __future__ import annotations

import pytest

from app.ai.explanation.service import CodeExplanationService, _strip_orphan_markers
from app.ai.providers.fake import FakeLLMProvider


def _parse(reply: str):
    return CodeExplanationService(FakeLLMProvider(response_text=reply)).explain_code(
        "IDENTIFICATION DIVISION."
    )


def test_bold_markers_around_labels_are_removed() -> None:
    reply = (
        "Summary: **  \nIt is HIGH VALUE at 50000.  \n\n**\n\n"
        "Explanation: **  \nWS-TOTAL >= 50000.  \n\n**"
    )
    result = _parse(reply)
    assert result.summary == "It is HIGH VALUE at 50000."
    assert result.explanation == "WS-TOTAL >= 50000."
    assert "**" not in str(result)


def test_real_emphasis_is_kept() -> None:
    reply = (
        "Summary: **High** value orders.\n\nExplanation: It flags **50000** or more."
    )
    result = _parse(reply)
    assert result.summary == "**High** value orders."
    assert result.explanation == "It flags **50000** or more."


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("** text", "text"),
        ("text **", "text"),
        ("**  \ntext\n\n**", "text"),
        ("**bold** kept", "**bold** kept"),
        ("plain", "plain"),
        ("  padded  ", "padded"),
    ],
)
def test_strip_orphan_markers(raw: str, clean: str) -> None:
    assert _strip_orphan_markers(raw) == clean


def test_a_section_that_is_only_markers_is_still_an_error() -> None:
    with pytest.raises(ValueError):
        _parse("Summary: ok\n\nExplanation: **")
