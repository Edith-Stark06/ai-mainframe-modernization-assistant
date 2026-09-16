# Benchmark report — benchmark-v1

- model: `n/a`  provider: `HeuristicDemoProvider`  mode: `retrieval`
- prompt version: `p6-prompt-v1`  analysis version: `deterministic-analysis-phases-1-5`  dataset version: `phase6-v1`
- benchmark content hash: `df0ff3202f54bfaf1dabecb801bbb07506875d78b689d9c641a2dd461aa8a632`
- timestamp: 2026-09-06T00:00:00Z

## Overall

- examples: 22
- pass rate: 0.7727
- hallucination rate (mean per example): 0.3636
- mean attribution precision: 0.0909
- mean attribution recall: 0.0909
- parse-failure rate: 0.0
- mean latency (s): 0.0002
- total tokens: unavailable
- estimated cost: unavailable

## By task

| task | n | pass rate | headline metric | hallucinations |
|---|---|---|---|---|
| business_rule_extraction | 5 | 0.8 | 0.8 | 2 |
| cobol_explanation | 2 | 1.0 | 1.0 | 0 |
| cobol_to_java | 3 | 1.0 | 0.9444 | 0 |
| cobol_to_structured | 1 | 1.0 | 1.0 | 0 |
| modernization_qa | 2 | 0.5 | 1.0 | 3 |
| modernization_recommendation | 2 | 1.0 | 1.0 | 0 |
| risk_identification | 4 | 1.0 | 1.0 | 0 |
| source_grounded_qa | 3 | 0.0 | 0.3333 | 3 |

## By difficulty

| difficulty | n | pass rate | hallucinations |
|---|---|---|---|
| easy | 4 | 1.0 | 0 |
| medium | 8 | 0.875 | 1 |
| difficult | 4 | 1.0 | 0 |
| adversarial | 6 | 0.3333 | 7 |

## Failures / hallucinations

- `business_rule_extraction-3d00c56cb600` (business_rule_extraction/adversarial) — passed=False hallucinations=2
- `modernization_qa-5aa9528205d8` (modernization_qa/adversarial) — passed=False hallucinations=3
- `source_grounded_qa-06930284c322` (source_grounded_qa/medium) — passed=False hallucinations=1
- `source_grounded_qa-a98c817daa3f` (source_grounded_qa/adversarial) — passed=False hallucinations=1
- `source_grounded_qa-ae907e8e0dbb` (source_grounded_qa/adversarial) — passed=False hallucinations=1
