import math

from geolab.corpus import Document, TARGET_ID
from geolab.pawc import impressions, split_sentences, word_len


def test_pawc_formula_single_citation():
    docs = [
        Document(TARGET_ID, "北屿", "北屿", "x", "target"),
        Document("other", "澄声", "澄声", "y", "competitor"),
    ]
    # two sentences, first cites target, second cites other; equal length
    ans = "北屿续航很长[beiyu_nova_air]。澄声更贵一些[other]。"
    imp = impressions(ans, docs, numbered=[TARGET_ID, "other"])
    sents = split_sentences(ans)
    assert len(sents) == 2
    w1, w2 = word_len(sents[0]), word_len(sents[1])
    denom = w1 + w2
    assert abs(imp[TARGET_ID].imp_wc - w1 / denom) < 1e-9
    expected_pwc = (w1 * math.exp(-1 / 2)) / denom
    assert abs(imp[TARGET_ID].imp_pwc - expected_pwc) < 1e-9
    assert imp[TARGET_ID].first_cite_pos == 1
    assert imp[TARGET_ID].mentioned_brand is True


def test_shared_credit_when_two_cites():
    docs = [
        Document(TARGET_ID, "t", "北屿", "x", "target"),
        Document("other", "o", "澄声", "y", "competitor"),
    ]
    ans = "两边都提到了。[beiyu_nova_air][other]"
    imp = impressions(ans, docs)
    # only one sentence, shared equally, so each Imp_wc = 0.5
    assert abs(imp[TARGET_ID].imp_wc - 0.5) < 1e-9
    assert abs(imp["other"].imp_wc - 0.5) < 1e-9


def test_brand_mention_is_not_a_citation():
    docs = [Document(TARGET_ID, "t", "北屿", "x", "target")]
    ans = "我觉得北屿还可以，但没有标注来源。"
    imp = impressions(ans, docs)
    assert imp[TARGET_ID].imp_wc == 0.0
    assert imp[TARGET_ID].mentioned_brand is True
    assert imp[TARGET_ID].n_cited_sentences == 0
