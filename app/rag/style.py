"""
Answer Style Metrics.

Purpose:
    Make "is this answer clean?" measurable. A chat answer can be factually
    right and still hard to read: raw chunk ids sprinkled through it, wide
    tables, hedging words where the context was silent, a wall of text. These
    counts let a prompt or post-processing change be shown to help, the same
    way :mod:`app.rag.evaluation` does for retrieval.

Responsibilities:
    - :func:`measure_style` -- count the noise in one answer.
    - :class:`StyleReport` -- the counts.

Non-responsibilities:
    - Judging correctness (see :mod:`app.rag.grounding` and
      ``scripts/evaluate_chat.py``).

Dependencies:
    - re (standard library)

Examples:
    >>> measure_style("See [java_method-ab12cd34ef56] now.").chunk_id_citations
    1

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["HEDGE_WORDS", "StyleReport", "measure_style"]

#: A raw chunk id used as a citation: ``[business_rule-d4f31d31b4b4f058]``.
CHUNK_ID_CITATION = re.compile(r"\[[a-z][a-z_]*-[0-9a-f]{8,}\]")

#: Words that signal a guess where the context was silent.
HEDGE_WORDS = (
    "presumably",
    "probably",
    "likely",
    "typically",
    "perhaps",
    "possibly",
    "might",
    "seems to",
    "appears to",
)

_LABEL_LINE = re.compile(
    r"^\s*(summary|explanation|note|answer|details)\s*:", re.I | re.M
)


@dataclass(frozen=True)
class StyleReport:
    """
    Noise counts for one answer.

    Attributes:
        words: Length in words.
        chunk_id_citations: Raw chunk ids appearing as citations.
        table_rows: Lines of a markdown table.
        hedges: Hedging words/phrases.
        section_labels: ``Summary:`` / ``Explanation:`` style label lines.
        stray_bold_markers: Unbalanced ``**`` (an odd count on a line).
    """

    words: int
    chunk_id_citations: int
    table_rows: int
    hedges: int
    section_labels: int
    stray_bold_markers: int

    @property
    def noise(self) -> int:
        """Total of the countable defects (length excluded)."""
        return (
            self.chunk_id_citations
            + self.table_rows
            + self.hedges
            + self.section_labels
            + self.stray_bold_markers
        )


def measure_style(answer: str) -> StyleReport:
    """
    Count the readability defects in *answer*.

    Args:
        answer: The text shown to the user.

    Returns:
        A :class:`StyleReport`.
    """
    lowered = answer.lower()
    return StyleReport(
        words=len(answer.split()),
        chunk_id_citations=len(CHUNK_ID_CITATION.findall(answer)),
        table_rows=sum(
            1 for line in answer.splitlines() if line.strip().startswith("|")
        ),
        hedges=sum(lowered.count(word) for word in HEDGE_WORDS),
        section_labels=len(_LABEL_LINE.findall(answer)),
        stray_bold_markers=sum(
            1 for line in answer.splitlines() if line.count("**") % 2 == 1
        ),
    )
