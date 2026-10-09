"""2026-10-02 incident fix.

A real NVDA research run (``034a0a60-430e-41f8-8321-03a11389707a``) wrote
2111 rows into the production database ``comqutor_alpha`` instead of the
isolated ``comqutor_alpha_test`` one. Root cause: the isolated-database
launcher (``docs/audit_artifacts/round_source_linking_t0_t2/
run_nvda_fresh_run_isolated_db.sh``) exported a ``COMQUTOR_DATABASE_URL``
override in its own process and verified it -- but
``scripts/start_live_comqutor.sh``, the next script in its own ``exec``
chain, re-sourced ``.env`` afterward (to pick up credentials/other config),
which silently clobbered that override back to ``.env``'s own production
value before the API process ever started. See
``docs/audit_artifacts/round_source_linking_t0_t2/
incident_prod_db_writes_20261002/INCIDENT_REPORT_AND_CLEANUP_PLAN.md`` for
the full incident writeup.

These tests exercise the two real places a live research run's database
target actually gets resolved -- not a same-process unit test that merely
proves a correctly-constructed DSN works (see
``tests/test_graph_persistence.py::TestRequiredDatabaseNameGuard`` for that
narrower coverage):

1. ``TestLiveLauncherDatabaseIsolationEndToEnd`` runs the REAL content of
   ``scripts/start_live_comqutor.sh`` (a byte-for-byte copy with only the
   ``.env`` path and the final ``exec comqutor-api`` line substituted -- the
   env-resolution logic, port check, and Python preflight are the actual
   production script, unmodified) as a real subprocess, end to end.
2. ``TestBackgroundWorkerSpawnInheritsDatabaseTarget`` spawns a real
   ``multiprocessing.get_context("spawn")`` child process -- exactly the
   mechanism ``comqutor_alpha.research_jobs.JobManager`` uses for every real
   research job -- and has it call the real
   ``build_write_repository_from_env`` itself, proving environment
   inheritance and guard enforcement both hold across an actual process
   boundary, not just within the current interpreter.

No real Provider call is made or needed by either class: the Python
preflight's credential check is presence-only (it never contacts a
Provider), and the worker-spawn tests use local SQLite/unreachable-address
targets.
"""

from __future__ import annotations

import multiprocessing
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_SCRIPT = REPO_ROOT / "scripts" / "start_live_comqutor.sh"
REAL_ENV_FILE = REPO_ROOT / ".env"


def _build_fake_env(tmp_path: Path, fake_database_url: str) -> Path:
    """The real ``.env``'s own content (so the Python preflight's
    presence-only credential check passes using the real provider key)
    with only ``COMQUTOR_DATABASE_URL`` replaced by a non-connecting marker
    value -- never a real production or test database."""
    real_env_lines = REAL_ENV_FILE.read_text().splitlines()
    lines = [line for line in real_env_lines if not line.startswith("COMQUTOR_DATABASE_URL=")]
    lines.append(f"COMQUTOR_DATABASE_URL={fake_database_url}")
    fake_env_path = tmp_path / "fake.env"
    fake_env_path.write_text("\n".join(lines) + "\n")
    return fake_env_path


def _build_patched_script(fake_env_path: Path, capture_file: Path) -> Path:
    """A byte-for-byte copy of the real launcher script with only the two
    ``.env`` path references and the final ``exec comqutor-api`` line
    substituted. Written as a sibling of the real script (never relocated)
    so ``$SCRIPT_DIR``/``$REPO_ROOT`` still resolve to the real repository
    -- ``.venv/bin/activate`` and the Python preflight must use the real
    venv and the real ``comqutor_alpha`` package."""
    real_content = REAL_SCRIPT.read_text()
    patched = real_content.replace('"$REPO_ROOT/.env"', f'"{fake_env_path}"')
    assert patched.count(str(fake_env_path)) == 2, "expected exactly two .env path references to substitute"
    capture_cmd = f'echo "CAPTURED_COMQUTOR_DATABASE_URL=${{COMQUTOR_DATABASE_URL:-}}" > "{capture_file}"; exit 0'
    assert "exec comqutor-api\n" in patched
    patched = patched.replace("exec comqutor-api\n", capture_cmd + "\n")
    patched_path = REAL_SCRIPT.parent / "._test_start_live_comqutor_patched.sh"
    patched_path.write_text(patched)
    patched_path.chmod(0o755)
    return patched_path


