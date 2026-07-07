from comqutor_alpha.api.routes_alpha_library import get_alpha_detail, get_alpha_library


EXPECTED_ALPHA_IDS = {
    "A001",
    "A003",
    "A101",
    "A102",
    "A103",
    "A201",
    "A301",
    "A304",
    "A501",
    "A601",
}


def _alpha_by_id(library, alpha_id):
    return next(alpha for alpha in library["alphas"] if alpha["alpha_id"] == alpha_id)


def test_get_alpha_library_returns_mvp_10():
    library = get_alpha_library()

    assert library["schema_version"] == "week1.alpha_library.v1"
    assert library["alpha_count"] == 10
    assert {alpha["alpha_id"] for alpha in library["alphas"]} == EXPECTED_ALPHA_IDS


def test_get_alpha_library_serializes_conflicts():
    library = get_alpha_library()

    a101 = _alpha_by_id(library, "A101")
    assert "A304" in {conflict["alpha_id"] for conflict in a101["conflict_alphas"]}

    a501 = _alpha_by_id(library, "A501")
    a501_conflicts = {conflict["alpha_id"] for conflict in a501["conflict_alphas"]}
    assert a501_conflicts & {"A001", "A003", "A601"}


def test_get_alpha_detail():
    detail = get_alpha_detail("A101")

    assert detail["alpha_id"] == "A101"
    assert detail["name_en"]
    assert isinstance(detail["keywords"], list)


def test_api_main_imports():
    import comqutor_alpha.api.main as api_main

    assert hasattr(api_main, "app")
