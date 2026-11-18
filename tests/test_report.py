from geolab.report import paired_effect, cite_given_retrieved


def _row(qid, strategy, cite, model="m", seed=1, in_topk=True):
    return {
        "query_id": qid,
        "strategy": strategy,
        "model": model,
        "seed": seed,
        "cite_rate": cite,
        "target_in_topk": in_topk,
    }


def test_paired_effect_baseline_is_zero():
    rows = [
        _row("q1", "baseline", 1.0, seed=1),
        _row("q1", "baseline", 0.0, seed=2),
        _row("q1", "structured_faq", 1.0, seed=1),
        _row("q1", "structured_faq", 1.0, seed=2),
        _row("q2", "baseline", 0.0, seed=1),
        _row("q2", "baseline", 0.0, seed=2),
        _row("q2", "structured_faq", 1.0, seed=1),
        _row("q2", "structured_faq", 1.0, seed=2),
    ]
    base = paired_effect(rows, "baseline", "cite_rate")
    assert base["mean"] == 0.0
    assert base["excludes_zero"] is False
    faq = paired_effect(rows, "structured_faq", "cite_rate")
    # q1: (1.0 - 0.5) = 0.5; q2: (1.0 - 0.0) = 1.0; mean 0.75
    assert abs(faq["mean"] - 0.75) < 1e-12
    assert faq["excludes_zero"] is True
    assert faq["mean"] > 0


def test_cite_given_retrieved_ignores_not_retrieved():
    rows = [
        _row("q1", "baseline", 1.0, in_topk=True),
        _row("q2", "baseline", 0.0, in_topk=False),
    ]
    out = {r["strategy"]: r for r in cite_given_retrieved(rows)}
    assert out["baseline"]["n_questions"] == 1
    assert out["baseline"]["cite_rate"]["mean"] == 1.0
