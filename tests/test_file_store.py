import json

import pytest

from comqutor_alpha.storage.file_store import (
    load_json_record,
    run_dir_for,
    save_json_record,
    validate_artifact_filename,
    validate_run_id_for_path,
)


def test_validate_run_id_for_path_accepts_uuid_like_run_id():
    run_id = "7eb4ad1b-c728-46fd-92a5-96210b35408d"

    assert validate_run_id_for_path(run_id) == run_id


@pytest.mark.parametrize("run_id", ["../secret", "abc/def", "abc\\def", ""])
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
