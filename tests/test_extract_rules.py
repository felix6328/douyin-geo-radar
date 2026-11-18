from georadar.brands import Brand, extract_mentions, load_dictionary, mention_order


def _b(**kw):
    aliases = kw.pop("aliases")
    return Brand(aliases=aliases, category=kw.pop("category", "headphones"), **kw)


def test_longest_alias_wins():
    brands = [
        _b(id="apple", name="苹果", aliases=["AirPods Pro", "AirPods", "苹果耳机"]),
    ]
    text = "可以看 AirPods Pro，普通 AirPods 也行。"
    ms = extract_mentions(text, brands)
    assert [m.alias for m in ms] == ["AirPods Pro", "AirPods"]


def test_apple_fruit_not_counted():
    brands = [
        _b(
            id="apple_brand",
            merge_into="apple",
            name="苹果",
            aliases=["苹果"],
            require_any_nearby=["耳机", "AirPods", "降噪"],
            exclusion_substrings=["苹果味", "苹果醋"],
        )
    ]
    assert extract_mentions("我想喝苹果醋，不想买耳机。", brands) == []
    assert extract_mentions("苹果味的糖果很好吃。", brands) == []
    ms = extract_mentions("苹果的降噪耳机口碑不错。", brands)
    assert len(ms) == 1 and ms[0].brand_id == "apple"


def test_li_auto_not_ideal():
    brands = [
        _b(
            id="li_generic",
            merge_into="li",
            name="理想",
            category="nev",
            aliases=["理想"],
            require_any_nearby=["汽车", "L9", "车", "增程"],
        ),
        _b(id="li", name="理想", category="nev", aliases=["理想汽车", "理想L9"]),
    ]
    assert extract_mentions("这是一个理想的方案。", brands) == []
    ms = extract_mentions("家里有小孩可以看看理想L9。", brands)
    assert mention_order(ms) == ["li"]


def test_dictionary_loads_and_skincare_winona():
    d = load_dictionary()
    assert set(d) == {"skincare", "headphones", "nev", "coffee", "travel"}
    ms = extract_mentions("敏感肌很多人会提到薇诺娜和理肤泉。", d["skincare"], category="skincare")
    ids = mention_order(ms)
    assert "winona" in ids and "larocheposay" in ids


def test_exclusion_and_nearby_xiaomi_food():
    d = load_dictionary()
    ms = extract_mentions("今晚煮小米粥。", d["headphones"], category="headphones")
    assert ms == []
    ms = extract_mentions("小米的蓝牙耳机值得看。", d["headphones"], category="headphones")
    assert mention_order(ms) == ["xiaomi"]
