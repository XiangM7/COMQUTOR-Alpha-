"""T4 round 28 content-support termination probe: the spawned worker's entry point (multiprocessing spawn, like the job
manager). Runs the real research pipeline (run_research_request) on the saved NVDA 10-02 trader output with its saved
sources; the fixed-response transport comes from this directory's sitecustomize."""
import json
import os
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
SOURCE_RUN = REPO / "outputs/runs/034a0a60-430e-41f8-8321-03a11389707a"
COPIED = ("raw_agent_outputs.json", "source_registry.json", "market_data_snapshot.json", "derived_inputs.json", "provider_response_audit.json")


def run(output_root: str, sqlite_path: str) -> None:
    for name in list(os.environ):
        if name.startswith(("COMQUTOR_WEEK2_", "COMQUTOR_RESEARCH_AGENT_", "COMQUTOR_DATABASE", "COMQUTOR_REQUIRE")):
            os.environ.pop(name)
    os.environ.update({"COMQUTOR_WEEK2_LLM_ENABLED": "true", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek", "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash",
                       "COMQUTOR_WEEK2_LLM_PROFILE": "t3_verified_20261008", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0", "COMQUTOR_WEEK2_LLM_MAX_CALLS": "1800",
                       "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45", "DEEPSEEK_API_KEY": "probe-not-a-key", "COMQUTOR_DATA_SANITY_ENABLED": "false"})
    from comqutor_alpha.api.routes_research import run_research_request
    from comqutor_alpha.classification_recovery import rebase_run_id
    from comqutor_alpha.storage.db.engine import build_engine
    from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

    repository = GraphPersistenceRepository(build_engine(f"sqlite:///{sqlite_path}"))
    repository.ensure_schema()

    def runner(payload, output_root):
        run_id = f"r28-cs-probe-{uuid.uuid4().hex[:8]}"
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True)
        for name in COPIED:
            if (SOURCE_RUN / name).is_file():
                data = rebase_run_id(json.loads((SOURCE_RUN / name).read_text(encoding="utf-8")), base_run_id=SOURCE_RUN.name, execution_id=run_id)
                if name == "raw_agent_outputs.json":
                    data["agent_outputs"] = [o for o in data["agent_outputs"] if o.get("agent") == "trader"]
                (run_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        meta = json.loads((SOURCE_RUN / "metadata.json").read_text(encoding="utf-8"))
        (run_dir / "metadata.json").write_text(json.dumps({**{k: meta[k] for k in ("ticker", "analysis_date") if k in meta}, "run_id": run_id,
                                                           "selected_analysts": ["trader"], "output_version": "week1a.v1",
                                                           "source": "round 28 content-support termination probe"}), encoding="utf-8")
        return str(run_dir)

    run_research_request({"ticker": "NVDA"}, runner=runner, output_root=output_root, graph_repository=repository)
