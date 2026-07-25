"""Entity Alpha Exposure Rubric Contract v1.

``exposure_rubric_contract_v1.yaml`` is the sole canonical source of truth
for the MVP-10-to-Rubric mapping, the four dimensions of each rubric, their
weights, the discrete score scale, and the impact semantics vocabulary.
Nothing here creates an entity Exposure Seed and nothing here is wired into
the research pipeline, the API, the frontend, Activation, or Conflict --
this package only freezes the contract and provides a strict loader,
validator, deterministic scorer, and semantic fingerprint.

Any future Seed, Exposure artifact, Exposure Engine, or UI must reference
this contract's ``schema_version``/``contract_version``/``taxonomy_version``/
``contract_fingerprint`` rather than redefining the rubric from a copied
constant.
"""

from comqutor_alpha.exposure.rubric_contract import (
    ExposureContractError,
    compute_contract_fingerprint,
    compute_structural_exposure,
    load_exposure_rubric_contract,
    validate_exposure_rubric_contract,
)

__all__ = [
    "ExposureContractError",
    "compute_contract_fingerprint",
    "compute_structural_exposure",
    "load_exposure_rubric_contract",
    "validate_exposure_rubric_contract",
]
