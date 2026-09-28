"""
Tests for :mod:`app.jcl.lexer` (task #stage46).

Purpose:
    Verify statement-line splitting (name/operation/parameters/comment),
    continuation-line joining, comment-line and in-stream-data skipping,
    and parameter parsing (quote- and paren-aware comma/equals splitting).

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

from app.jcl.lexer import JclParameter, parse_parameters, tokenize


class TestBasicStatementSplitting:
    def test_name_operation_and_positional_parameter(self) -> None:
        stmts = tokenize("//STEP1 EXEC PGM=IEFBR14\n")
        assert len(stmts) == 1
        assert stmts[0].name == "STEP1"
        assert stmts[0].operation == "EXEC"
        assert stmts[0].parameters == (JclParameter(key="PGM", value="IEFBR14"),)

    def test_trailing_comment_text_is_captured_separately(self) -> None:
        stmts = tokenize("//STEP1 EXEC PGM=IEFBR14  RUN THE THING\n")
        assert stmts[0].comment_text == "RUN THE THING"
        assert len(stmts[0].parameters) == 1

    def test_null_statement(self) -> None:
        stmts = tokenize("//\n")
        assert len(stmts) == 1
        assert stmts[0].name is None
        assert stmts[0].operation is None
        assert stmts[0].parameters == ()

    def test_non_statement_lines_are_ignored(self) -> None:
        stmts = tokenize("this is not JCL\n\n//STEP1 EXEC PGM=X\n")
        assert len(stmts) == 1
        assert stmts[0].name == "STEP1"

    def test_line_number_is_1_based(self) -> None:
        stmts = tokenize("//A JOB\n//B EXEC PGM=X\n")
        assert stmts[0].line == 1
        assert stmts[1].line == 2


class TestCommentLines:
    def test_comment_line_is_captured_as_is_comment(self) -> None:
        stmts = tokenize("//* THIS IS A REMARK\n")
        assert len(stmts) == 1
        assert stmts[0].is_comment is True
        assert stmts[0].comment_text == " THIS IS A REMARK"

    def test_comment_line_does_not_interrupt_continuation(self) -> None:
        """A genuine ``//*`` line between a statement and its
        continuation is not itself a valid continuation (its name field
        is never blank-with-more-params), so continuation stops there --
        confirmed directly rather than assumed to "just work"."""
        stmts = tokenize("//A JOB CLASS=A,\n//* A COMMENT\n//    REGION=4M\n")
        job = [s for s in stmts if s.operation == "JOB"][0]
        assert [p.key for p in job.parameters] == ["CLASS"]


class TestContinuationLines:
    def test_trailing_comma_continues_on_next_line(self) -> None:
        stmts = tokenize("//A JOB CLASS=A,\n//    MSGCLASS=X\n")
        assert len(stmts) == 1
        job = stmts[0]
        assert [(p.key, p.value) for p in job.parameters] == [
            ("CLASS", "A"),
            ("MSGCLASS", "X"),
        ]

    def test_chained_three_line_continuation(self) -> None:
        stmts = tokenize("//A JOB CLASS=A,\n//    MSGCLASS=X,\n//    REGION=4M\n")
        assert len(stmts) == 1
        assert [p.key for p in stmts[0].parameters] == [
            "CLASS",
            "MSGCLASS",
            "REGION",
        ]

    def test_a_named_line_ends_continuation(self) -> None:
        """A line with its own name field is a genuine new statement,
        not a continuation, even if the previous line ended in a comma
        (a malformed but not-infinitely-consuming input)."""
        stmts = tokenize("//A JOB CLASS=A,\n//B EXEC PGM=X\n")
        assert len(stmts) == 2
        assert stmts[0].operation == "JOB"
        assert stmts[1].operation == "EXEC"

    def test_no_trailing_comma_means_no_continuation(self) -> None:
        stmts = tokenize("//A JOB CLASS=A\n//B EXEC PGM=X\n")
        assert len(stmts) == 2

    def test_continuation_respects_parenthesised_sub_list(self) -> None:
        stmts = tokenize("//A DD DISP=(NEW,CATLG,DELETE),\n//    SPACE=(CYL,(10,5))\n")
        assert len(stmts) == 1
        by_key = {p.key: p.value for p in stmts[0].parameters}
        assert by_key["DISP"] == "(NEW,CATLG,DELETE)"
        assert by_key["SPACE"] == "(CYL,(10,5))"


class TestInStreamData:
    def test_data_between_dd_star_and_slash_star_is_skipped(self) -> None:
        stmts = tokenize("//A DD *\nTHIS IS DATA\nSO IS THIS\n/*\n//B EXEC PGM=X\n")
        assert [s.name for s in stmts] == ["A", "B"]

    def test_dd_data_keyword_also_starts_in_stream_data(self) -> None:
        stmts = tokenize("//A DD DATA\nSOME DATA\n/*\n//B EXEC PGM=X\n")
        assert [s.name for s in stmts] == ["A", "B"]

    def test_in_stream_data_ends_at_the_next_statement_without_a_delimiter(
        self,
    ) -> None:
        """Some shops omit the ``/*`` delimiter when a ``//`` statement
        follows directly -- also recognised as ending the data, matching
        real JCL's own tolerance for a missing delimiter. A data line
        that itself happens to start with ``//`` is therefore
        indistinguishable from a real statement and *does* end the
        in-stream data early -- a known, accepted ambiguity of the
        no-delimiter form, not something this lexer can resolve without
        seeing the ``/*`` (the standard's own recommended, unambiguous
        way to end in-stream data)."""
        stmts = tokenize("//A DD *\nDATA LINE\n//B EXEC PGM=X\n")
        assert [s.name for s in stmts] == ["A", "B"]


class TestParameterParsing:
    def test_positional_and_keyword_mixed(self) -> None:
        params = parse_parameters("(ACCT123),'JOHN DOE',CLASS=A")
        assert params[0].key is None
        assert params[0].value == "(ACCT123)"
        assert params[1].key is None
        assert params[1].value == "'JOHN DOE'"
        assert params[2].key == "CLASS"
        assert params[2].value == "A"

    def test_comma_inside_quotes_does_not_split(self) -> None:
        params = parse_parameters("PARM='A,B,C'")
        assert len(params) == 1
        assert params[0].value == "'A,B,C'"

    def test_comma_inside_parens_does_not_split(self) -> None:
        params = parse_parameters("DISP=(NEW,CATLG,DELETE)")
        assert len(params) == 1
        assert params[0].value == "(NEW,CATLG,DELETE)"

    def test_nested_parens(self) -> None:
        params = parse_parameters("SPACE=(CYL,(10,5),RLSE)")
        assert len(params) == 1
        assert params[0].value == "(CYL,(10,5),RLSE)"

    def test_empty_text_produces_no_parameters(self) -> None:
        assert parse_parameters("") == ()
        assert parse_parameters("   ") == ()

    def test_value_containing_equals_inside_quotes_is_not_split_as_keyword(
        self,
    ) -> None:
        """The first top-level ``=`` splits key/value; one inside quotes
        does not count."""
        params = parse_parameters("PARM='X=Y'")
        assert params[0].key == "PARM"
        assert params[0].value == "'X=Y'"
