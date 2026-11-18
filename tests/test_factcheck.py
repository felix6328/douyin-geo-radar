from geolab.corpus import STRATEGIES, STRATEGY_ORDER
from geolab.factcheck import factcheck_target_text, factcheck_all_variants


def test_all_authored_variants_pass():
    results = factcheck_all_variants()
    failed = {k: v.violations for k, v in results.items() if not v.ok}
    assert failed == {}, failed
    assert list(results) == list(STRATEGIES)
    assert "keyword_stuffing" in STRATEGY_ORDER


def test_rejects_fabricated_award_and_number():
    r = factcheck_target_text("北屿获得红点奖，降噪高达 50 dB，官方售价 799 元。")
    assert not r.ok
    kinds = ",".join(r.violations)
    assert "红点" in kinds or "forbidden" in kinds
    assert "50" in kinds or "undeclared" in kinds


def test_rejects_competitor_on_target_page():
    r = factcheck_target_text("北屿 Nova Air 官方售价 799 元，比澄声更轻。")
    assert not r.ok
    assert any("competitor" in v for v in r.violations)
