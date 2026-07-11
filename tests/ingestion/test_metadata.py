"""
Metadata Extractor Tests.

Purpose:
    Verify that :class:`app.ingestion.metadata.MetadataExtractor` correctly
    populates all fields of :class:`app.ingestion.models.FileMetadata`.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import hashlib

import pytest

from app.ingestion.metadata import MetadataExtractor
from app.ingestion.models import FileMetadata


@pytest.fixture()
def extractor() -> MetadataExtractor:
    """Return a :class:`MetadataExtractor` instance."""
    return MetadataExtractor()


_WORKSPACE_ID = "test-workspace-001"
_COBOL = b"IDENTIFICATION DIVISION.\nPROGRAM-ID. TEST.\n"


class TestMetadataExtractorExtract:
    """Tests for :meth:`MetadataExtractor.extract`."""

    def test_returns_file_metadata_instance(self, extractor: MetadataExtractor) -> None:
        """extract() must return a FileMetadata instance."""
        meta = extractor.extract("test.cbl", _COBOL, _WORKSPACE_ID)
        assert isinstance(meta, FileMetadata)

    def test_filename_preserved(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.filename must equal the supplied filename."""
        meta = extractor.extract("payroll.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.filename == "payroll.cbl"

    def test_extension_extracted(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.extension must equal the lowercase dot-extension."""
        meta = extractor.extract("payroll.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.extension == ".cbl"

    def test_extension_lowercased(self, extractor: MetadataExtractor) -> None:
        """Extension must be stored in lowercase."""
        meta = extractor.extract("PAYROLL.CBL", _COBOL, _WORKSPACE_ID)
        assert meta.extension == ".cbl"

    def test_size_bytes_correct(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.size_bytes must equal len(content)."""
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.size_bytes == len(_COBOL)

    def test_sha256_is_hex_string_of_64_chars(
        self, extractor: MetadataExtractor
    ) -> None:
        """SHA-256 must be a lowercase 64-character hex string."""
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert len(meta.sha256) == 64
        assert all(c in "0123456789abcdef" for c in meta.sha256)

    def test_sha256_correctness(self, extractor: MetadataExtractor) -> None:
        """SHA-256 digest must match the hashlib reference value."""
        expected = hashlib.sha256(_COBOL).hexdigest()
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.sha256 == expected

    def test_workspace_id_stored(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.workspace_id must match the supplied workspace ID."""
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.workspace_id == _WORKSPACE_ID

    def test_encoding_field_is_string(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.encoding must be a non-empty string."""
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert isinstance(meta.encoding, str)
        assert len(meta.encoding) > 0

    def test_created_at_is_set(self, extractor: MetadataExtractor) -> None:
        """FileMetadata.created_at must be a non-None datetime."""
        meta = extractor.extract("a.cbl", _COBOL, _WORKSPACE_ID)
        assert meta.created_at is not None

    def test_different_content_produces_different_sha256(
        self, extractor: MetadataExtractor
    ) -> None:
        """Two distinct byte strings must produce different SHA-256 values."""
        meta1 = extractor.extract("a.cbl", b"content one", _WORKSPACE_ID)
        meta2 = extractor.extract("b.cbl", b"content two", _WORKSPACE_ID)
        assert meta1.sha256 != meta2.sha256

    def test_no_extension_produces_empty_extension(
        self, extractor: MetadataExtractor
    ) -> None:
        """A filename without a dot must produce an empty extension string."""
        meta = extractor.extract("NOEXT", _COBOL, _WORKSPACE_ID)
        assert meta.extension == ""

    @pytest.mark.parametrize("ext", [".cbl", ".cob", ".cpy", ".jcl", ".txt"])
    def test_known_extensions_extracted_correctly(
        self, extractor: MetadataExtractor, ext: str
    ) -> None:
        """Known extensions must be extracted verbatim."""
        meta = extractor.extract(f"file{ext}", _COBOL, _WORKSPACE_ID)
        assert meta.extension == ext
