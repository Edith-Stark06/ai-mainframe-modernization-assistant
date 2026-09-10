"""
#130 — generate a minimal, deterministic, framework-free Java test harness
from #129 behavioral test cases + the #126 generated project.

No JUnit (or any other test framework) exists in this Python-first
repository, so this introduces the smallest possible executable
mechanism: one reflective harness class per source
(``<Main>BehaviorHarness.java``) that a plain ``java`` invocation drives
per test case — set fields via reflection (using the SAME
COBOL->Java field-name convention as the existing generator,
:func:`app.backend.java.naming.to_java_field_name`, never re-derived),
invoke the entry method, capture stdout + field state, and self-assert
against the expected values #129 already computed. This is documented
here rather than silently assumed.

Only *executable* behavioral test cases get an artifact — a #129 case
already marked ``executable=False`` needs no Java test; #131 reports it
INCONCLUSIVE directly from the extraction reason.
"""

from __future__ import annotations

from app.backend.java.naming import to_java_field_name
from app.behavioral.extraction.models import BehavioralSuite, BehavioralTestCase
from app.behavioral.javatests.models import JavaTarget, JavaTestArtifact
from app.java_modernization.generation.models import GeneratedProject

__all__ = ["HARNESS_SUFFIX", "generate_java_tests", "render_harness"]

HARNESS_SUFFIX = "BehaviorHarness"


def render_harness(main_class: str) -> str:
    return f"""\
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.lang.reflect.Field;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Phase 10 (#130) deterministic behavioral test harness for {main_class}.
 * NOT a claim of semantic equivalence — see MODERNIZATION_MANIFEST.json.
 *
 * Usage: java {main_class}{HARNESS_SUFFIX} <field>=<value> ... [expect:<field>=<value> ...]
 * Output lines (stable prefixes, one observation per line):
 *   ##EXEC## ok=<bool> [error=<msg>]
 *   ##STDOUT## <captured System.out line, in order>
 *   ##FIELD## <name>=<value>          (one per requested "expect:" field)
 *   ##ASSERT## PASS | FAIL <field ...>
 */
public class {main_class}{HARNESS_SUFFIX} {{
    public static void main(String[] args) throws Exception {{
        Map<String, String> in = new LinkedHashMap<>();
        Map<String, String> expect = new LinkedHashMap<>();
        for (String a : args) {{
            int eq = a.indexOf('=');
            if (eq < 0) continue;
            String k = a.substring(0, eq);
            String v = a.substring(eq + 1);
            if (k.startsWith("expect:")) {{
                expect.put(k.substring(7), v);
            }} else {{
                in.put(k, v);
            }}
        }}

        {main_class} target = new {main_class}();
        try {{
            for (Map.Entry<String, String> e : in.entrySet()) {{
                Field f = target.getClass().getDeclaredField(e.getKey());
                f.setAccessible(true);
                if (f.getType() == int.class) {{
                    f.setInt(target, Integer.parseInt(e.getValue()));
                }} else if (f.getType() == long.class) {{
                    f.setLong(target, Long.parseLong(e.getValue()));
                }} else {{
                    f.set(target, e.getValue());
                }}
            }}
        }} catch (Throwable t) {{
            System.out.println("##EXEC## ok=false error=input setup: " + t);
            System.exit(2);
            return;
        }}

        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        PrintStream original = System.out;
        System.setOut(new PrintStream(buf));
        boolean ranOk = true;
        String execError = "";
        try {{
            target.run();
        }} catch (Throwable t) {{
            ranOk = false;
            execError = String.valueOf(t);
        }} finally {{
            System.setOut(original);
        }}

        System.out.println(
            "##EXEC## ok=" + ranOk
            + (execError.isEmpty() ? "" : " error=" + execError.replace("\\n", " "))
        );
        for (String line : buf.toString().split("\\n", -1)) {{
            if (!line.isEmpty()) {{
                System.out.println("##STDOUT## " + line);
            }}
        }}

        boolean allPass = ranOk;
        StringBuilder failed = new StringBuilder();
        for (Map.Entry<String, String> e : expect.entrySet()) {{
            String actual;
            try {{
                Field f = target.getClass().getDeclaredField(e.getKey());
                f.setAccessible(true);
                actual = String.valueOf(f.get(target));
            }} catch (NoSuchFieldException ex) {{
                actual = "<no-such-field>";
            }}
            System.out.println("##FIELD## " + e.getKey() + "=" + actual);
            if (!actual.equals(e.getValue())) {{
                allPass = false;
                failed.append(e.getKey()).append(' ');
            }}
        }}
        System.out.println(allPass ? "##ASSERT## PASS" : "##ASSERT## FAIL " + failed);
        System.exit(allPass ? 0 : 1);
    }}
}}
"""


def _run_args(test: BehavioralTestCase) -> tuple[str, ...]:
    args: list[str] = []
    for inp in test.inputs:
        args.append(f"{to_java_field_name(inp.name)}={inp.value}")
    for out in test.expected_outputs:
        if out.kind == "field":
            args.append(f"expect:{to_java_field_name(out.name)}={out.expected_value}")
    for state in test.expected_state_changes:
        key = f"expect:{to_java_field_name(state.field)}="
        if not any(a.startswith(key) for a in args):
            args.append(f"{key}{state.to_value}")
    return tuple(args)


def generate_java_tests(
    suite: BehavioralSuite, project: GeneratedProject
) -> tuple[dict[str, str], tuple[JavaTestArtifact, ...]]:
    """Returns ``(extra_files, artifacts)`` — merge ``extra_files`` into
    ``project.files`` before compiling."""
    harness_path = f"src/{project.main_class}{HARNESS_SUFFIX}.java"
    files = {harness_path: render_harness(project.main_class)}

    artifacts: list[JavaTestArtifact] = []
    for test in suite.executable_tests:
        assumptions = [
            "fields are set/read via reflection using the existing "
            "COBOL->Java field-naming convention",
            "the entry method (run()) is invoked directly — paragraph-level "
            "targeting is not modeled by this minimal harness",
        ]
        artifacts.append(
            JavaTestArtifact(
                test_id=test.test_id,
                behavioral_test_id=test.test_id,
                file_path=harness_path,
                test_name=f"test_{test.test_id}",
                java_target=JavaTarget(
                    java_class=project.main_class, java_method="run"
                ),
                run_args=_run_args(test),
                source_refs=test.source_refs,
                business_rule_ids=test.business_rule_ids,
                assumptions=tuple(assumptions),
            )
        )
    artifacts.sort(key=lambda a: a.test_id)
    return files, tuple(artifacts)
