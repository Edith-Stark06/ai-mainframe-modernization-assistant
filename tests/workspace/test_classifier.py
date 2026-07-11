"""
File Classifier Tests.

Purpose:
    Verify that :class:`app.workspace.classifier.FileClassifier` correctly
    classifies mainframe files by extension and content sniff.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.workspace.classifier import FileClassifier
from app.workspace.models import FileType


@pytest.fixture()
def clf() -> FileClassifier:
    """Return a :class:`FileClassifier` instance."""
    return FileClassifier()


# ---------------------------------------------------------------------------
# Extension-based classification
# ---------------------------------------------------------------------------


class TestClassifierByExtension:
    """Tests for extension-based classification (primary lookup)."""

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("payroll.cbl", FileType.COBOL),
            ("PAYROLL.CBL", FileType.COBOL),
            ("program.cob", FileType.COBOL),
            ("copybook.cpy", FileType.COPYBOOK),
            ("batch.jcl", FileType.JCL),
            ("proc.proc", FileType.PROC),
            ("procedure.prc", FileType.PROC),
            ("screen.bms", FileType.BMS),
            ("config.xml", FileType.XML),
            ("data.json", FileType.JSON),
            ("readme.txt", FileType.TEXT),
        ],
    )
    def test_extension_classification(
        self, clf: FileClassifier, filename: str, expected: FileType
    ) -> None:
        """Files with well-known extensions must be classified correctly."""
        result = clf.classify(filename=filename)
        assert result == expected

    def test_unknown_extension_returns_unknown(self, clf: FileClassifier) -> None:
        """Files with unrecognised extensions must return FileType.UNKNOWN."""
        result = clf.classify(filename="file.docx")
        assert result == FileType.UNKNOWN

    def test_no_extension_returns_unknown(self, clf: FileClassifier) -> None:
        """Files without an extension must return FileType.UNKNOWN."""
        result = clf.classify(filename="NOEXTENSION")
        assert result == FileType.UNKNOWN

    def test_extension_check_is_case_insensitive(self, clf: FileClassifier) -> None:
        """Extension matching must be case-insensitive."""
        assert clf.classify("FILE.JCL") == FileType.JCL
        assert clf.classify("FILE.jcl") == FileType.JCL


# ---------------------------------------------------------------------------
# Content-sniff classification
# ---------------------------------------------------------------------------


class TestClassifierContentSniff:
    """Tests for content-based sniff fallback on .txt and unknown extensions."""

    def test_txt_file_with_jcl_content_classified_as_jcl(
        self, clf: FileClassifier
    ) -> None:
        """A .txt file whose content starts with '//' must be classified as JCL."""
        content = b"//MYJOB JOB (ACCT),'TEST',CLASS=A\n//STEP1 EXEC PGM=IEFBR14\n"
        result = clf.classify(filename="unknown.txt", content=content)
        assert result == FileType.JCL

    def test_txt_file_with_bms_content_classified_as_bms(
        self, clf: FileClassifier
    ) -> None:
        """A .txt file with BMS macro names must be classified as BMS."""
        content = b"MAPSET   DFHMSD TYPE=MAP,LANG=COBOL,MODE=INOUT\n"
        result = clf.classify(filename="screen.txt", content=content)
        assert result == FileType.BMS

    def test_txt_file_with_plain_content_classified_as_text(
        self, clf: FileClassifier
    ) -> None:
        """A .txt file with no distinctive signature must stay as TEXT."""
        content = b"This is a readme file with no special content.\n"
        result = clf.classify(filename="readme.txt", content=content)
        assert result == FileType.TEXT

    def test_sniff_not_applied_to_cbl(self, clf: FileClassifier) -> None:
        """Content sniff must NOT override a definitive extension match (.cbl)."""
        # Even if content looks like JCL, .cbl must win
        content = b"//MYJOB JOB ...\n"
        result = clf.classify(filename="prog.cbl", content=content)
        assert result == FileType.COBOL

    def test_classify_without_content_for_txt(self, clf: FileClassifier) -> None:
        """Classifying a .txt file without content must return TEXT."""
        result = clf.classify(filename="notes.txt", content=None)
        assert result == FileType.TEXT


# ---------------------------------------------------------------------------
# Return type validation
# ---------------------------------------------------------------------------


class TestClassifierReturnType:
    """Tests for return type consistency."""

    def test_return_is_file_type_enum(self, clf: FileClassifier) -> None:
        """classify() must always return a FileType enum member."""
        result = clf.classify("file.cbl")
        assert isinstance(result, FileType)

    def test_all_file_types_are_reachable(self, clf: FileClassifier) -> None:
        """Every FileType value must be reachable through classify()."""
        reachable = {
            clf.classify("a.cbl"),
            clf.classify("b.cpy"),
            clf.classify("c.jcl"),
            clf.classify("d.proc"),
            clf.classify("e.bms"),
            clf.classify("f.xml"),
            clf.classify("g.json"),
            clf.classify("h.txt"),
            clf.classify("i.unknown"),
        }
        assert FileType.COBOL in reachable
        assert FileType.COPYBOOK in reachable
        assert FileType.JCL in reachable
        assert FileType.TEXT in reachable
        assert FileType.UNKNOWN in reachable
