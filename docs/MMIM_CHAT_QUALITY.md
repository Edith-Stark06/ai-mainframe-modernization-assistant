# Chat answer quality: retrieval, grounding, evaluation

## Purpose

A question to chat about `moderate_sales_report.cbl` — *"At what order total does the status become HIGH VALUE,
and what happens to the customer's discount rate for type R?"* — got an answer that guessed the threshold
("typically 10,000") instead of the real `WS-TOTAL >= 50000`. The parser had already extracted that rule
correctly; the failure was in what reached the model and in how it was told to answer.

## Measured causes

| Cause | Evidence |
|---|---|
| A two-part question is one vector, a blur of both parts | The `50000` rule was not retrieved at `top_k`=5; asking only the first part found it at rank 1 |
| Vector-only search has no exact-text match | A literal such as `HIGH VALUE` or `0.18` was found only by chance |
| A field's `PIC`/`VALUE` was buried in one whole-DATA-DIVISION chunk | "What tax rate?" missed `VALUE 0.18` |
| Re-indexing never removed old chunks | The same paragraph and IR chunks appeared twice, wasting slots |
| Chat reused the *explanation* prompt with the question appended, no temperature | The model was free to fill gaps, differently on each run |

## What changed

1. **Stale chunks are replaced.** `app/rag/ingestion.py::index_program` (now the one indexing path, used by
   `/chat/index` and by the evaluation) deletes a file's earlier chunks before adding the new ones, only after
   ingestion and embedding succeeded. `VectorIndex` gained `list_chunks` and `delete`.
2. **Hybrid retrieval** (`app/rag/retrieval/hybrid.py`). Each part of the question (`query.py::split_question`,
   deterministic) gets a vector search *and* a BM25 exact-word search (`lexical.py`; COBOL `WS-TOTAL`, Java `wsTotal`
   and numbers such as `0.18` tokenise alike, and a verbatim phrase such as `HIGH VALUE` earns a bonus). All rankings
   are fused with reciprocal-rank fusion and chunks with identical text are dropped. A small explicit glossary maps
   everyday words to COBOL verbs (`user`/`enter` → `ACCEPT`, `show` → `DISPLAY`).
3. **Per-field `data_item` chunks** so a field's picture and initial value are directly retrievable.
4. **Default `top_k` is 8** (chat API and UI client), the smallest value at which the evaluation retrieves all
   the evidence.
5. **Grounded prompt** (`app/ai/grounding.py`): answer only from the context, never guess numbers, say "not in the
   retrieved context" for anything missing, cite chunk ids, and treat *parser-derived business rules* — now
   passed separately from the other chunks — as authoritative over any paraphrase. Chunks are labelled with
   their ids.
6. **Low temperature** (`LLM_TEMPERATURE`, default `0.0`) for the NVIDIA/OpenAI-compatible provider, so
   the same question gets the same answer. (Anthropic's API takes no sampling parameters.)
7. **Unverified-figure check** (`app/rag/grounding.py`): every number in the answer must appear in the
   retrieved context or the question (percent/fraction forms such as `18` ↔ `0.18` count; whole numbers under
   10 are ignored). Any other figure is listed in the answer text and in the response's `ungrounded_figures`.

## Measurement

`python -m app.rag.evaluation --mode vector|hybrid --top-k N [--cases FILE]` scores retrieval with no model:
each case is a question plus text that must appear in the retrieved chunks ("complete" = all of it did).
`scripts/evaluate_chat.py` runs the same questions through the live API and checks the answers.

Fraction of cases with **all** evidence retrieved:

| Program | Questions | Vector-only, before any change | Vector-only, new chunks | Hybrid, `top_k` 5 | Hybrid, `top_k` 8 |
|---|---|---|---|---|---|
| Sales report (developed against) | 14 | 64% (top_k 5) | 71% / 79% (top_k 5 / 8) | 86% | **100%** |
| Eligibility (held out) | 8 | — | 88% | **100%** | **100%** |

The held-out program and its questions were written after the design was fixed and nothing was tuned on them.
Both sets are small; treat the figures as a regression guard, not a benchmark. The tests
(`tests/rag/test_retrieval_evaluation.py`, marked `slow`, real embedding model) fail if hybrid retrieval drops
below these results.

## Answer style

A correct answer can still be hard to read. A live answer to "analyze the converted java code" was a 522-word
`Summary:`/`Explanation:` block with a 12-row table whose last column was raw chunk ids
(`[java_method-e8524fdcdb084683]`). The model cannot be fine-tuned from here, but its output can be shaped, and
the shaping is measured (`app/rag/style.py`, reported by `scripts/evaluate_chat.py`).

1. **Prompt style rules** (`app/ai/grounding.py`): direct answer first in one or two plain sentences, then short
   one-line bullets (at most 6 for a specific question, 10 when asked to explain or analyze a program), no
   tables/headings/"Note" sections, identifiers in backticks, no hedging words ("presumably", "likely").
2. **Short numbered citations.** Retrieved chunks are numbered `[1]`, `[2]`, ... in the prompt, the answer cites
   `[2]`, and the chat Evidence list shows the same numbers (`context[].ref` in the API response).
3. **Deterministic clean-up** (`app/rag/answer_format.py`), applied whatever the model writes: raw chunk ids become
   their number (unknown ids are dropped), markdown tables become bullet lists (citation columns and row numbers
   removed), dangling `**` markers and trailing double-space breaks are removed, blank-line runs collapsed.
4. **No parsing labels in chat.** The `Summary:` / `Explanation:` format is still requested (it is what the
   parser needs) but chat shows the direct answer followed by the detail.

Measured on 16 live answers (10 fact questions + 6 open-ended ones such as "analyze the converted java code"),
`openai/gpt-oss-20b` via NVIDIA, temperature 0:

| | Before | After |
|---|---|---|
| Raw chunk-id citations | 57 | **0** |
| Markdown table rows | 22 | **0** |
| `Summary:`/`Explanation:` labels shown | 32 | **0** |
| Hedging words | 1 | 0 |
| Average length | 158 words | **95 words** |
| Fact questions answered correctly | 10/10 | 10/10 |

The open-ended "analyze the converted java code" answer went from 522 words with a table to 254 words of bullets.
Latency is unchanged and dominated by the hosted model (3-20 s for most answers, up to ~90 s for the longest).

Limits: the counts measure readability noise, not quality of the prose; the table-to-bullet conversion keeps every
non-citation column joined by " — ", which reads well for two or three columns and less well for many; the length
limits are requested in the prompt, not enforced.

## Limits

* The unverified-figure check compares numbers, not meaning: a number that appears elsewhere in the context but is
  used wrongly is not flagged (a guessed "10,000" is grounded whenever a different rule mentions 10000), and a
  correctly *computed* figure is reported as unverified — the safe direction.
* The glossary is hand-written and small; extend it when an evaluation case shows a gap.
* Lexical search lists every chunk matching the filter for each query. That is fine for one file's chunks
  (tens to hundreds); a workspace-wide search over very large systems would need an inverted index.
* `data_item` chunks add `ChunkType.DATA_ITEM`; previously indexed files gain them on the next re-index.
* Answer wording still depends on the model; a small model can still misread correct context.
