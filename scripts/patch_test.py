"""
Patch pre-existing tests in test_data_parser.py and test_procedure_parser.py
to reflect the new recovery behavior introduced in TASK-017.

These conditions now record SyntaxDiagnostic instead of raising ParserError:
  Data parser:
    - missing period after data item (EOF case)
    - missing period after elementary item (EOF case)
    - invalid level number (e.g. 99)
    - missing data-name after level

  Procedure parser:
    - missing period after paragraph label
    - STOP without RUN
    - MOVE missing TO keyword
    - DISPLAY missing period
    - STOP RUN missing period
    - GOBACK missing period
    - MOVE missing period

Fatal errors (still raise ParserError) remain:
  - missing/wrong DIVISION keyword in headers
  - missing period after header
"""


def patch_file(filepath: str, patches: list[tuple[str, str]]) -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    applied = 0
    for i, (old, new) in enumerate(patches):
        if old not in content:
            print(f"  WARNING: patch #{i} OLD NOT FOUND in {filepath}")
            print(f"           old[:70]={old[:70]!r}")
        else:
            content = content.replace(old, new, 1)
            applied += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"DONE - patched {filepath} ({applied}/{len(patches)} patches applied)")


# ============================================================================
# DATA PARSER TESTS
# ============================================================================

data_patches = [
    # Update class docstring
    (
        "class TestDataDivisionParserErrors:\n"
        '    """Malformed inputs raise ParserError."""\n',
        "class TestDataDivisionParserErrors:\n"
        '    """Fatal errors raise ParserError; recoverable errors record diagnostics.\n'
        "\n"
        "    After TASK-017, item-level errors (invalid level, missing data-name,\n"
        "    missing period at item end) are recovered via SyntaxDiagnostic.\n"
        "    Division/section header errors remain fatal.\n"
        '    """\n',
    ),
    # test_missing_period_after_data_item
    (
        "    def test_missing_period_after_data_item(self) -> None:\n"
        '        """01 CUSTOMER-REC <eof> \u2192 missing period after item."""\n'
        "        tokens = (\n"
        '            _data_header() + _ws_header() + [_num("01"), _id("CUSTOMER-REC"), _eof()]\n'
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_missing_period_after_data_item(self) -> None:\n"
        '        """01 CUSTOMER-REC <eof> \u2192 missing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        '            _data_header() + _ws_header() + [_num("01"), _id("CUSTOMER-REC"), _eof()]\n'
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = DataDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_missing_period_after_elementary_item
    (
        "    def test_missing_period_after_elementary_item(self) -> None:\n"
        '        """05 CUSTOMER-ID PIC 9 <eof> \u2192 missing period."""\n'
        "        tokens = (\n"
        "            _data_header()\n"
        "            + _ws_header()\n"
        '            + [_num("05"), _id("CUSTOMER-ID")]\n'
        '            + _pic_clause("9")\n'
        "            + [_eof()]\n"
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_missing_period_after_elementary_item(self) -> None:\n"
        '        """05 CUSTOMER-ID PIC 9 <eof> \u2192 missing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _data_header()\n"
        "            + _ws_header()\n"
        '            + [_num("05"), _id("CUSTOMER-ID")]\n'
        '            + _pic_clause("9")\n'
        "            + [_eof()]\n"
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = DataDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_invalid_level_number
    (
        "    def test_invalid_level_number(self) -> None:\n"
        '        """Level 99 is not a valid COBOL level number."""\n'
        "        tokens = (\n"
        "            _data_header()\n"
        "            + _ws_header()\n"
        '            + [_num("99"), _id("INVALID"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        err = self._parse_expect_error(tokens)\n"
        '        assert "99" in str(err) or "invalid" in str(err).lower()\n',
        "    def test_invalid_level_number(self) -> None:\n"
        '        """Level 99 is not a valid COBOL level number \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _data_header()\n"
        "            + _ws_header()\n"
        '            + [_num("99"), _id("INVALID"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = DataDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n"
        '        diag_messages = " ".join(d.message for d in state.diagnostics)\n'
        '        assert "99" in diag_messages or "invalid" in diag_messages.lower()\n',
    ),
    # test_missing_data_name_after_level
    (
        "    def test_missing_data_name_after_level(self) -> None:\n"
        '        """01 . \u2192 missing data-name after level number."""\n'
        '        tokens = _data_header() + _ws_header() + [_num("01"), _period()] + [_eof()]\n'
        "        self._parse_expect_error(tokens)\n",
        "    def test_missing_data_name_after_level(self) -> None:\n"
        '        """01 . \u2192 missing data-name \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        '        tokens = _data_header() + _ws_header() + [_num("01"), _period()] + [_eof()]\n'
        "        state = _make_state(tokens)\n"
        "        parser = DataDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
]

patch_file("tests/parser/test_data_parser.py", data_patches)


# ============================================================================
# PROCEDURE PARSER TESTS
# ============================================================================

proc_patches = [
    # Update class docstring
    (
        "class TestProcedureDivisionParserErrors:\n"
        '    """Malformed inputs raise ParserError."""\n',
        "class TestProcedureDivisionParserErrors:\n"
        '    """Fatal errors raise ParserError; recoverable errors record diagnostics.\n'
        "\n"
        "    After TASK-017, statement-level and paragraph-level errors are recovered\n"
        "    via SyntaxDiagnostic. Division header errors remain fatal.\n"
        '    """\n',
    ),
    # test_missing_period_after_paragraph_label
    (
        "    def test_missing_period_after_paragraph_label(self) -> None:\n"
        '        tokens = _proc_header() + [_id("MAIN-PARA"), _id("SOMETHING"), _eof()]\n'
        "        self._parse_expect_error(tokens)\n",
        "    def test_missing_period_after_paragraph_label(self) -> None:\n"
        '        """Missing period after paragraph label \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        '        tokens = _proc_header() + [_id("MAIN-PARA"), _id("SOMETHING"), _eof()]\n'
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_stop_without_run
    (
        "    def test_stop_without_run(self) -> None:\n"
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("STOP"), _id("SOMETHING"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_stop_without_run(self) -> None:\n"
        '        """STOP <non-RUN> \u2192 diagnostic recorded, parsing continues.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("STOP"), _id("SOMETHING"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_move_missing_to
    (
        "    def test_move_missing_to(self) -> None:\n"
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("MOVE"), _num("1"), _id("WS-COUNT"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_move_missing_to(self) -> None:\n"
        '        """MOVE without TO \u2192 diagnostic recorded, parsing continues.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("MOVE"), _num("1"), _id("WS-COUNT"), _period()]\n'
        "            + [_eof()]\n"
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_display_missing_period
    (
        "    def test_display_missing_period(self) -> None:\n"
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("DISPLAY"), _str_tok(\'"X"\'), _eof()]\n'
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_display_missing_period(self) -> None:\n"
        '        """DISPLAY without trailing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("DISPLAY"), _str_tok(\'"X"\'), _eof()]\n'
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_stop_run_missing_period
    (
        "    def test_stop_run_missing_period(self) -> None:\n"
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("STOP"), _kw("RUN"), _eof()]\n'
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_stop_run_missing_period(self) -> None:\n"
        '        """STOP RUN without trailing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("STOP"), _kw("RUN"), _eof()]\n'
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_goback_missing_period
    (
        "    def test_goback_missing_period(self) -> None:\n"
        "        tokens = (\n"
        '            _proc_header() + [_id("MAIN-PARA"), _period()] + [_id("GOBACK"), _eof()]\n'
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_goback_missing_period(self) -> None:\n"
        '        """GOBACK without trailing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        '            _proc_header() + [_id("MAIN-PARA"), _period()] + [_id("GOBACK"), _eof()]\n'
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
    # test_move_missing_period
    (
        "    def test_move_missing_period(self) -> None:\n"
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _eof()]\n'
        "        )\n"
        "        self._parse_expect_error(tokens)\n",
        "    def test_move_missing_period(self) -> None:\n"
        '        """MOVE ... TO ... without trailing period \u2192 diagnostic recorded.\n'
        "\n"
        "        After TASK-017 the parser records a SyntaxDiagnostic and continues.\n"
        '        """\n'
        "        tokens = (\n"
        "            _proc_header()\n"
        '            + [_id("MAIN-PARA"), _period()]\n'
        '            + [_kw("MOVE"), _num("1"), _id("TO"), _id("WS-COUNT"), _eof()]\n'
        "        )\n"
        "        state = _make_state(tokens)\n"
        "        parser = ProcedureDivisionParser()\n"
        "        node = parser.parse(state)\n"
        "        assert state.has_errors\n",
    ),
]

patch_file("tests/parser/test_procedure_parser.py", proc_patches)
