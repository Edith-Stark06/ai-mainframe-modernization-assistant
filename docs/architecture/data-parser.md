# Data Division Parser Architecture

## Overview

This document describes the design of the COBOL DATA DIVISION parser — the
second grammar-aware component in the COBOL parser pipeline.

The Data Division parser transforms a flat token stream into an immutable
`DataDivisionNode` containing a `WorkingStorageSectionNode` whose ordered
tuple of `DataItemNode` instances represents the declared data items.

---

## Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `ProgramParser` | Top-level coordinator; detects division presence via two-token lookahead |
| `DataDivisionParser` | Parses header + supported sections + data items; raises `ParserError` on errors |
| `DataDivisionNode` | Immutable root container for the division |
| `WorkingStorageSectionNode` | Immutable container for items in WORKING-STORAGE |
| `ElementaryItemNode` | Immutable carrier for elementary items (with PIC and optional VALUE) |
| `GroupItemNode` | Immutable carrier for group records (no PIC) |
| `ConditionNameNode` | Immutable carrier for 88-level condition-name entries |

---

## Supported Grammar

```
DATA DIVISION.

WORKING-STORAGE SECTION.

01 group-name .
   05 field-name  PIC picture-string [ VALUE literal ] .
   88 cond-name   VALUE literal .

77 standalone-name PIC picture-string [ VALUE literal ] .
```

Supported level numbers:

| Level | Meaning |
|-------|---------|
| 01–49 | Regular data items (group or elementary) |
| 66 | RENAMES — level number accepted but treated as elementary |
| 77 | Standalone elementary (non-contiguous) |
| 78 | Constant definition |
| 88 | Condition name |

Supported clauses:

| Clause | Notes |
|--------|-------|
| `PIC` / `PICTURE` | Followed by a picture string (e.g. `9(5)`, `X(30)`) |
| `PIC IS` | Optional `IS` keyword absorbed |
| `VALUE literal` | Simple single-literal VALUE clause |
| `VALUE IS literal` | Optional `IS` keyword absorbed |

---

## Unsupported Grammar (Out of Scope)

The following constructs are **not** implemented in this milestone and are
explicitly excluded:

| Construct | Reason |
|-----------|--------|
| `FILE SECTION` | Future milestone |
| `LINKAGE SECTION` | Future milestone |
| `LOCAL-STORAGE SECTION` | Future milestone |
| `SCREEN SECTION` | Future milestone |
| `REPORT SECTION` | Future milestone |
| `OCCURS` clause | Future milestone |
| `REDEFINES` clause | Future milestone |
| `RENAMES` (66-level) | Future milestone |
| `COMP`, `COMP-3` | Future milestone |
| `INDEXED BY` | Future milestone |
| `JUSTIFIED` | Future milestone |
| `SYNCHRONIZED` | Future milestone |
| `COPY` expansion | Resolver layer (future) |
| Semantic analysis | Semantic layer (future) |

When the parser encounters an unsupported section keyword (e.g. `FILE`,
`LINKAGE`), it stops parsing the DATA DIVISION and returns what has been
collected so far.  This preserves forward-compatibility.

---

## Parser Flow

```
ProgramParser.parse(tokens)
      |
      |  _is_data_division(): two-token lookahead (DATA DIVISION)
      |
      v
DataDivisionParser.parse(state)
      |
      |  consume: DATA DIVISION .
      |
      +–– _is_working_storage()? ──► _parse_working_storage(state)
      |                                     |
      |                              consume: WORKING-STORAGE SECTION .
      |                                     |
      |                              _parse_data_items(state)
      |                                     |
      |                              while current == NUMBER token:
      |                                     |
      |                              _parse_data_item(state)
      |                                     |
      |                        ┌────────────┴──────────────────────┐
      |                        │ level == 88                        │ level 01-77
      |                        ▼                                    ▼
      |              _parse_condition_name()          _parse_elementary_or_group()
      |                        │                                    │
      |                        │                         PIC clause? → ElementaryItemNode
      |                        │                         no PIC?    → GroupItemNode
      |                        ▼                                    ▼
      |              ConditionNameNode                 ElementaryItemNode | GroupItemNode
      |
      v
DataDivisionNode
  └── WorkingStorageSectionNode
        └── items: tuple[DataItemNode, ...]
```

---

## Division Detection

`ProgramParser._is_data_division()` peeks at the current and next token
**without consuming** either one.  This two-token lookahead is sufficient to
confirm the presence of `DATA DIVISION`:

```python
def _is_data_division(state: ParserState) -> bool:
    tok = state.stream.current()
    if tok.type is not TokenType.KEYWORD:
        return False
    if tok.lexeme.upper() != "DATA":
        return False
    next_tok = state.stream.peek()
    return (
        next_tok.type is TokenType.KEYWORD
        and next_tok.lexeme.upper() == "DIVISION"
    )
```

---

## AST Hierarchy

```
ASTNode (abstract)
├── DataDivisionNode
│     └── working_storage: WorkingStorageSectionNode | None
│           └── items: tuple[DataItemNode, ...]
│                 ├── GroupItemNode          (level 01-49, no PIC)
│                 ├── ElementaryItemNode     (level 01-49, 77; has PIC)
│                 └── ConditionNameNode      (level 88)
└── ...
```

