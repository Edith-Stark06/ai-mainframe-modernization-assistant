# Benchmark report — benchmark-v1

- model: `n/a`  provider: `HeuristicDemoProvider`  mode: `raw`
- prompt version: `p6-prompt-v1`  analysis version: `deterministic-analysis-phases-1-5`  dataset version: `phase6-v1`
- benchmark content hash: `df0ff3202f54bfaf1dabecb801bbb07506875d78b689d9c641a2dd461aa8a632`
- timestamp: 2026-09-06T00:00:00Z

## Overall

- examples: 22
- pass rate: 0.4091
- hallucination rate (mean per example): 1.0
- mean attribution precision: 0.0909
- mean attribution recall: 0.0909
- parse-failure rate: 0.0
- mean latency (s): 0.0001
- total tokens: unavailable
- estimated cost: unavailable

## By task

| task | n | pass rate | headline metric | hallucinations |
|---|---|---|---|---|
| business_rule_extraction | 5 | 0.0 | 0.0 | 12 |
| cobol_explanation | 2 | 1.0 | 1.0 | 0 |
| cobol_to_java | 3 | 1.0 | 0.9444 | 0 |
| cobol_to_structured | 1 | 1.0 | 1.0 | 0 |
| modernization_qa | 2 | 0.0 | 0.5 | 4 |
| modernization_recommendation | 2 | 0.5 | 0.5 | 1 |
| risk_identification | 4 | 0.5 | 0.375 | 2 |
| source_grounded_qa | 3 | 0.0 | 0.0 | 3 |

## By difficulty

| difficulty | n | pass rate | hallucinations |
|---|---|---|---|
| easy | 4 | 1.0 | 0 |
| medium | 8 | 0.25 | 12 |
| difficult | 4 | 0.5 | 2 |
| adversarial | 6 | 0.1667 | 8 |

## Failures / hallucinations

- `business_rule_extraction-1c72b226df65` (business_rule_extraction/medium) — passed=False hallucinations=3
- `business_rule_extraction-291016d74081` (business_rule_extraction/medium) — passed=False hallucinations=2
- `business_rule_extraction-2b08747b07e9` (business_rule_extraction/medium) — passed=False hallucinations=3
- `business_rule_extraction-3d00c56cb600` (business_rule_extraction/adversarial) — passed=False hallucinations=2
- `business_rule_extraction-d3542f7335ff` (business_rule_extraction/medium) — passed=False hallucinations=2
- `modernization_qa-36f573950d82` (modernization_qa/medium) — passed=False hallucinations=1
- `modernization_qa-5aa9528205d8` (modernization_qa/adversarial) — passed=False hallucinations=3
- `modernization_recommendation-d285d85e7d98` (modernization_recommendation/difficult) — passed=False hallucinations=1
- `risk_identification-187076740efe` (risk_identification/difficult) — passed=False hallucinations=1
- `risk_identification-772231015e43` (risk_identification/adversarial) — passed=False hallucinations=1
- `source_grounded_qa-06930284c322` (source_grounded_qa/medium) — passed=False hallucinations=1
- `source_grounded_qa-a98c817daa3f` (source_grounded_qa/adversarial) — passed=False hallucinations=1
- `source_grounded_qa-ae907e8e0dbb` (source_grounded_qa/adversarial) — passed=False hallucinations=1
