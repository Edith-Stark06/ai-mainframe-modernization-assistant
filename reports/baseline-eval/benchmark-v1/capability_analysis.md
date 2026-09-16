# Capability analysis / fine-tuning assessment (#120)

- benchmark: `benchmark-v1`  prompt: `p6-prompt-v1`  analysis: `deterministic-analysis-phases-1-5`
- providers: {'raw': 'HeuristicDemoProvider', 'analysis': 'HeuristicDemoProvider', 'retrieval': 'HeuristicDemoProvider'}

**No task shows clear fine-tuning evidence in this run. Prompting + deterministic analysis is the higher-leverage next step. Re-evaluate #121 only after a live-provider baseline confirms the pattern.**

| task | raw | analysis | retrieval | lift | failure | cause | fine-tuning evidence |
|---|---|---|---|---|---|---|---|
| business_rule_extraction | 0.0 | 0.8 | 0.8 | 0.8 | hallucination | raw model lacks structured evidence; analysis supplies it | no fine-tuning evidence — deterministic analysis closes the gap |
| cobol_explanation | 1.0 | 1.0 | 1.0 | 0.0 | none | task is within base capability | no fine-tuning evidence — already strong |
| cobol_to_java | 1.0 | 1.0 | 1.0 | 0.0 | none | task is within base capability | no fine-tuning evidence — already strong |
| cobol_to_structured | 1.0 | 1.0 | 1.0 | 0.0 | none | task is within base capability | no fine-tuning evidence — already strong |
| modernization_qa | 0.0 | 0.5 | 0.5 | 0.5 | hallucination | mixed | collect more evidence — partial improvement from context; not yet a clear fine-tuning case |
| modernization_recommendation | 0.5 | 1.0 | 1.0 | 0.5 | none | raw model lacks structured evidence; analysis supplies it | no fine-tuning evidence — deterministic analysis closes the gap |
| risk_identification | 0.5 | 1.0 | 1.0 | 0.5 | none | raw model lacks structured evidence; analysis supplies it | no fine-tuning evidence — deterministic analysis closes the gap |
| source_grounded_qa | 0.0 | 0.0 | 0.0 | 0.0 | hallucination | mixed | collect more evidence — partial improvement from context; not yet a clear fine-tuning case |
