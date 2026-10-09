#!/usr/bin/env python3
"""Runs the final run's failing test FILES against two recorded "before"
trees and writes per-nodeid outcomes (round 14, section 2):

  head      pristine `git archive HEAD` snapshot (committed baseline; no .git,
            no untracked/ignored files -- so some tests fail there for purely
            environmental reasons; a HEAD failure only counts as "same cause"
            when the reason matches, which build_regression_manifest does NOT
            assume -- it relies on the pre-thread tree for that)
  pre       the CURRENT working tree with the five files the audit-concurrency
            repair thread edited replaced by their RECORDED pre-thread versions
            (Claude Code file-history backups, each verified by diff). The
            tests directory is a COPY (not a symlink) so test files resolve
            REPO_ROOT inside this tree and the frozen-hash tests see the
            pre-thread file contents. docs/, outputs/, scripts/ and .env are
            symlinked (read access; no secrets copied).

Usage: run_counterfactual_trees.py <files.txt> <out_dir>
"""
import json, os, shutil, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FH = Path.home() / ".claude/file-history/8d38fcbd-98ee-4ff6-b804-8855e3f6b189"
PRE_THREAD = {
    "comqutor_alpha/structure_engine/alpha_mapper.py": FH / "60ccb681d0ed547b@v6",
    "comqutor_alpha/structure_engine/week2_llm.py": FH / "3bf6612f604a7651@v17",
    "comqutor_alpha/llm_runtime/contracts.py": FH / "7dcb1eacbb377004@v5",
    "comqutor_alpha/llm_runtime/session.py": FH / "c6d1ccde9b659efc@v3",
    "comqutor_alpha/api/routes_research.py": FH / "6997f2f4f1787e8e@v11",
}
# NOT reverted (they are round-14 edits that only WIDEN what is accepted or
# forwarded, and no file in the failing set exercises them): replay/
# source_bundle.py's optional-field mirror and the adapter's transparent
# proxy. Leaving them current avoids inventing a state that never existed.


def build_pre_tree(tree: Path):
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    shutil.copytree(REPO / "comqutor_alpha", tree / "comqutor_alpha", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "tests", tree / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("docs", "outputs", "scripts", "evaluation", "tradingagents", "cli"):
        if (REPO / name).exists():
            (tree / name).symlink_to(REPO / name)
    for name in ("pyproject.toml", ".env", "requirements.txt"):
        if (REPO / name).exists():
            if name == ".env":
                (tree / name).symlink_to(REPO / name)
            else:
                shutil.copyfile(REPO / name, tree / name)
    for rel, src in PRE_THREAD.items():
        shutil.copyfile(src, tree / rel)


def run_files(root: Path, files: list[str], out_xml: Path, log: Path):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("COMQUTOR_PROBE_LOG", None)
    with log.open("w") as fh:
        subprocess.run(
            [str(REPO / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junitxml={out_xml}", *files],
            cwd=str(root), env=env, stdout=fh, stderr=subprocess.STDOUT,
        )


def outcomes(xml_path: Path) -> dict:
    out = {}
    if not xml_path.exists():
        return out
    for tc in ET.parse(xml_path).getroot().iter("testcase"):
        parts = tc.get("classname", "").split(".")
        module = [p for p in parts if not p[:1].isupper()]
        klass = [p for p in parts if p[:1].isupper()]
        nodeid = "/".join(module) + ".py::" + "::".join(klass + [tc.get("name")])
        if tc.find("failure") is not None:
            out[nodeid] = ["FAILED", ((tc.find("failure").get("message") or "").splitlines() or [""])[0][:600]]
        elif tc.find("error") is not None:
            out[nodeid] = ["ERROR", ((tc.find("error").get("message") or "").splitlines() or [""])[0][:600]]
        elif tc.find("skipped") is not None:
            out[nodeid] = ["SKIPPED", ""]
        else:
            out[nodeid] = ["PASSED", ""]
    return out


def main():
    files = [l.strip() for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
    out_dir = Path(sys.argv[2]); out_dir.mkdir(parents=True, exist_ok=True)
    head_tree = Path(os.environ["HEAD_SNAPSHOT"])
    pre_tree = Path(os.environ["PRE_TREE"])
    build_pre_tree(pre_tree)
    run_files(pre_tree, files, out_dir / "pre_junit.xml", out_dir / "pre_run.log")
    json.dump(outcomes(out_dir / "pre_junit.xml"), open(out_dir / "pre_outcomes.json", "w"), indent=1)
    run_files(head_tree, files, out_dir / "head_junit.xml", out_dir / "head_run.log")
    json.dump(outcomes(out_dir / "head_junit.xml"), open(out_dir / "head_outcomes.json", "w"), indent=1)
    for name in ("pre", "head"):
        o = json.load(open(out_dir / f"{name}_outcomes.json"))
        from collections import Counter
        print(name, dict(Counter(v[0] for v in o.values())))


if __name__ == "__main__":
    main()
