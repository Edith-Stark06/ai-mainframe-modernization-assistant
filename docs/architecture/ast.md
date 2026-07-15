# AST Foundation Architecture

## Overview

The Abstract Syntax Tree (AST) is the central data structure of the COBOL
Understanding Engine.  It provides a semantically clean, normalized
representation of a COBOL program, stripped of syntactic noise (whitespace,
redundant keywords, column artefacts).

The AST layer sits between the Parser (which consumes tokens) and the
Semantic Analyser (which reasons about program meaning).

---

## Immutable Nodes

All AST nodes are **frozen dataclasses**.

```python
@dataclass(frozen=True)
class ASTNode(ABC):
    start_position: Position
    end_position: Position
```

### Why immutability?

| Property | Benefit |
|----------|---------|
| Thread safety | Nodes can be shared across analysis passes without locking |
| Hashability | Nodes can be stored in `set` and used as `dict` keys |
| Predictability | No pass can accidentally mutate a node seen by another pass |
| Simpler reasoning | No defensive copying needed |

To "modify" an AST node (e.g. during source transformation), a new node is
constructed with the updated fields.  The original remains unchanged.

---

## Node Hierarchy

```
ASTNode (abstract base)
├── ProgramNode     — root of the entire COBOL compilation unit
└── DivisionNode    — one COBOL division (future: SectionNode, ParagraphNode …)
```

### ASTNode

Every concrete node inherits from `ASTNode`:

- `start_position: Position` — source position of the node's first token.
- `end_position: Position`   — source position of the node's last token.
- `accept(visitor)` — abstract; dispatches to the appropriate visitor method.

### DivisionNode

Represents one COBOL division.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Division name in uppercase (`"IDENTIFICATION"`, `"DATA"`, etc.) |
| `children` | `tuple[ASTNode, ...]` | Ordered child nodes (sections, paragraphs) |

### ProgramNode

Root node for an entire COBOL program.

| Field | Type | Description |
|-------|------|-------------|
| `identification_division` | `DivisionNode \| None` | IDENTIFICATION DIVISION |
| `environment_division` | `DivisionNode \| None` | ENVIRONMENT DIVISION |
| `data_division` | `DivisionNode \| None` | DATA DIVISION |
| `procedure_division` | `DivisionNode \| None` | PROCEDURE DIVISION |

Any absent division is `None`.

---

## Compiler Pipeline

```
COBOL File  (on disk)
     |
     v
Source Reader              app.parser.lexer.source_reader
     |
     v
Format Detector            app.parser.lexer.format_detector
     |
     v
Source Normalizer          app.parser.lexer.normalizer
     |
     v
Character Scanner          app.parser.lexer.scanner
     |
     v
Lexer                      app.parser.lexer.lexer
     |  list[Token]
     v
Parser                     app.parser.syntax (future task)
     |  ProgramNode
     v
AST Layer                  app.parser.ast      <- this component
     |
     v
Semantic Analyser          app.parser.semantic (future task)
     |
     v
IR / Analysis Results      app.parser.ir
```

---

## Visitor Pattern

The Visitor pattern decouples AST structure from AST operations.

### Why Visitor?

COBOL programs require many independent analysis passes:

- Division detection
- Variable declaration extraction
- Business rule extraction
- Dead code detection
- Data flow analysis

Without the Visitor pattern, each pass would need to add methods to every
AST node class.  With Visitor, each pass is a self-contained subclass:

```python
class DivisionCollector(ASTVisitor):
    def __init__(self) -> None:
        self.names: list[str] = []

    def visit_division(self, node: DivisionNode) -> None:
        self.names.append(node.name)
```

### ASTVisitor interface

```python
class ASTVisitor(ABC):
    def visit_program(self, node: ProgramNode) -> Any:
        ...   # no-op by default

    def visit_division(self, node: DivisionNode) -> Any:
        ...   # no-op by default
```

Default implementations are no-ops so subclasses only override what they
need.

### Dispatch via accept()

Each node implements `accept(visitor)`:

```python
# In ProgramNode:
def accept(self, visitor):
    return visitor.visit_program(self)

# In DivisionNode:
def accept(self, visitor):
    return visitor.visit_division(self)
```

---

## Parser Protocol

`ParserProtocol` is a `typing.Protocol` (structural interface) that defines
the contract any parser must satisfy:

```python
class ParserProtocol(Protocol):
    def parse(self, tokens: list[Token]) -> ProgramNode:
        ...
```

This allows the AST layer to be tested with mock parsers and swapped to
different parser implementations without changing downstream code.

---

## Exception Hierarchy

```
Exception
+-- ParserError               app.parser.syntax.parser_exceptions
```

`ParserError` carries:

| Attribute | Type  | Description |
|-----------|-------|-------------|
| `message` | `str` | Human-readable failure description |
| `line`    | `int` | One-based line of the offending token |
| `column`  | `int` | One-based column of the offending token |
| `offset`  | `int` | Zero-based byte offset |

---

## Design Principles

- **Immutability** — all nodes are frozen dataclasses.
- **Abstraction** — `ASTNode` is abstract; no direct instantiation.
- **Extensibility** — new node types added without modifying existing ones.
- **Separation of concerns** — AST models know nothing about parsing or lexing.
- **Visitor pattern** — analysis passes are decoupled from the tree structure.
