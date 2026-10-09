#!/usr/bin/env python3
"""T4 round 28: terminate a research worker IN THE MIDDLE OF CONTENT SUPPORT (the serial stage a Fresh Run is most likely
to time out in) the way the job manager does (research_jobs.JobManager._terminate_process: terminate(), join 5 s,
kill), then inventory what it kept and rebuild the structured-adapter stage with zero calls. Zero provider calls: the
spawned worker's bottom HTTP transport is the probe's fixed-response mock (sitecustomize, plan hang_cs: content-support
request 2 is held open); non-loopback sockets are blocked.

    python run_cs_termination_probe.py --out-dir <new dir>
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "termination_probe"
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    if out.exists():
        print("refusing: out dir exists", file=sys.stderr)
        return 2
    (out / "runs").mkdir(parents=True)
    os.environ.update({"PYTHONPATH": f"{PROBE}{os.pathsep}{REPO}", "R28_PROBE_PLAN": "hang_cs", "R28_PROBE_LOG": str(out / "provider_requests.jsonl"),
                       "R28_PROBE_NET_LOG": str(out / "blocked_network.jsonl")})
    sys.path.insert(0, str(PROBE))
    import cs_probe_child

    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(target=cs_probe_child.run, args=(str(out / "runs"), str(out / "probe.sqlite")), daemon=True)
    started = time.time()
    worker.start()
    held = None
    while time.time() - started < 180 and worker.is_alive():
        log = out / "provider_requests.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()] if log.is_file() else []
        held = next((r for r in rows if r.get("held_open")), None)
        if held:
            break
        time.sleep(0.2)
    time.sleep(1.0)
    terminated_at = time.time()
    # exactly research_jobs.JobManager._terminate_process
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=5)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=5)
    run_dirs = [p for p in (out / "runs").iterdir() if p.is_dir()]
    rows = [json.loads(line) for line in (out / "provider_requests.jsonl").read_text().splitlines()] if (out / "provider_requests.jsonl").is_file() else []
    record = {"held_request": held, "worker_exitcode": worker.exitcode, "terminated_after_seconds": round(terminated_at - started, 2),
              "run_dir": str(run_dirs[0]) if len(run_dirs) == 1 else [str(p) for p in run_dirs],
              "provider_requests": {t: sum(1 for r in rows if r.get("task") == t) for t in sorted({r.get("task") for r in rows})},
              "blocked_non_loopback_connections": len((out / "blocked_network.jsonl").read_text().splitlines()) if (out / "blocked_network.jsonl").is_file() else 0}
    (out / "probe_result.json").write_text(json.dumps(record, indent=1, default=str) + "\n")
    print(json.dumps(record, indent=1, default=str))
    if len(run_dirs) != 1:
        return 1
    inspect = subprocess.run([sys.executable, str(HERE / "run_with_network_trap.py"), str(HERE / "inspect_terminated_run.py"), "--run-dir", str(run_dirs[0]),
                              "--rebuild-root", str(out / "rebuild"), "--stage", "structured_adapter", "--profile", "t3_verified_20261008",
                              "--out", str(out / "inspect_result.json")],
                             capture_output=True, text=True, env={k: v for k, v in os.environ.items() if not k.startswith("R28_") and k != "PYTHONPATH"})
    (out / "inspect_stdout.txt").write_text(inspect.stdout + inspect.stderr)
    print(inspect.stdout[-3000:], inspect.stderr[-2000:])
    return inspect.returncode


if __name__ == "__main__":
    raise SystemExit(main())
