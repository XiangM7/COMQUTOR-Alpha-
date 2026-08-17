from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.errors import RecorderIntegrityError
from comqutor_alpha.llm_runtime.recorder import SEMANTIC_CALLS_FILENAME, SemanticCallRecorder
from tests.llm_runtime.fakes import make_record


def test_ordered_append_read_count_and_close(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record())
    recorder.append(make_record(call_id="call-1", call_sequence=1, task="alpha_classifier"))

    records = recorder.read_all()
    assert [record["call_sequence"] for record in records] == [0, 1]
    assert recorder.record_count() == 2
    assert recorder.verify_integrity().valid
    assert recorder.calls_path == tmp_path / SEMANTIC_CALLS_FILENAME
    assert recorder.calls_path.read_bytes().endswith(b"\n")
    recorder.close()
    with pytest.raises(RecorderIntegrityError) as caught:
        recorder.append(make_record(call_id="call-2", call_sequence=2))
    assert caught.value.reason_code == "RECORDER_CLOSED"


def test_duplicate_call_id_is_rejected(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record())
    with pytest.raises(RecorderIntegrityError) as caught:
        recorder.append(make_record(call_sequence=1))
    assert caught.value.reason_code == "RECORDER_DUPLICATE_CALL_ID"


def test_non_monotonic_sequence_is_rejected(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record(call_sequence=3))
    with pytest.raises(RecorderIntegrityError) as caught:
        recorder.append(make_record(call_id="call-2", call_sequence=2))
    assert caught.value.reason_code == "RECORDER_SEQUENCE_NOT_MONOTONIC"


def test_wrong_run_id_is_rejected(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    with pytest.raises(RecorderIntegrityError) as caught:
        recorder.append(make_record(run_id="other-run"))
    assert caught.value.reason_code == "RECORDER_RUN_ID_MISMATCH"


def test_tail_corruption_is_detected(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record())
    with recorder.calls_path.open("ab") as handle:
        handle.write(b'{"partial":')
    with pytest.raises(RecorderIntegrityError) as caught:
        recorder.read_all()
    assert caught.value.reason_code == "RECORDER_TAIL_CORRUPTED"
    assert recorder.verify_integrity().reason_codes == ("RECORDER_TAIL_CORRUPTED",)


def test_middle_corruption_is_not_skipped(tmp_path: Path) -> None:
    calls_path = tmp_path / SEMANTIC_CALLS_FILENAME
    first = json.dumps(make_record()).encode()
    second = json.dumps(make_record(call_id="call-1", call_sequence=1)).encode()
    calls_path.write_bytes(first + b"\nnot-json\n" + second + b"\n")
    with pytest.raises(RecorderIntegrityError) as caught:
        SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    assert caught.value.reason_code == "RECORDER_MIDDLE_LINE_CORRUPTED"


def test_concurrent_calls_are_serialized_and_never_create_partial_lines(tmp_path: Path) -> None:
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def append_competing(index: int) -> None:
        barrier.wait()
        try:
            recorder.append(make_record(call_id=f"call-{index}", call_sequence=0))
            outcome = "accepted"
        except RecorderIntegrityError as exc:
            outcome = exc.reason_code
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=append_competing, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("accepted") == 1
    assert outcomes.count("RECORDER_SEQUENCE_NOT_MONOTONIC") == 7
    assert recorder.record_count() == 1
    assert recorder.verify_integrity().valid


def test_production_artifact_directories_are_forbidden() -> None:
    repository = Path(__file__).resolve().parents[2]
    for protected in (repository / "outputs/runs", repository / "outputs/replays"):
        with pytest.raises(ValueError, match="RECORDER_PROTECTED_OUTPUT_DIRECTORY_FORBIDDEN"):
            SemanticCallRecorder(run_id="run-test", output_directory=protected, mode="test")
