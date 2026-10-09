# v0.2 Alpha Final Adjudication Packet — Manifest

**Status: `PACKET_FROZEN_AWAITING_EXTERNAL_ADJUDICATION`**

| Field | Value |
|---|---|
| Packet path | `docs/audit_artifacts/v0_2_alpha_final_adjudication_packet.json` |
| Packet SHA256 | `64e7f2ca635a472fd4403f6419b43ca54461cd5306bfebe789fffb834f323c5d` |
| Sample count | 150 |

## Membership Provenance

Direct 1:1 materialization of the frozen `final_independent_set` (from `v0_2_new_alpha_holdout_split.json`, Day 4E), ordered by `final_sample_number`, with only the four blank adjudication fields added. No sample was added, removed, or reordered relative to the frozen split. Source final-set content hash, verified unchanged before packet creation: `a7c84445247f0ce0fdf187e6e73d62c04eb82e64557c40a98704a49bcd4bf70c`.

## Candidate 3 Freeze Hashes (verified unchanged this task)

| Prompt | SHA256 |
|---|---|
| Classifier (`week2.alpha_classifier.v6`) | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` |
| Batch (`week2.alpha_classifier_batch.v4`) | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |

## Immutability

This packet must not be modified after this hash was computed. Any future correction requires a new packet version, never an edit in place.
