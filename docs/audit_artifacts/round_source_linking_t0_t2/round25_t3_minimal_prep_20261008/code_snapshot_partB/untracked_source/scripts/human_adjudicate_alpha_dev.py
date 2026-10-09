"""Operator-only interactive CLI for HUMAN Gold-label adjudication of the
100-sample new Alpha development set (docs/audit_artifacts/v0_2_alpha_dev_adjudication_packet.json).

This script is an INPUT TOOL ONLY. It never generates, suggests, recommends,
infers, ranks, or auto-fills an expected Alpha label. Every label, confidence,
ambiguity flag, and reason comes exclusively from operator keyboard input.

It never reads, references, or displays any COMQUTOR prediction, Alpha mapper
output, model confidence, Provider output, historical expected label, or
Candidate 1/2 result. It contains no code path that reads the sealed 150-sample
RESERVED_FINAL_INDEPENDENT_SET or v0_2_alpha_final_holdout_sealed_manifest.json.

Usage:
    python3 scripts/human_adjudicate_alpha_dev.py --status
    python3 scripts/human_adjudicate_alpha_dev.py --resume
    python3 scripts/human_adjudicate_alpha_dev.py --sample 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

PACKET_PATH = "docs/audit_artifacts/v0_2_alpha_dev_adjudication_packet.json"
LABELS_PATH = "docs/audit_artifacts/v0_2_alpha_dev_human_labels.json"
QUEUE_PATH = "docs/audit_artifacts/v0_2_alpha_dev_review_queue.json"

CONFIDENCE_VALUES = ("HIGH", "MEDIUM", "LOW")
AMBIGUITY_VALUES = ("CLEAR", "AMBIGUOUS", "EXCLUDE")


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_save_json(path: str, data: dict) -> None:
    tmp_path = f"{path}.tmp{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, path)


def valid_expected_labels(packet: dict) -> set[str]:
    ids = {t["alpha_id"] for t in packet["taxonomy_reference"]}
    ids.add("NONE")
    return ids


def sample_number_from_id(sample_id: str) -> int:
    # sample_id format: "nh-dev-NNN"
    return int(sample_id.rsplit("-", 1)[-1])


def find_sample(packet: dict, sample_id: str) -> dict:
    for s in packet["samples"]:
        if s["sample_id"] == sample_id:
            return s
    raise KeyError(sample_id)


def find_label_entry(labels_doc: dict, sample_id: str) -> dict:
    for entry in labels_doc["labels"]:
        if entry["sample_id"] == sample_id:
            return entry
    raise KeyError(sample_id)


def display_sample(sample: dict, packet: dict, index: int, total: int) -> None:
    print("=" * 72)
    print(f"Progress: sample {index} / {total}")
    print(f"Blinded sample ID: {sample['sample_id']}")
    print(f"Ticker: {sample['ticker']}")
    print("-" * 72)
    print(f"Claim:    {sample['claim']}")
    print(f"Evidence: {sample['evidence']}")
    print("-" * 72)
    print("Existing Alpha taxonomy reference (authoritative, unchanged):")
    for t in packet["taxonomy_reference"]:
        print(f"  {t['alpha_id']:6s} {t['name_en']:28s} {t['core_thesis']}")
    print("  NONE   (no single Alpha is materially engaged)")
    print("-" * 72)
    print(
        "Rubric reminder: label only what the claim/evidence text itself materially\n"
        "supports (see docs/audit_artifacts/v0_2_alpha_human_adjudication_rubric.md).\n"
        "A bare keyword/topic mention is not sufficient. Use NONE when no single\n"
        "Alpha's own mechanism is engaged. Use AMBIGUOUS/EXCLUDE rather than guessing."
    )
    print("=" * 72)


def display_existing_label(entry: dict) -> None:
    print("This sample already has a HUMAN-entered adjudication:")
    print(f"  expected_label:     {entry['expected_label']}")
    print(f"  confidence:         {entry['confidence']}")
    print(f"  ambiguity_flag:     {entry['ambiguity_flag']}")
    print(f"  adjudication_reason:{entry['adjudication_reason']}")


def prompt_ambiguity_flag() -> str:
    while True:
        raw = input(f"ambiguity_flag {AMBIGUITY_VALUES} (required): ").strip().upper()
        if raw in AMBIGUITY_VALUES:
            return raw
        print(f"Invalid value. Must be one of {AMBIGUITY_VALUES}.")


def prompt_expected_label(valid_labels: set[str], required: bool) -> Optional[str]:
    hint = "required" if required else "leave blank if EXCLUDE"
    while True:
        raw = input(f"expected_label ({hint}): ").strip().upper()
        if not raw:
            if required:
                print("expected_label is required for this ambiguity_flag.")
                continue
            return None
        if raw in valid_labels:
            return raw
        print(f"Invalid label '{raw}'. Must be one of the taxonomy IDs shown above, or NONE.")


def prompt_confidence(required: bool) -> Optional[str]:
    hint = "required" if required else "optional"
    while True:
        raw = input(f"confidence {CONFIDENCE_VALUES} ({hint}): ").strip().upper()
        if not raw:
            if required:
                print("confidence is required.")
                continue
            return None
        if raw in CONFIDENCE_VALUES:
            return raw
        print(f"Invalid value. Must be one of {CONFIDENCE_VALUES}.")


def prompt_reason() -> str:
    while True:
        raw = input("adjudication_reason (required, free text): ").strip()
        if raw:
            return raw
        print("adjudication_reason is required, including for NONE and EXCLUDE.")


def collect_human_adjudication(valid_labels: set[str]) -> dict:
    """Collects all four fields from operator keyboard input only. Never
    generates or defaults a label."""
    ambiguity_flag = prompt_ambiguity_flag()
    is_exclude = ambiguity_flag == "EXCLUDE"
    expected_label = prompt_expected_label(valid_labels, required=not is_exclude)
    confidence = prompt_confidence(required=not is_exclude)
    adjudication_reason = prompt_reason()
    return {
        "expected_label": expected_label,
        "confidence": confidence,
        "ambiguity_flag": ambiguity_flag,
        "adjudication_reason": adjudication_reason,
    }


def rebuild_review_queue(labels_doc: dict) -> dict:
    """Derived ONLY from operator-entered fields already stored in the labels
    file. Never classifies ambiguity itself."""
    queue = []
    for entry in labels_doc["labels"]:
        if not entry["adjudicated"]:
            continue
        flagged = entry["ambiguity_flag"] in ("AMBIGUOUS", "EXCLUDE") or entry["confidence"] == "LOW"
        if flagged:
            queue.append(
                {
                    "sample_id": entry["sample_id"],
                    "ticker": entry["ticker"],
                    "claim_id": entry["claim_id"],
                    "expected_label": entry["expected_label"],
                    "confidence": entry["confidence"],
                    "ambiguity_flag": entry["ambiguity_flag"],
                    "adjudication_reason": entry["adjudication_reason"],
                }
            )
    return {
        "schema_version": "alpha_dev_review_queue.v1",
        "dataset_version": labels_doc["dataset_version"],
        "purpose": (
            "Holds only samples flagged AMBIGUOUS, LOW confidence, or EXCLUDE during "
            "human adjudication of the development set. Derived solely from "
            "operator-entered fields in v0_2_alpha_dev_human_labels.json."
        ),
        "status": "AWAITING_HUMAN_ADJUDICATION" if not queue else "CONTAINS_FLAGGED_SAMPLES",
        "queue_count": len(queue),
        "queue": queue,
    }


def apply_adjudication(labels_doc: dict, sample_id: str, result: dict) -> None:
    entry = find_label_entry(labels_doc, sample_id)
    entry.update(result)
    entry["adjudicated"] = True
    labels_doc["labels_completed"] = sum(1 for e in labels_doc["labels"] if e["adjudicated"])
    if labels_doc["labels_completed"] == len(labels_doc["labels"]):
        labels_doc["status"] = "ALL_SLOTS_ADJUDICATED_PENDING_QUEUE_RESOLUTION"
    else:
        labels_doc["status"] = "AWAITING_HUMAN_ADJUDICATION"


def status_counts(labels_doc: dict, queue_doc: dict) -> dict:
    entries = labels_doc["labels"]
    total = len(entries)
    labeled = sum(1 for e in entries if e["adjudicated"])
    unlabeled = total - labeled
    counts = {v: 0 for v in AMBIGUITY_VALUES}
    conf_counts = {v: 0 for v in CONFIDENCE_VALUES}
    for e in entries:
        if e["adjudicated"]:
            if e["ambiguity_flag"] in counts:
                counts[e["ambiguity_flag"]] += 1
            if e["confidence"] in conf_counts:
                conf_counts[e["confidence"]] += 1
    ready_to_freeze = labeled == total and queue_doc["queue_count"] == 0
    return {
        "total": total,
        "labeled": labeled,
        "unlabeled": unlabeled,
        "CLEAR": counts["CLEAR"],
        "AMBIGUOUS": counts["AMBIGUOUS"],
        "EXCLUDE": counts["EXCLUDE"],
        "HIGH": conf_counts["HIGH"],
        "MEDIUM": conf_counts["MEDIUM"],
        "LOW": conf_counts["LOW"],
        "review_queue_size": queue_doc["queue_count"],
        "READY_TO_FREEZE_GOLD": "YES" if ready_to_freeze else "NO",
    }


def cmd_status(packet_path: str, labels_path: str, queue_path: str) -> None:
    labels_doc = load_json(labels_path)
    queue_doc = load_json(queue_path) if os.path.exists(queue_path) else rebuild_review_queue(labels_doc)
    s = status_counts(labels_doc, queue_doc)
    print(f"total = {s['total']}")
    print(f"labeled = {s['labeled']}")
    print(f"unlabeled = {s['unlabeled']}")
    print(f"CLEAR = {s['CLEAR']}")
    print(f"AMBIGUOUS = {s['AMBIGUOUS']}")
    print(f"EXCLUDE = {s['EXCLUDE']}")
    print(f"HIGH = {s['HIGH']}")
    print(f"MEDIUM = {s['MEDIUM']}")
    print(f"LOW = {s['LOW']}")
    print(f"review_queue_size = {s['review_queue_size']}")
    print(f"READY_TO_FREEZE_GOLD = {s['READY_TO_FREEZE_GOLD']}")


def cmd_resume(packet_path: str, labels_path: str, queue_path: str) -> None:
    packet = load_json(packet_path)
    labels_doc = load_json(labels_path)
    valid_labels = valid_expected_labels(packet)
    total = len(packet["samples"])
    unlabeled_ids = [e["sample_id"] for e in labels_doc["labels"] if not e["adjudicated"]]
    if not unlabeled_ids:
        print("All 100 development slots already have a HUMAN-entered adjudication.")
        print("Use --status to see review-queue / READY_TO_FREEZE_GOLD, or --sample N to revisit one.")
        return
    for sample_id in unlabeled_ids:
        sample = find_sample(packet, sample_id)
        idx = sample_number_from_id(sample_id)
        display_sample(sample, packet, idx, total)
        try:
            result = collect_human_adjudication(valid_labels)
        except (EOFError, KeyboardInterrupt):
            print("\nSession paused. Progress already saved through the previous sample.")
            print("Re-run with --resume to continue from the next unlabeled sample.")
            return
        apply_adjudication(labels_doc, sample_id, result)
        atomic_save_json(labels_path, labels_doc)
        queue_doc = rebuild_review_queue(labels_doc)
        atomic_save_json(queue_path, queue_doc)
        print(f"Saved. ({labels_doc['labels_completed']} / {total} complete)\n")
        cont = input("Press Enter to continue, or type 'q' to stop here: ").strip().lower()
        if cont == "q":
            print("Stopped. Re-run with --resume to continue.")
            return
    print("All development samples now have a HUMAN-entered adjudication.")


def cmd_sample(packet_path: str, labels_path: str, queue_path: str, number: int) -> None:
    packet = load_json(packet_path)
    labels_doc = load_json(labels_path)
    valid_labels = valid_expected_labels(packet)
    total = len(packet["samples"])
    sample_id = f"nh-dev-{number:03d}"
    try:
        sample = find_sample(packet, sample_id)
        entry = find_label_entry(labels_doc, sample_id)
    except KeyError:
        print(f"No such development sample: {sample_id} (valid range 1-{total}).")
        return
    display_sample(sample, packet, number, total)
    if entry["adjudicated"]:
        display_existing_label(entry)
        confirm = input("Overwrite this existing HUMAN-entered adjudication? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("No change made.")
            return
    try:
        result = collect_human_adjudication(valid_labels)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No change made.")
        return
    apply_adjudication(labels_doc, sample_id, result)
    atomic_save_json(labels_path, labels_doc)
    queue_doc = rebuild_review_queue(labels_doc)
    atomic_save_json(queue_path, queue_doc)
    print(f"Saved sample {sample_id}.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator-only HUMAN adjudication CLI for the 100-sample Alpha development set."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--resume", action="store_true", help="Continue from the first unlabeled sample.")
    group.add_argument("--sample", type=int, metavar="N", help="Revisit development sample N (1-100).")
    group.add_argument("--status", action="store_true", help="Print progress counts only. No prompts.")
    parser.add_argument("--packet", default=PACKET_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--labels", default=LABELS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--queue", default=QUEUE_PATH, help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.status:
        cmd_status(args.packet, args.labels, args.queue)
    elif args.resume:
        cmd_resume(args.packet, args.labels, args.queue)
    elif args.sample is not None:
        cmd_sample(args.packet, args.labels, args.queue, args.sample)
    return 0


if __name__ == "__main__":
    sys.exit(main())