All nodes are **frozen dataclasses** (`@dataclass(frozen=True)`):

- Immutable after construction — safe to share across analysis passes.
- Hashable — can be stored in sets or used as dict keys.
- Comparable by value — equality works without a custom `__eq__`.

### `DataDivisionNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `DATA` keyword |
| `end_position` | `Position` | Position of the last consumed token |
| `working_storage` | `WorkingStorageSectionNode \| None` | WORKING-STORAGE SECTION |

### `WorkingStorageSectionNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `WORKING-STORAGE` keyword |
| `end_position` | `Position` | Position of the last consumed token |
| `items` | `tuple[DataItemNode, ...]` | Ordered data items in this section |

### `ElementaryItemNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the level number token |
| `end_position` | `Position` | Position of the terminating period |
| `level` | `int` | COBOL level number |
| `name` | `str` | Data-name (uppercased) |
| `picture` | `str` | Picture string (e.g. `"9(5)"`) |
| `value` | `str \| None` | VALUE literal, or `None` if absent |

### `GroupItemNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the level number token |
| `end_position` | `Position` | Position of the terminating period |
| `level` | `int` | COBOL level number |
| `name` | `str` | Group-name (uppercased) |
| `children` | `tuple[DataItemNode, ...]` | Populated by future semantic pass |

### `ConditionNameNode` Fields

| Field | Type | Description |
|-------|------|-------------|
| `start_position` | `Position` | Position of the `88` token |
| `end_position` | `Position` | Position of the terminating period |
| `level` | `int` | Always `88` |
| `name` | `str` | Condition-name (uppercased) |
| `value` | `str \| None` | VALUE literal, or `None` if absent |

---

## Visitor Integration

All new AST nodes use **getattr-based dispatch** in `accept()`:

```python
def accept(self, visitor: object) -> object:
    visit = getattr(visitor, "visit_data_division", None)
    if callable(visit):
        return visit(self)
    return None
```

This preserves backward-compatibility with existing `ASTVisitor` subclasses
— they continue to work without modification.

To handle the new nodes, subclass `ASTVisitor` and add methods:

```python
class DataInventory(ASTVisitor):
    def visit_data_division(self, node: DataDivisionNode) -> None:
        if node.working_storage:
            for item in node.working_storage.items:
                item.accept(self)

    def visit_elementary_item(self, node: ElementaryItemNode) -> None:
        print(f"{node.level:02d} {node.name} PIC {node.picture}")

    def visit_group_item(self, node: GroupItemNode) -> None:
        print(f"{node.level:02d} {node.name}")

    def visit_condition_name(self, node: ConditionNameNode) -> None:
        print(f"88 {node.name} VALUE {node.value}")
```

---

## Error Handling

All parse errors raise `ParserError` from
`app.parser.syntax.parser_exceptions`.

| Condition | Error Message |
|-----------|---------------|
| Wrong second keyword (not `DIVISION`) | `expected 'DIVISION', got <actual>` |
| Missing period after `DATA DIVISION` | `UnexpectedEOFError` / `UnexpectedTokenError` |
| Missing period after `WORKING-STORAGE SECTION` | `UnexpectedEOFError` / `UnexpectedTokenError` |
| Invalid level number (e.g. 99) | `invalid level number 99; supported: 01–49, 66, 77, 78, 88` |
| Missing data-name after level | `expected data-name after level number <N>` |
| Missing period after data item | `expected '.' to terminate data item, got EOF` |
| Missing picture string after PIC | `expected picture string after PIC for '<name>'` |

---

## Implementation Notes

### Level Numbers and Tokens

The COBOL lexer emits level numbers (e.g. `01`, `05`, `77`, `88`) as
`TokenType.NUMBER` tokens (not `LEVEL_NUMBER`).  The parser converts them
to integers and validates membership in the supported set.

### Picture Strings

Picture strings may contain multiple tokens (e.g. `X(30)` scans as
`X`, `(`, `30`, `)`).  The `_read_picture_string()` helper accumulates all
tokens until it encounters a period, a `VALUE` keyword, or another terminal
clause keyword, then concatenates them into a single string.

### Flat Item List

The parser emits all data items into a flat list regardless of their nesting
level.  Group structure (parent/child relationships) is left for the future
semantic analysis pass, which will walk the flat list and construct the
nested tree based on level-number precedence rules.

---

## Future Enhancements

The following will be added in subsequent tasks:

```
DataDivisionParser._parse_data_division()
├── _parse_file_section()        (future)
├── _parse_working_storage()     ← (this task)
├── _parse_linkage_section()     (future)
├── _parse_local_storage()       (future)
├── _parse_screen_section()      (future)
└── _parse_report_section()      (future)
```

Additional clause support:

- `OCCURS` — array dimension parsing.
- `REDEFINES` — memory overlay declarations.
- `COMP`, `COMP-3` — binary and packed-decimal usage clauses.
- Multiple VALUE literals in 88-level entries (`VALUE 'Y' 'T'`).
- `PICTURE IS` full validation.
- Hierarchical grouping in `GroupItemNode.children` populated by the
  semantic pass.
