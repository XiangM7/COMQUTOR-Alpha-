#!/usr/bin/env python3
"""Controlled before/after experiments for
tests/test_week2_llm.py::test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts
(round 14, section 3).

Question: is the occasional failure (a) a race in the TEST's own
synchronization, or (b) an identity/terminal-state/retry/log race introduced
into production code by the round-13 contextvar redesign?

Evidence built from RECORDED states, not reconstructed history:
  * ORIGINAL test = the Claude Code file-history backup of tests/test_week2_llm.py
    taken before the fix (version v10, contains self._call3_done.set() inside
    model.invoke()).
  * PRE-THREAD gateway = file-history backups of week2_llm.py v17, alpha_mapper.py
    v6, contracts.py v5, session.py v3, routes_research.py v11 -- the states
    immediately before the audit-concurrency repair thread (each verified by
    diffing against the next recorded version: the delta is exactly the repair
    thread's own edits). The adapter's pre-thread snapshot is not cleanly
    isolated; it is left as-is (its only repair-thread change was a comment +
    a removed concurrency override that this test never reaches).
  * FINAL gateway = the current working tree.

Experiment A: natural timing, N runs per combination.
Experiment B: the SAME scenario with a controlled delay injected only into
  call 3's persist step (SemanticRuntimeSession.finalize_call). If the test's
  synchronization truly guaranteed "call 3 persists before call 1", a slow
  persist could not reorder them. It does reorder them -> the original test
  never established the order it asserts. The FIXED test (call 1 blocks on an
  Event set only after call 3's gateway.invoke_json has fully returned) must
  pass under the same delay.
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FH = Path.home() / ".claude/file-history/8d38fcbd-98ee-4ff6-b804-8855e3f6b189"
OUT = Path(__file__).parent / "flaky_test_root_cause_experiments.json"
SCRATCH = Path(os.environ["SCRATCH_DIR"])

PRE_THREAD = {
    "comqutor_alpha/structure_engine/alpha_mapper.py": FH / "60ccb681d0ed547b@v6",
    "comqutor_alpha/structure_engine/week2_llm.py": FH / "3bf6612f604a7651@v17",
    "comqutor_alpha/llm_runtime/contracts.py": FH / "7dcb1eacbb377004@v5",
    "comqutor_alpha/llm_runtime/session.py": FH / "c6d1ccde9b659efc@v3",
    "comqutor_alpha/api/routes_research.py": FH / "6997f2f4f1787e8e@v11",
}
ORIGINAL_TEST = SCRATCH / "original_test_week2_llm_v10.py"  # byte copy of the recorded backup (file-history v10); the backup has no .py suffix so importlib cannot load it directly
FIXED_TEST = REPO / "tests/test_week2_llm.py"
TEST_NAME = "test_concurrent_success_timeout_and_retry_all_preserve_their_own_attempts"

RUNNER = r'''
import importlib.util, json, sys, tempfile, time
from pathlib import Path
tree, test_file, test_name, n, delay = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
sys.path.insert(0, tree)
import comqutor_alpha
assert comqutor_alpha.__file__.startswith(tree), comqutor_alpha.__file__
spec = importlib.util.spec_from_file_location("test_under_test", test_file)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
fn = getattr(mod, test_name)
if delay > 0:
    from comqutor_alpha.llm_runtime import session as sess
    orig = sess.SemanticRuntimeSession.finalize_call
    def slow(self, trace, **kw):
        if trace is not None and (trace.input_payload or {}).get("which") == 3:
            time.sleep(delay)   # only call 3's persist is slowed
        return orig(self, trace, **kw)
    sess.SemanticRuntimeSession.finalize_call = slow
fails, reasons = 0, {}
for _ in range(n):
    with tempfile.TemporaryDirectory() as td:
        try:
            fn(Path(td))
        except BaseException as e:
            fails += 1
            key = (type(e).__name__ + ": " + (str(e).splitlines() or [""])[0])[:90]
            reasons[key] = reasons.get(key, 0) + 1
print(json.dumps({"runs": n, "failures": fails, "reasons": reasons}))
'''


def materialize_original_test():
    src = FH / "810ce5c536fdc282@v10"
    shutil.copyfile(src, ORIGINAL_TEST)


def build_pre_thread_tree() -> Path:
    tree = SCRATCH / "pre_thread_tree"
    if tree.exists():
        shutil.rmtree(tree)
    shutil.copytree(REPO / "comqutor_alpha", tree / "comqutor_alpha", ignore=shutil.ignore_patterns("__pycache__"))
    (tree / "tradingagents").symlink_to(REPO / "tradingagents")
    for rel, src in PRE_THREAD.items():
        shutil.copyfile(src, tree / rel)
    return tree


def run(tree: Path, test_file: Path, n: int, delay: float) -> dict:
    proc = subprocess.run(
        [str(REPO / ".venv/bin/python"), "-c", RUNNER, str(tree), str(test_file), TEST_NAME, str(n), str(delay)],
        capture_output=True, text=True, cwd=str(tree),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if proc.returncode != 0:
        return {"error": proc.stderr[-600:]}
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main():
    n_natural = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    n_delayed = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    materialize_original_test()
    pre = build_pre_thread_tree()
    trees = {"pre_thread_gateway": pre, "final_gateway": REPO}
    tests = {"original_test(v10)": ORIGINAL_TEST, "fixed_test": FIXED_TEST}
    result = {"natural_timing": {}, "call3_persist_delayed_0.15s": {}}
    for tname, tfile in tests.items():
        for gname, tree in trees.items():
            result["natural_timing"][f"{tname} @ {gname}"] = run(tree, tfile, n_natural, 0.0)
            result["call3_persist_delayed_0.15s"][f"{tname} @ {gname}"] = run(tree, tfile, n_delayed, 0.15)
    OUT.write_text(json.dumps(result, indent=2))
    for section, rows in result.items():
        print(f"\n== {section} ==")
        for k, v in rows.items():
            print(f"  {k:46} runs={v.get('runs')} failures={v.get('failures')} {v.get('reasons') or v.get('error', '')}")


if __name__ == "__main__":
    main()
