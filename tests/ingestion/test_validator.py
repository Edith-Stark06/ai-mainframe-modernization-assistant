"""
File Validator Tests.

Purpose:
    Verify that :class:`app.ingestion.validator.FileValidator` enforces
    all upload validation rules correctly.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

import pytest

from app.core.exceptions import ValidationException
from app.ingestion.validator import SUPPORTED_EXTENSIONS, FileValidator


@pytest.fixture()
def validator() -> FileValidator:
    """Return a :class:`FileValidator` instance."""
    return FileValidator()


# ---------------------------------------------------------------------------
# Extension validation
# ---------------------------------------------------------------------------


class TestValidateExtension:
    """Tests for :meth:`FileValidator.validate_extension`."""

    @pytest.mark.parametrize(
        "filename",
        [
            "payroll.cbl",
            "copybook.cpy",
            "batch.jcl",
            "archive.zip",
            "notes.txt",
            "program.cob",
        ],
    )
    def test_supported_extensions_pass(
        self, validator: FileValidator, filename: str
    ) -> None:
        """Supported extensions must not raise."""
        validator.validate_extension(filename)  # should not raise

    @pytest.mark.parametrize(
        "filename",
        [
            "report.docx",
            "data.xlsx",
            "readme.md",
            "script.py",
            "image.png",
            "no_extension",
        ],
    )
    def test_unsupported_extensions_raise(
        self, validator: FileValidator, filename: str
    ) -> None:
        """Unsupported extensions must raise ValidationException."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_extension(filename)
        assert exc_info.value.error_code == "VALIDATION_ERROR"

    def test_error_details_contain_extension(self, validator: FileValidator) -> None:
        """ValidationException details must include the offending extension."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_extension("file.docx")
        assert exc_info.value.details is not None
        assert ".docx" in str(exc_info.value.details)

    def test_error_details_contain_allowed_list(self, validator: FileValidator) -> None:
        """ValidationException details must include the allowed-extensions list."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_extension("file.bad")
        details = exc_info.value.details
        assert details is not None
        assert "allowed" in details

    def test_extension_check_is_case_insensitive(
        self, validator: FileValidator
    ) -> None:
        """Extension validation must be case-insensitive."""
        # Upper-case extension should be treated the same as lower-case.
        # Currently SUPPORTED_EXTENSIONS are lowercase; upper-case MUST
        # raise (raw extension comparison) unless we normalise.
        # The validator normalises to lowercase, so .CBL should pass.
        validator.validate_extension("payroll.CBL")


# ---------------------------------------------------------------------------
# Empty-file validation
# ---------------------------------------------------------------------------


class TestValidateNotEmpty:
    """Tests for :meth:`FileValidator.validate_not_empty`."""

    def test_non_empty_file_passes(self, validator: FileValidator) -> None:
        """Non-empty content must not raise."""
        validator.validate_not_empty(b"data", "payroll.cbl")

    def test_empty_file_raises(self, validator: FileValidator) -> None:
        """Zero-byte content must raise ValidationException."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_not_empty(b"", "empty.cbl")
        assert exc_info.value.error_code == "VALIDATION_ERROR"

    def test_empty_file_error_details(self, validator: FileValidator) -> None:
        """ValidationException details must report size_bytes as 0."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_not_empty(b"", "empty.cbl")
        assert exc_info.value.details["size_bytes"] == 0


# ---------------------------------------------------------------------------
# Size validation
# ---------------------------------------------------------------------------


class TestValidateSize:
    """Tests for :meth:`FileValidator.validate_size`."""

    def test_file_under_limit_passes(self, validator: FileValidator) -> None:
        """Content within the size limit must not raise."""
        content = b"x" * 100  # 100 bytes — well under default 20 MB
        validator.validate_size(content, "small.cbl")

    def test_file_exactly_at_limit_passes(
        self, validator: FileValidator, monkeypatch
    ) -> None:
        """Content exactly at the size limit must pass."""
        from app.core import config as cfg

        monkeypatch.setattr(cfg.settings, "max_upload_mb", 1)
        content = b"x" * (1 * 1024 * 1024)  # exactly 1 MB
        validator.validate_size(content, "exact.cbl")

    def test_file_over_limit_raises(
        self, validator: FileValidator, monkeypatch
    ) -> None:
        """Content exceeding the size limit must raise ValidationException."""
        from app.core import config as cfg

        monkeypatch.setattr(cfg.settings, "max_upload_mb", 1)
        content = b"x" * (1 * 1024 * 1024 + 1)  # 1 byte over 1 MB
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_size(content, "big.cbl")
        assert exc_info.value.error_code == "VALIDATION_ERROR"

    def test_oversized_details_contain_max_mb(
        self, validator: FileValidator, monkeypatch
    ) -> None:
        """ValidationException details must include the configured max_mb."""
        from app.core import config as cfg

        monkeypatch.setattr(cfg.settings, "max_upload_mb", 1)
        content = b"x" * (2 * 1024 * 1024)
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_size(content, "huge.cbl")
        assert exc_info.value.details["max_mb"] == 1


# ---------------------------------------------------------------------------
# Duplicate filename validation
# ---------------------------------------------------------------------------


class TestValidateNoDuplicates:
    """Tests for :meth:`FileValidator.validate_no_duplicates`."""

    def test_unique_filenames_pass(self, validator: FileValidator) -> None:
        """Unique filenames must not raise."""
        validator.validate_no_duplicates(["a.cbl", "b.jcl", "c.cpy"])

    def test_duplicate_filenames_raise(self, validator: FileValidator) -> None:
        """Duplicate filenames must raise ValidationException."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_no_duplicates(["a.cbl", "b.jcl", "a.cbl"])
        assert exc_info.value.error_code == "VALIDATION_ERROR"

    def test_duplicate_detection_is_case_insensitive(
        self, validator: FileValidator
    ) -> None:
        """Duplicate detection must be case-insensitive."""
        with pytest.raises(ValidationException):
            validator.validate_no_duplicates(["Payroll.cbl", "payroll.cbl"])

    def test_single_file_passes(self, validator: FileValidator) -> None:
        """A list with a single file must not raise."""
        validator.validate_no_duplicates(["only.cbl"])

    def test_empty_list_passes(self, validator: FileValidator) -> None:
        """An empty list must not raise."""
        validator.validate_no_duplicates([])

    def test_duplicate_details_list_present(self, validator: FileValidator) -> None:
        """ValidationException details must include the duplicates list."""
        with pytest.raises(ValidationException) as exc_info:
            validator.validate_no_duplicates(["x.cbl", "x.cbl"])
        assert "duplicates" in exc_info.value.details


# ---------------------------------------------------------------------------
# Supported extensions set
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    """Tests for the :data:`SUPPORTED_EXTENSIONS` constant."""

    def test_cbl_in_supported(self) -> None:
        assert ".cbl" in SUPPORTED_EXTENSIONS

    def test_cob_in_supported(self) -> None:
        assert ".cob" in SUPPORTED_EXTENSIONS

    def test_cpy_in_supported(self) -> None:
        assert ".cpy" in SUPPORTED_EXTENSIONS

    def test_jcl_in_supported(self) -> None:
        assert ".jcl" in SUPPORTED_EXTENSIONS

    def test_txt_in_supported(self) -> None:
        assert ".txt" in SUPPORTED_EXTENSIONS

    def test_zip_in_supported(self) -> None:
        assert ".zip" in SUPPORTED_EXTENSIONS
