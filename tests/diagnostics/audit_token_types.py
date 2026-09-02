"""
Parser token-type assumption audit (task #104).

Purpose:
    Produce reproducible evidence for the audit of where parser
    correctness depends on ``TokenType`` classification.

    Several parser sites gate a grammar-word check behind a token-type
    test, e.g.::

        if tok.type is TokenType.KEYWORD:
            if tok.lexeme.upper() in SOME_SET:
                ...

    The lexer's reserved-keyword set is small (26 words, scoped to
    "milestone Task-010" in ``app/parser/lexer/keywords.py``), so most
    COBOL grammar words are emitted as ``TokenType.IDENTIFIER``.  Where
    a set gated behind a ``KEYWORD`` test contains such a word, that
    branch is unreachable.

    This script reports, from live lexer output rather than assumption:

    1. how the lexer actually classifies each grammar word;
    2. for each token-type-gated lexeme set in the parser, which members
       are reachable and which are dead;
    3. end-to-end parse outcomes for constructs whose handling depends
       on those gates.

Usage::

    python tests/diagnostics/audit_token_types.py

This is a diagnostic utility, not a pytest module: it asserts nothing
and changes no production behaviour.  It is intended to be re-run after
the #105 fixes to confirm the dead branches became reachable.

Author:
    Edith Stark

Project:
    AI-Powered Mainframe Modernization Assistant
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT in sys.path:
    sys.path.remove(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

from loguru import logger  # noqa: E402

logger.remove()

from app.parser.lexer.keywords import KEYWORDS  # noqa: E402
from app.parser.lexer.lexer import CobolLexer  # noqa: E402
from app.parser.syntax.parser_state import ParserState  # noqa: E402
from app.parser.syntax.program_parser import ProgramParser  # noqa: E402
from app.parser.syntax.token_stream import TokenStream  # noqa: E402

# ---------------------------------------------------------------------------
# Grammar words the parser layer refers to, by category.
# ---------------------------------------------------------------------------
GRAMMAR_WORDS: dict[str, list[str]] = {
    "divisions": ["IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "DIVISION"],
    "sections": [
        "SECTION",
        "CONFIGURATION",
        "INPUT-OUTPUT",
        "FILE",
        "WORKING-STORAGE",
        "LINKAGE",
        "LOCAL-STORAGE",
        "SCREEN",
        "REPORT",
        "COMMUNICATION",
    ],
    "identification clauses": [
        "PROGRAM-ID",
        "AUTHOR",
        "INSTALLATION",
        "DATE-WRITTEN",
        "DATE-COMPILED",
        "SECURITY",
    ],
    "data descriptors": [
        "FD",
        "SD",
        "PIC",
        "PICTURE",
        "VALUE",
        "OCCURS",
        "REDEFINES",
        "RENAMES",
        "USAGE",
        "COMP",
        "COMP-3",
        "JUSTIFIED",
        "SYNCHRONIZED",
        "BLANK",
        "FILLER",
        "IS",
    ],
    "environment clauses": [
        "SELECT",
        "ASSIGN",
        "ORGANIZATION",
        "STATUS",
        "FILE-CONTROL",
        "I-O-CONTROL",
        "SOURCE-COMPUTER",
        "OBJECT-COMPUTER",
        "SPECIAL-NAMES",
    ],
    "statement verbs (supported)": [
        "DISPLAY",
        "MOVE",
        "STOP",
        "RUN",
        "GOBACK",
        "ACCEPT",
        "ADD",
        "SUBTRACT",
        "MULTIPLY",
        "DIVIDE",
        "CALL",
        "IF",
        "PERFORM",
    ],
    "statement verbs (unsupported)": [
        "OPEN",
        "CLOSE",
        "READ",
        "WRITE",
        "REWRITE",
        "DELETE",
        "EVALUATE",
        "COMPUTE",
        "STRING",
        "UNSTRING",
        "INSPECT",
        "GO",
        "CONTINUE",
        "EXIT",
    ],
    "scope terminators / connectives": [
        "ELSE",
        "END-IF",
        "WHEN",
        "END-EVALUATE",
        "END-PERFORM",
        "TO",
        "FROM",
        "BY",
        "INTO",
        "UNTIL",
        "GIVING",
        "THRU",
        "COPY",
    ],
}

# ---------------------------------------------------------------------------
# Lexeme sets the parser tests tokens against.
#
# ``mode`` records how the enclosing check matches:
#   "keyword-gated" — behind ``if tok.type is TokenType.KEYWORD``, so any
#                     member the lexer does not reserve is unreachable.
#   "lexeme"        — matched with
#                     :func:`~app.parser.grammar_words.matches_grammar_word`
#                     against this explicit set, so reserved-word status is
#                     irrelevant and no member can be dead.
#
# Task #105 converted the sets that needed it.  A "keyword-gated" set with
# dead members is a defect; a "lexeme" set is safe by construction.
# ---------------------------------------------------------------------------
GATED_SETS: list[tuple[str, str, str, set[str]]] = [
    (
        "recovery._DIVISION_KEYWORDS",
        "keyword-gated",
        "app/parser/diagnostics/recovery.py",
        {"IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"},
    ),
    (
        "recovery._SECTION_KEYWORDS",
        "lexeme",
        "app/parser/diagnostics/recovery.py",
        {
            "WORKING-STORAGE",
            "FILE",
            "LINKAGE",
            "LOCAL-STORAGE",
            "SCREEN",
            "REPORT",
            "COMMUNICATION",
        },
    ),
    (
        "data_parser._UNSUPPORTED_SECTION_KEYWORDS",
        "lexeme",
        "app/parser/syntax/data_parser.py",
        {"FILE", "LINKAGE", "LOCAL-STORAGE", "SCREEN", "REPORT", "COMMUNICATION"},
    ),
    (
        "data_parser._NEXT_DIVISION_KEYWORDS",
        "keyword-gated",
        "app/parser/syntax/data_parser.py",
        {"ENVIRONMENT", "PROCEDURE", "IDENTIFICATION"},
    ),
    (
        "data_parser._PICTURE_TERMINATOR_WORDS",
        "lexeme",
        "app/parser/syntax/data_parser.py",
        {"VALUE", "OCCURS", "REDEFINES", "JUSTIFIED", "SYNCHRONIZED"},
    ),
    (
        "data_parser._PICTURE_WORDS",
        "lexeme",
        "app/parser/syntax/data_parser.py",
        {"PIC", "PICTURE"},
    ),
    (
        "data_parser._IS_WORD",
        "lexeme",
        "app/parser/syntax/data_parser.py",
        {"IS"},
    ),
    (
        "identification_parser missing-period guard",
        "lexeme",
        "app/parser/syntax/identification_parser.py",
        {
            "PROGRAM-ID",
            "AUTHOR",
            "INSTALLATION",
            "DATE-WRITTEN",
            "DATE-COMPILED",
            "SECURITY",
            "ENVIRONMENT",
            "DATA",
            "PROCEDURE",
            "DIVISION",
        },
    ),
    (
        "procedure_parser._UNSUPPORTED_STATEMENT_LEXEMES",
        "lexeme",
        "app/parser/syntax/procedure_parser.py",
        {"OPEN", "CLOSE", "READ", "WRITE", "EVALUATE", "COMPUTE", "STRING"},
    ),
    (
        "procedure_parser._DIVISION_KEYWORDS",
        "keyword-gated",
        "app/parser/syntax/procedure_parser.py",
        {"IDENTIFICATION", "ENVIRONMENT", "DATA"},
    ),
    (
        "environment_parser._DIVISION_HEADERS",
        "keyword-gated",
        "app/parser/syntax/environment_parser.py",
        {"IDENTIFICATION", "DATA", "PROCEDURE"},
    ),
]

_HDR = "IDENTIFICATION DIVISION.\nPROGRAM-ID. T.\n"
_WS = "DATA DIVISION.\nWORKING-STORAGE SECTION.\n"
_PROC = "PROCEDURE DIVISION.\nMAIN-PARA.\n    STOP RUN.\n"

# ---------------------------------------------------------------------------
# End-to-end constructs whose outcome depends on the gates above.
# ---------------------------------------------------------------------------
CONSTRUCTS: list[tuple[str, str]] = [
    ("PIC X(10)", _HDR + _WS + "01 WS-A PIC X(10).\n" + _PROC),
    ("PICTURE X(10)", _HDR + _WS + "01 WS-A PICTURE X(10).\n" + _PROC),
    ("PIC IS X(10)", _HDR + _WS + "01 WS-A PIC IS X(10).\n" + _PROC),
    ("PIC 9(2) VALUE 5", _HDR + _WS + "01 WS-A PIC 9(2) VALUE 5.\n" + _PROC),
    ("PIC 9(2) VALUE IS 5", _HDR + _WS + "01 WS-A PIC 9(2) VALUE IS 5.\n" + _PROC),
    ("PIC S9(4) COMP-3", _HDR + _WS + "01 WS-A PIC S9(4) COMP-3.\n" + _PROC),
    ("PIC X(5) REDEFINES", _HDR + _WS + "01 WS-A PIC X(5) REDEFINES WS-B.\n" + _PROC),
    ("PIC X(5) OCCURS 3", _HDR + _WS + "01 WS-A PIC X(5) OCCURS 3 TIMES.\n" + _PROC),
    (
        "FILE SECTION before WS",
        _HDR
        + "DATA DIVISION.\nFILE SECTION.\nFD F1.\n01 R1 PIC X(01).\n"
        + "WORKING-STORAGE SECTION.\n01 WS-A PIC X(01).\n"
        + _PROC,
    ),
    (
        "LINKAGE SECTION before WS",
        _HDR
        + "DATA DIVISION.\nLINKAGE SECTION.\n01 L1 PIC X(01).\n"
        + "WORKING-STORAGE SECTION.\n01 WS-A PIC X(01).\n"
        + _PROC,
    ),
    (
        "unsupported verb mid-paragraph",
        _HDR
        + "PROCEDURE DIVISION.\nMAIN-PARA.\n"
        + '    OPEN INPUT F1.\n    DISPLAY "A".\n    STOP RUN.\n',
    ),
]


def _rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def report_lexer_inventory() -> None:
    """Print the real lexer classification of every grammar word."""
    _rule("1. LEXER CLASSIFICATION OF GRAMMAR WORDS (live lexer output)")
    lexer = CobolLexer()
    print(f"lexer reserved-keyword set size: {len(KEYWORDS)}\n")
    for category, words in GRAMMAR_WORDS.items():
        keyword, identifier, other = [], [], []
        for word in words:
            try:
                token = lexer.tokenize(f"{word} X.", filename="p.cbl")[0]
                name = token.type.name
            except Exception as exc:  # pragma: no cover - diagnostic only
                name = f"LEXER-ERROR({type(exc).__name__})"
            if name == "KEYWORD":
                keyword.append(word)
            elif name == "IDENTIFIER":
                identifier.append(word)
            else:
                other.append(f"{word}:{name}")
        print(f"{category}:")
        print(f"    KEYWORD    ({len(keyword):>2}): {' '.join(keyword) or '-'}")
        print(f"    IDENTIFIER ({len(identifier):>2}): {' '.join(identifier) or '-'}")
        if other:
            print(f"    OTHER      ({len(other):>2}): {' '.join(other)}")


def report_gate_reachability() -> None:
    """Print which members of each lexeme set the enclosing check can reach."""
    _rule("2. REACHABILITY OF PARSER LEXEME SETS")
    print("A member of a keyword-gated set is DEAD if the lexer never emits it")
    print("as KEYWORD, because `if tok.type is TokenType.KEYWORD` is then never")
    print("true for it.  Lexeme-matched sets are safe by construction.\n")
    defects = 0
    for name, mode, location, members in GATED_SETS:
        not_reserved = sorted(members - KEYWORDS)
        if mode == "keyword-gated":
            verdict = "OK" if not not_reserved else "DEAD MEMBERS"
            if not_reserved:
                defects += 1
        else:
            verdict = "OK (lexeme-matched)"
        print(f"{name}  [{verdict}]")
        print(f"    {location}  ({mode})")
        print(f"    reserved words     : {' '.join(sorted(members & KEYWORDS)) or '-'}")
        print(f"    non-reserved words : {' '.join(not_reserved) or '-'}\n")
    print(f"keyword-gated sets containing unreachable members: {defects}")


def report_construct_outcomes() -> None:
    """Parse representative constructs and report what survives."""
    _rule("3. END-TO-END OUTCOMES FOR AFFECTED CONSTRUCTS")
    print(f"{'construct':<32}{'ws_items':>9}{'pictures':>26}{'proc':>6}{'diags':>7}")
    print("-" * 80)
    for label, source in CONSTRUCTS:
        try:
            tokens = CobolLexer().tokenize(source, filename="t.cbl")
            state = ParserState(TokenStream(tokens))
            program = ProgramParser()._parse_program(state)
        except Exception as exc:  # pragma: no cover - diagnostic only
            print(f"{label:<32}{type(exc).__name__}")
            continue
        storage = (
            program.data_division.working_storage if program.data_division else None
        )
        items = storage.items if storage else ()
        pictures = ",".join(str(getattr(i, "picture", None)) for i in items) or "-"
        print(
            f"{label:<32}{len(items):>9}{pictures[:25]:>26}"
            f"{str(program.procedure_division is not None):>6}"
            f"{len(state.diagnostics):>7}"
        )


def main() -> None:
    """Run the full audit report."""
    report_lexer_inventory()
    report_gate_reachability()
    report_construct_outcomes()
    print("\nAudit complete. This script only reads; it changes no state.")


if __name__ == "__main__":
    main()
