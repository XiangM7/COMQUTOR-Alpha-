import json

import pytest

from comqutor_alpha.storage.file_store import (
    append_jsonl_record,
    list_runs,
    load_json_record,
    load_json_record_if_exists,
    resolve_output_root,
    run_dir_for,
    save_json_record,
    validate_artifact_filename,
    validate_artifact_path,
    validate_run_id_for_path,
)


def test_validate_run_id_for_path_accepts_uuid_like_run_id():
    run_id = "7eb4ad1b-c728-46fd-92a5-96210b35408d"

    assert validate_run_id_for_path(run_id) == run_id


@pytest.mark.parametrize(
    "run_id",
    ["../secret", "abc/def", "abc\\def", "", "/etc/passwd", "/", "C:\\Windows\\System32"],
)
def test_validate_run_id_for_path_rejects_unsafe_values(run_id):
    with pytest.raises(ValueError):
        validate_run_id_for_path(run_id)


def test_save_json_record_and_load_json_record_round_trip(tmp_path):
    save_json_record("run_1", "metadata.json", {"ticker": "NVDA"}, output_root=tmp_path)

    assert load_json_record("run_1", "metadata.json", output_root=tmp_path) == {
        "ticker": "NVDA"
    }


def test_validate_artifact_filename_rejects_unknown_filename():
    with pytest.raises(ValueError):
        validate_artifact_filename("secret.json")


def test_run_dir_for_stays_inside_output_root(tmp_path):
    root = tmp_path / "runs"
    run_dir = run_dir_for("run_1", output_root=root)

    assert run_dir.relative_to(root.resolve())


def test_saved_json_is_utf8_json(tmp_path):
    path = save_json_record("run_2", "metadata.json", {"text": "英伟达"}, output_root=tmp_path)

    assert json.loads(path.read_text(encoding="utf-8"))["text"] == "英伟达"


def test_list_runs_returns_only_valid_run_id_directories(tmp_path):
    (tmp_path / "valid_run-1").mkdir()
    (tmp_path / "bad.name").mkdir()
    (tmp_path / "with space").mkdir()
    (tmp_path / "not_a_dir").write_text("x", encoding="utf-8")

    assert list_runs(output_root=tmp_path) == ["valid_run-1"]


def test_load_json_record_if_exists_returns_empty_dict_for_missing_artifact(tmp_path):
    (tmp_path / "run_1").mkdir()

    assert load_json_record_if_exists("run_1", "metadata.json", output_root=tmp_path) == {}


def test_resolve_output_root_uses_explicit_output_root(tmp_path):
    root = tmp_path / "runs"

    assert resolve_output_root(root) == root.resolve()


def test_append_jsonl_record_writes_allowlisted_error_log(tmp_path):
    path = append_jsonl_record(
        "run_1",
        "error_logs/structured_output_adapter_errors.jsonl",
        {"error_code": "EMPTY_RAW_OUTPUT"},
        output_root=tmp_path,
    )

    assert path.relative_to((tmp_path / "run_1").resolve())
    assert '"EMPTY_RAW_OUTPUT"' in path.read_text(encoding="utf-8")


def test_validate_artifact_path_rejects_unallowlisted_subpaths():
    with pytest.raises(ValueError):
        validate_artifact_path("../error_logs/structured_output_adapter_errors.jsonl")

    with pytest.raises(ValueError):
        validate_artifact_path("error_logs/secret.jsonl")


@pytest.mark.parametrize("filename", ["alpha_matches.json", "extracted_structures.json"])
def test_week2_artifacts_can_be_saved_and_loaded(tmp_path, filename):
    save_json_record("run_1", filename, {"schema_version": "week2.v1"}, output_root=tmp_path)

    assert load_json_record("run_1", filename, output_root=tmp_path) == {
        "schema_version": "week2.v1"
    }


def test_unallowlisted_artifact_filename_is_rejected_by_save(tmp_path):
    with pytest.raises(ValueError):
        save_json_record("run_1", "arbitrary_secret.json", {"a": 1}, output_root=tmp_path)