_SKIP_REASON_NO_ENV = "requires a real .env with provider credentials for the live preflight"
_SKIP_REASON_NO_VENV = "requires the real project venv"


@pytest.mark.skipif(not REAL_ENV_FILE.exists(), reason=_SKIP_REASON_NO_ENV)
@pytest.mark.skipif(not (REPO_ROOT / ".venv" / "bin" / "activate").exists(), reason=_SKIP_REASON_NO_VENV)
class TestLiveLauncherDatabaseIsolationEndToEnd:
    def _run(self, tmp_path: Path, *, caller_override: str | None, fake_production_url: str) -> str:
        capture_file = tmp_path / "captured.txt"
        fake_env_path = _build_fake_env(tmp_path, fake_production_url)
        patched_path = _build_patched_script(fake_env_path, capture_file)
        try:
            env = dict(os.environ)
            if caller_override is None:
                env.pop("COMQUTOR_DATABASE_URL", None)
            else:
                env["COMQUTOR_DATABASE_URL"] = caller_override
            result = subprocess.run(
                ["bash", str(patched_path)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, (
                f"script failed: stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            assert capture_file.exists(), (
                f"script exited before reaching the capture point: stdout={result.stdout!r}"
            )
            content = capture_file.read_text().strip()
            match = re.match(r"CAPTURED_COMQUTOR_DATABASE_URL=(.*)", content)
            assert match is not None, f"unexpected capture file content: {content!r}"
            return match.group(1)
        finally:
            patched_path.unlink(missing_ok=True)

    def test_no_caller_override_uses_env_value_unchanged(self, tmp_path):
        """Normal case (a developer running this script directly, no
        isolated-DB wrapper involved): .env's own value flows through
        exactly as before -- zero behavior change for this case."""
        fake_prod = "postgresql+psycopg://fake:fake@127.0.0.1:1/FAKE_PRODUCTION_MARKER_DB"

        resolved = self._run(tmp_path, caller_override=None, fake_production_url=fake_prod)

        assert resolved == fake_prod

    def test_caller_override_survives_the_env_reload(self, tmp_path):
        """The exact incident scenario: a caller (the isolated-DB launcher)
        has already exported COMQUTOR_DATABASE_URL before invoking this
        script, and .env defines its own, different value. The caller's
        override must win -- this is what was previously silently
        clobbered, causing a real run to write into production."""
        fake_prod = "postgresql+psycopg://fake:fake@127.0.0.1:1/FAKE_PRODUCTION_MARKER_DB"
        fake_isolated = "postgresql+psycopg://fake:fake@127.0.0.1:2/FAKE_ISOLATED_TEST_MARKER_DB_test"

        resolved = self._run(tmp_path, caller_override=fake_isolated, fake_production_url=fake_prod)

        assert resolved == fake_isolated
        assert resolved != fake_prod


def _build_fake_env_for_week2_retries(tmp_path: Path, fake_max_retries: str) -> Path:
    """Same pattern as ``_build_fake_env``, but replaces
    ``COMQUTOR_WEEK2_LLM_MAX_RETRIES`` instead of ``COMQUTOR_DATABASE_URL`` --
    covers the 2026-10-06 generalization of the same clobber-on-reload class
    of bug (see ``scripts/start_live_comqutor.sh``'s own
    ``_CALLER_OVERRIDE_VARS`` comment)."""
    real_env_lines = REAL_ENV_FILE.read_text().splitlines()
    lines = [line for line in real_env_lines if not line.startswith("COMQUTOR_WEEK2_LLM_MAX_RETRIES=")]
    lines.append(f"COMQUTOR_WEEK2_LLM_MAX_RETRIES={fake_max_retries}")
    fake_env_path = tmp_path / "fake_week2_retries.env"
    fake_env_path.write_text("\n".join(lines) + "\n")
    return fake_env_path


def _build_patched_script_for_week2_retries(fake_env_path: Path, capture_file: Path) -> Path:
    real_content = REAL_SCRIPT.read_text()
    patched = real_content.replace('"$REPO_ROOT/.env"', f'"{fake_env_path}"')
    assert patched.count(str(fake_env_path)) == 2, "expected exactly two .env path references to substitute"
    capture_cmd = (
        f'echo "CAPTURED_COMQUTOR_WEEK2_LLM_MAX_RETRIES=${{COMQUTOR_WEEK2_LLM_MAX_RETRIES:-}}" '
        f'> "{capture_file}"; exit 0'
    )
    assert "exec comqutor-api\n" in patched
    patched = patched.replace("exec comqutor-api\n", capture_cmd + "\n")
    patched_path = REAL_SCRIPT.parent / "._test_start_live_comqutor_patched_week2_retries.sh"
    patched_path.write_text(patched)
    patched_path.chmod(0o755)
    return patched_path


@pytest.mark.skipif(not REAL_ENV_FILE.exists(), reason=_SKIP_REASON_NO_ENV)
@pytest.mark.skipif(not (REPO_ROOT / ".venv" / "bin" / "activate").exists(), reason=_SKIP_REASON_NO_VENV)
class TestLiveLauncherWeek2MaxRetriesIsolationEndToEnd:
    """2026-10-06 (AMD Fresh Run preflight, round 7): reproduced, before any
    real Provider spend, that this repository's own .env defines
    COMQUTOR_WEEK2_LLM_MAX_RETRIES=1 -- a caller requiring 0 (this run's
    "zero retries at both layers" budget constraint) had that override
    silently clobbered back to 1 by start_live_comqutor.sh's unconditional
    `source .env`, the exact same bug class as the 2026-10-02 database-URL
    incident, just for a different variable. Fixed by generalizing the same
    capture-before/restore-after pattern; these tests run the REAL launcher
    script end to end (same technique as
    TestLiveLauncherDatabaseIsolationEndToEnd above) to prove it."""

    def _run(self, tmp_path: Path, *, caller_override: str | None, fake_env_value: str) -> str:
        capture_file = tmp_path / "captured_week2_retries.txt"
        fake_env_path = _build_fake_env_for_week2_retries(tmp_path, fake_env_value)
        patched_path = _build_patched_script_for_week2_retries(fake_env_path, capture_file)
        try:
            env = dict(os.environ)
            if caller_override is None:
                env.pop("COMQUTOR_WEEK2_LLM_MAX_RETRIES", None)
            else:
                env["COMQUTOR_WEEK2_LLM_MAX_RETRIES"] = caller_override
            result = subprocess.run(
                ["bash", str(patched_path)],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, (
                f"script failed: stdout={result.stdout!r} stderr={result.stderr!r}"
            )
            assert capture_file.exists(), (
                f"script exited before reaching the capture point: stdout={result.stdout!r}"
            )
            content = capture_file.read_text().strip()
            match = re.match(r"CAPTURED_COMQUTOR_WEEK2_LLM_MAX_RETRIES=(.*)", content)
            assert match is not None, f"unexpected capture file content: {content!r}"
            return match.group(1)
        finally:
            patched_path.unlink(missing_ok=True)

    def test_no_caller_override_uses_env_value_unchanged(self, tmp_path):
        resolved = self._run(tmp_path, caller_override=None, fake_env_value="1")
        assert resolved == "1"

    def test_caller_override_survives_the_env_reload(self, tmp_path):
        """The exact reproduced defect: a caller exports
        COMQUTOR_WEEK2_LLM_MAX_RETRIES=0 (required for this run's zero-retry
        budget constraint) before invoking this script, and .env defines its
        own, different value (1). The caller's override must win."""
        resolved = self._run(tmp_path, caller_override="0", fake_env_value="1")
        assert resolved == "0"


def _spawn_worker_target(queue, output_root: str) -> None:
    """Runs in the spawned child process -- a fresh interpreter, nothing
    inherited except argv/env/picklable arguments. Mirrors exactly what
    ``comqutor_alpha.research_jobs._job_worker_entrypoint`` does: call
    ``build_write_repository_from_env`` itself and let it resolve
    ``COMQUTOR_DATABASE_URL`` from this process's own (inherited)
    environment."""
    import os as _os

    from comqutor_alpha.storage.db.repository import (
        GraphPersistenceError,
        build_write_repository_from_env,
    )

    seen_url = _os.environ.get("COMQUTOR_DATABASE_URL")
    try:
        build_write_repository_from_env(output_root=output_root)
        queue.put(("ok", seen_url, None))
    except GraphPersistenceError as exc:
        queue.put(("refused", seen_url, exc.reason_code))
    except Exception as exc:  # pragma: no cover - diagnostic only
        queue.put(("error", seen_url, f"{type(exc).__name__}: {exc}"))


class TestBackgroundWorkerSpawnInheritsDatabaseTarget:
    """comqutor_alpha.research_jobs.JobManager runs every real research job
    in its own ``multiprocessing.get_context("spawn")`` child process
    (``_job_worker_entrypoint``), which independently calls
    ``build_write_repository_from_env`` itself. These tests use the real
    spawn mechanism (a genuine separate OS process, not a thread or a
    same-process call) to prove environment inheritance and guard
    enforcement both hold there -- not merely within the test's own
    interpreter."""

    def test_worker_process_inherits_the_correct_target_and_succeeds(self, tmp_path, monkeypatch):
        sqlite_path = tmp_path / "worker_target.db"
        monkeypatch.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{sqlite_path}")
        monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", str(sqlite_path))

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        proc = ctx.Process(target=_spawn_worker_target, args=(queue, str(tmp_path)))
        proc.start()
        outcome, seen_url, detail = queue.get(timeout=60)
        proc.join(timeout=60)

        assert outcome == "ok", f"worker did not succeed: seen_url={seen_url!r} detail={detail!r}"
        assert seen_url == f"sqlite:///{sqlite_path}"
        assert sqlite_path.exists()  # ensure_schema() actually ran against the inherited target

    def test_worker_process_inherits_a_mismatched_target_and_refuses(self, tmp_path, monkeypatch):
        """The exact incident's worker-side half: if COMQUTOR_DATABASE_URL
        were ever wrong by the time the API process spawns its worker, the
        worker inherits that same wrong value -- and must refuse before any
        write, exactly like the main process's own synchronous claim does."""
        monkeypatch.setenv(
            "COMQUTOR_DATABASE_URL",
            "postgresql+psycopg://fake:fake@192.0.2.1:5999/comqutor_alpha",
        )
        monkeypatch.setenv("COMQUTOR_REQUIRE_DATABASE_NAME", "comqutor_alpha_test")

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        proc = ctx.Process(target=_spawn_worker_target, args=(queue, str(tmp_path)))
        proc.start()
        outcome, seen_url, detail = queue.get(timeout=60)
        proc.join(timeout=60)

        assert outcome == "refused", f"worker did not refuse: seen_url={seen_url!r} detail={detail!r}"
        assert seen_url == "postgresql+psycopg://fake:fake@192.0.2.1:5999/comqutor_alpha"
        assert detail == "DATABASE_TARGET_MISMATCH"
