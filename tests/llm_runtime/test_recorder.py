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


def test_out_of_order_call_sequence_is_accepted_and_persist_sequence_reflects_append_order(
    tmp_path: Path,
) -> None:
    """2026-10-02 (concurrent-audit-loss incident fix): call_sequence
    reflects call-START order (assigned by the caller, e.g.
    SemanticRuntimeSession, well before a real Provider attempt even
    begins) -- under real concurrent dispatch, a later-started call can
    legitimately complete, and need to be appended, before an
    earlier-started one. A real NVDA run lost ~240 real, billed attempts'
    own audit records because the previous design rejected exactly this
    case as "RECORDER_SEQUENCE_NOT_MONOTONIC". The recorder must now accept
    an out-of-order call_sequence outright, and assign its own
    persist_sequence (true append order) instead."""
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    # call_sequence=3 started (and would normally complete) before
    # call_sequence=2 -- but call_sequence=2's own work finishes first and
    # is the one that actually reaches append() first.
    recorder.append(make_record(call_id="call-3", call_sequence=3))
    recorder.append(make_record(call_id="call-2", call_sequence=2))

    records = recorder.read_all()
    assert [r["call_id"] for r in records] == ["call-3", "call-2"]
    assert [r["call_sequence"] for r in records] == [3, 2]  # preserved as-is, never reordered
    assert [r["persist_sequence"] for r in records] == [0, 1]  # true append order, strictly increasing
    assert recorder.record_count() == 2
    assert recorder.verify_integrity().valid


def test_duplicate_call_sequence_across_different_calls_is_accepted(tmp_path: Path) -> None:
    """call_sequence is no longer used as a per-record uniqueness/ordering
    gate at all -- only call_id must be unique (see
    test_duplicate_call_id_is_rejected). Two different real calls that
    happen to carry the same call_sequence (which should not occur from the
    real SemanticRuntimeSession allocator, but is not this recorder's
    concern to police) must not be rejected on that basis alone."""
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    recorder.append(make_record(call_id="call-a", call_sequence=0))
    recorder.append(make_record(call_id="call-b", call_sequence=0))

    assert recorder.record_count() == 2
    assert recorder.verify_integrity().valid


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


def test_concurrent_calls_all_persist_with_strictly_increasing_persist_sequence(
    tmp_path: Path,
) -> None:
    """2026-10-02 (concurrent-audit-loss incident fix): this test previously
    asserted that 7 of 8 real, concurrently-completing calls were REJECTED
    (RECORDER_SEQUENCE_NOT_MONOTONIC) as if that were correct behavior --
    it encoded the exact bug that lost ~240 real, billed attempts' own
    audit records in a real NVDA run. Real concurrent dispatch (the Week2
    alpha_classifier stage's own default concurrency=4) means genuinely
    distinct calls legitimately race to append() at the same moment; every
    one of them is a real, already-billed Provider attempt and must be
    persisted, not dropped. Each thread uses its own distinct call_sequence
    (as the real SemanticRuntimeSession allocator would), assigned in
    thread-index order but with no guarantee of completing in that order --
    exactly the real-world condition this fix addresses."""
    recorder = SemanticCallRecorder(run_id="run-test", output_directory=tmp_path, mode="test")
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def append_competing(index: int) -> None:
        barrier.wait()
        try:
            recorder.append(make_record(call_id=f"call-{index}", call_sequence=index))
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

    assert outcomes.count("accepted") == 8  # every real, concurrently-completing attempt persists
    assert recorder.record_count() == 8
    assert recorder.verify_integrity().valid

    records = recorder.read_all()
    persist_sequences = [r["persist_sequence"] for r in records]
    assert persist_sequences == sorted(persist_sequences)  # strictly increasing by append order
    assert persist_sequences == list(range(8))  # no gaps, no duplicates
    assert {r["call_id"] for r in records} == {f"call-{i}" for i in range(8)}  # none lost


def test_production_artifact_directories_are_forbidden() -> None:
    repository = Path(__file__).resolve().parents[2]
    for protected in (repository / "outputs/runs", repository / "outputs/replays"):
        with pytest.raises(ValueError, match="RECORDER_PROTECTED_OUTPUT_DIRECTORY_FORBIDDEN"):
            SemanticCallRecorder(run_id="run-test", output_directory=protected, mode="test")
