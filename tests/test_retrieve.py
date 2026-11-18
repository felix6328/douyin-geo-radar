from geolab.corpus import TARGET_ID, corpus_for
from geolab.retrieve import Retriever


def test_keyword_stuffing_not_worse_on_keyword_query():
    q = "通勤用的头戴降噪耳机有什么推荐？"
    r_base = Retriever(corpus_for("baseline"))
    r_stuff = Retriever(corpus_for("keyword_stuffing"))
    rb, _ = r_base.rank_of(q, TARGET_ID)
    rs, _ = r_stuff.rank_of(q, TARGET_ID)
    assert rb is not None and rs is not None
    # stuffing is designed to contain query keywords; it should not rank worse
    assert rs <= rb


def test_top_k_deterministic():
    docs = corpus_for("statistics")
    a = Retriever(docs).search("开启降噪以后还能用多久？", top_k=4)
    b = Retriever(docs).search("开启降噪以后还能用多久？", top_k=4)
    assert [d.doc_id for d, _, _ in a] == [d.doc_id for d, _, _ in b]
    assert len(a) == 4
