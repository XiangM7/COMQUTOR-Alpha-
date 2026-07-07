from comqutor_alpha.alpha_library.alpha_loader import build_keyword_index, load_alpha_taxonomy


def test_loader_returns_mvp_10_and_required_conflicts():
    taxonomy = load_alpha_taxonomy()
    assert len(taxonomy) == 10
    assert "A101" in taxonomy
    assert "A304" in taxonomy

    conflicts = {
        (alpha.alpha_id, conflict.alpha_id)
        for alpha in taxonomy.values()
        for conflict in alpha.conflict_alphas
    }
    for left, right in (
        ("A101", "A304"),
        ("A301", "A304"),
        ("A001", "A501"),
        ("A003", "A501"),
        ("A601", "A304"),
        ("A601", "A501"),
    ):
        assert (left, right) in conflicts
        assert (right, left) in conflicts


def test_keyword_index_contains_useful_terms():
    index = build_keyword_index(load_alpha_taxonomy())
    text = " ".join(index)
    for keyword in ("ai", "gpu", "valuation", "recession", "liquidity"):
        assert keyword in text

