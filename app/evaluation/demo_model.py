"""
Deterministic NON-LLM "model" behind :class:`HeuristicDemoProvider`.

It parses the evaluation prompt (a format this project controls),
figures out the task and whether deterministic-analysis context is
present, and returns a plausible answer:

* with analysis / retrieved context -> it reads the answer out of the
  JSON blocks (simulating a model that grounds itself in the evidence);
* with only raw source -> a degraded, partially-guessed answer, and for
  the adversarial traps it sometimes takes the bait.

This exists ONLY to demonstrate the #120 harness and produce a committed
sample report. It is not a language model.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["answer_from_prompt"]

_JSON_BLOCK = re.compile(r"```json\s*(.*?)```", re.DOTALL)
_SOURCE_ID = re.compile(r"## COBOL source \(([^)]+)\)")


def _analysis_blocks(prompt: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in _JSON_BLOCK.finditer(prompt):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        # keyed by a guess of what the block is
        header = (
            prompt[: m.start()].rsplit("###", 1)[-1].splitlines()[0].strip().lower()
        )
        if "business rule" in header:
            out["business_rules"] = obj
        elif "risk" in header:
            out["risks"] = obj
        elif "strateg" in header:
            out["strategy"] = obj
        elif "dependenc" in header:
            out["dependencies"] = obj
        elif "coverage" in header:
            out["coverage"] = obj
        elif "ast" in header:
            out["ast"] = obj
        elif "cfg" in header:
            out["cfg"] = obj
    return out


def _has_analysis(prompt: str) -> bool:
    return (
        "Deterministic analysis (Phases 1-5)" in prompt
        or "Retrieved deterministic evidence" in prompt
    )


def _source_id(prompt: str) -> str:
    m = _SOURCE_ID.search(prompt)
    return m.group(1) if m else ""


def _cobol_source(prompt: str) -> str:
    m = re.search(r"```cobol\s*(.*?)```", prompt, re.DOTALL)
    return m.group(1) if m else ""


def answer_from_prompt(prompt: str) -> str:  # noqa: C901 - simple dispatch
    task_line = prompt.split("## Task\n", 1)[-1].split("\n", 1)[0].lower()
    has_ana = _has_analysis(prompt)
    blocks = _analysis_blocks(prompt) if has_ana else {}
    sid = _source_id(prompt)
    src = _cobol_source(prompt)

    # -- business rule extraction -----------------------------------
    if "extract the business rules" in task_line:
        if has_ana and "business_rules" in blocks:
            rules = blocks["business_rules"]
            rules = rules if isinstance(rules, list) else []
            return json.dumps(
                {
                    "business_rules": [
                        {
                            "condition": r.get("condition"),
                            "actions": [a.get("raw") for a in r.get("actions", [])],
                        }
                        for r in rules
                    ]
                }
            )
        # raw guess: pull IF ... conditions from the source
        conds = re.findall(r"IF\s+([A-Z0-9\-]+\s*[<>=]+\s*[^\n]+?)(?:\n|END-IF)", src)
        rules = [{"condition": c.strip(), "actions": []} for c in conds[:2]]
        if "20 percent" in src.lower() or "discount" in src.lower():
            # takes the misleading-comment bait
            rules.append(
                {
                    "condition": "WS-CUSTOMER-TYPE = 'V'",
                    "actions": ["apply 20% discount"],
                }
            )
        return json.dumps({"business_rules": rules})

    # -- risk identification ---------------------------------------
    if "identify the modernization risks" in task_line:
        if has_ana and "risks" in blocks:
            risks = blocks["risks"]
            risks = risks if isinstance(risks, list) else []
            return json.dumps(
                {
                    "risks": [
                        {"category": r.get("category"), "severity": r.get("severity")}
                        for r in risks
                    ]
                }
            )
        guessed = []
        if "CALL" in src:
            guessed.append({"category": "EXTERNAL_CALL", "severity": "MEDIUM"})
        if "COMP-3" in src or "GO TO" in src:
            guessed.append({"category": "UNSUPPORTED_SYNTAX", "severity": "HIGH"})
        return json.dumps({"risks": guessed})

    # -- recommendation ------------------------------------------
    if "recommend a modernization strategy" in task_line:
        if has_ana and isinstance(blocks.get("strategy"), dict):
            prim = blocks["strategy"].get("primary") or {}
            return json.dumps(
                {
                    "primary": {
                        "strategy": prim.get("strategy"),
                        "prerequisites": prim.get("prerequisites", []),
                    }
                }
            )
        return json.dumps({"primary": {"strategy": "REWRITE", "prerequisites": []}})

    # -- cobol -> structured ------------------------------------
    if "structured representation" in task_line:
        paras = re.findall(r"^\s{7}([A-Z0-9\-]+)\.\s*$", src, re.MULTILINE)
        if has_ana and isinstance(blocks.get("ast"), dict):
            ast = blocks["ast"]
            pd = (ast.get("procedure_division") if isinstance(ast, dict) else {}) or {}
            paras = [p.get("name") for p in pd.get("paragraphs", [])]
        return json.dumps(
            {
                "ast": {
                    "procedure_division": {"paragraphs": [{"name": p} for p in paras]}
                },
                "cfg_summary": {},
            }
        )

    # -- cobol -> java -----------------------------------------
    if "translate this program to java" in task_line:
        _m = re.search(r"PROGRAM-ID\.\s*([A-Z0-9\-]+)", src)
        pid = _m.group(1) if _m else "Prog"
        cls = "".join(w.capitalize() for w in re.split(r"[-_]", pid))
        body = "        return;"
        if "DISPLAY" in src:
            body = '        System.out.println("...");\n' + body
        if "IF" in src:
            body = "        if (x > 0) {\n        }\n" + body
        java = (
            f"public class {cls} {{\n"
            "    public static void main(String[] args) {\n"
            f"        new {cls}().run();\n    }}\n\n"
            "    public void run() {\n" + body + "\n    }\n}\n"
        )
        return json.dumps({"java": java})

    # -- explanation / modernization QA ------------------------
    if "explain what this program does" in task_line:
        paras = re.findall(r"^\s{7}([A-Z0-9\-]+)\.\s*$", src, re.MULTILINE)
        text = f"Program {sid}. Paragraphs: {', '.join(paras)}. "
        if has_ana and isinstance(blocks.get("dependencies"), list):
            calls = sorted(
                {
                    d.get("target", "").strip("'\"")
                    for d in (
                        blocks["dependencies"]
                        if isinstance(blocks.get("dependencies"), list)
                        else []
                    )
                    if str(d.get("type")).upper() == "CALL"
                }
            )
            if calls:
                text += f"It calls {', '.join(calls)}. "
        if has_ana and isinstance(blocks.get("coverage"), dict):
            codes = (
                (
                    blocks["coverage"].get("unsupported_syntax")
                    if isinstance(blocks.get("coverage"), dict)
                    else {}
                )
                or {}
            ).get("codes", [])
            if codes:
                text += f"Unsupported constructs: {', '.join(codes)}. "
        return text

    if "answer the question" in task_line:
        q = prompt.split("## Question\n", 1)[-1].split("\n", 1)[0].lower()
        if "business rule" in q:
            if has_ana and "business_rules" in blocks:
                rules = (
                    blocks["business_rules"]
                    if isinstance(blocks["business_rules"], list)
                    else []
                )
                return json.dumps(
                    {
                        "answer": {
                            "business_rules": [
                                {
                                    "rule_id": r.get("rule_id"),
                                    "condition": r.get("condition"),
                                }
                                for r in rules
                            ]
                        }
                    }
                )
            # raw + misleading-name trap
            if "FRAUD" in src:
                return json.dumps(
                    {
                        "answer": {
                            "business_rules": [
                                {
                                    "rule_id": "BR-001",
                                    "condition": "fraud score threshold",
                                }
                            ]
                        }
                    }
                )
            return json.dumps({"answer": {"business_rules": []}})
        if "external" in q or "dependen" in q:
            calls = sorted({m for m in re.findall(r"CALL\s+'([A-Z0-9\-]+)'", src)})
            if has_ana and isinstance(blocks.get("dependencies"), list):
                calls = sorted(
                    {
                        d.get("target", "").strip("'\"")
                        for d in (
                            blocks["dependencies"]
                            if isinstance(blocks.get("dependencies"), list)
                            else []
                        )
                        if str(d.get("type")).upper() == "CALL"
                    }
                )
            return json.dumps({"answer": {"external_calls": calls}})
        return json.dumps({"answer": "see analysis"})

    # -- source-grounded QA -----------------------------------
    if "answer the question only from the source" in task_line:
        q = prompt.split("## Question\n", 1)[-1].split("\n", 1)[0].lower()
        lines = src.splitlines()
        if "call" in q:
            calls = []
            cites = []
            for i, ln in enumerate(lines, 1):
                m = re.search(r"CALL\s+'([A-Z0-9\-]+)'", ln)
                if m:
                    calls.append(m.group(1))
                    cites.append({"line": i, "claim_terms": ["CALL"]})
            return json.dumps(
                {"answer": {"external_calls": sorted(set(calls))}, "citations": cites}
            )
        if "unsupported" in q or "not support" in q:
            codes = []
            if "COMP-3" in src:
                codes.append("SYN200")
            if "GO TO" in src:
                codes.append("SYN100")
            return json.dumps(
                {
                    "answer": {
                        "has_unsupported_syntax": bool(codes),
                        "codes": sorted(codes),
                    }
                }
            )
        if "tier" in q or "priority" in q:
            return json.dumps({"answer": {"determinable": False}})
        # paragraph inventory
        paras, cites = [], []
        for i, ln in enumerate(lines, 1):
            m = re.match(r"^\s{7}([A-Z0-9\-]+)\.\s*$", ln)
            if m:
                paras.append(m.group(1))
                cites.append({"line": i, "claim_terms": []})
        return json.dumps({"answer": {"paragraphs": paras}, "citations": cites})

    return "{}"
