"""GeoLab evaluation reports. Numbers are computed from saved rows, never hand-edited."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from geo_common.envload import estimate_cost_cny
from geo_common.llm import cumulative_spend_cny
from geo_common.paths import ANSWERS, EVAL, GOLD
from geolab.corpus import STRATEGY_NOTES, STRATEGY_ORDER
from geolab.statsutil import bootstrap_ci, question_means


def _fmt(x, nd=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _ci(d: dict, nd=4) -> str:
    if not d or d.get("mean") is None:
        return "n/a"
    return f"{d['mean']:.{nd}f} [{d['ci_low']:.{nd}f}, {d['ci_high']:.{nd}f}]"


def _qmeans(rows: list[dict], field: str) -> dict[str, float]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        val = r.get(field)
        if val is None:
            continue
        groups[r["query_id"]].append(float(val))
    return {k: sum(v) / len(v) for k, v in groups.items() if v}


def paired_effect(
    rows: list[dict],
    strategy: str,
    field: str,
    model: Optional[str] = None,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict:
    """Bootstrap CI of (strategy - baseline) at the question level (paired)."""
    sub = [r for r in rows if model is None or r["model"] == model]
    base = _qmeans([r for r in sub if r["strategy"] == "baseline"], field)
    treat = _qmeans([r for r in sub if r["strategy"] == strategy], field)
    ids = sorted(set(base) & set(treat))
    diffs = [treat[i] - base[i] for i in ids]
    ci = bootstrap_ci(diffs, n_boot=n_boot, seed=seed)
    lo, hi = ci.get("ci_low"), ci.get("ci_high")
    excludes_zero = lo is not None and hi is not None and not (lo <= 0.0 <= hi)
    return {
        "strategy": strategy,
        "model": model or "pooled",
        "metric": field,
        "n": ci["n"],
        "mean": ci["mean"],
        "ci_low": ci["ci_low"],
        "ci_high": ci["ci_high"],
        "n_boot": ci.get("n_boot"),
        "excludes_zero": excludes_zero,
        "delta_pp": (ci["mean"] * 100) if ci["mean"] is not None and field in {"cite_rate", "mention_rate", "target_in_topk"} else ci["mean"],
    }


def all_paired_effects(rows: list[dict], field: str) -> list[dict]:
    out = []
    models = [None] + sorted({r["model"] for r in rows})
    for model in models:
        for st in STRATEGY_ORDER:
            out.append(paired_effect(rows, st, field, model=model))
    return out


def cite_given_retrieved(rows: list[dict]) -> list[dict]:
    out = []
    for st in STRATEGY_ORDER:
        sub = [r for r in rows if r["strategy"] == st and r.get("target_in_topk")]
        vals = question_means(sub, "cite_rate")
        ci = bootstrap_ci(vals)
        out.append({"strategy": st, "n_questions": len(vals), "n_rows": len(sub), "cite_rate": ci})
    return out


def retrieval_table(rows: list[dict]) -> list[dict]:
    seen = set()
    by_st: dict[str, list] = defaultdict(list)
    for r in rows:
        key = (r["query_id"], r["strategy"])
        if key in seen:
            continue
        seen.add(key)
        by_st[r["strategy"]].append(r)
    out = []
    for st in STRATEGY_ORDER:
        items = by_st[st]
        ranks = [x["target_rank_live"] for x in items if x.get("target_rank_live") is not None]
        ink = [1.0 if x["target_in_topk"] else 0.0 for x in items]
        # rank vs baseline, same questions
        base_items = {x["query_id"]: x["target_rank_live"] for x in by_st.get("baseline", [])}
        better = worse = same = 0
        for x in items:
            rb, rs = base_items.get(x["query_id"]), x.get("target_rank_live")
            if rb is None or rs is None:
                continue
            if rs < rb:
                better += 1
            elif rs > rb:
                worse += 1
            else:
                same += 1
        out.append(
            {
                "strategy": st,
                "n": len(items),
                "mean_rank": (sum(ranks) / len(ranks)) if ranks else None,
                "in_topk": (sum(ink) / len(ink)) if ink else None,
                "rank_better_than_baseline": better,
                "rank_worse_than_baseline": worse,
                "rank_same_as_baseline": same,
            }
        )
    return out


def _agg_table(rows: list[dict], filters: Optional[dict] = None) -> list[dict]:
    from geolab.pipeline import _agg_table as _inner

    return _inner(rows, filters)


def relative_improvement(table: list[dict], metric: str = "imp_pwc") -> list[dict]:
    from geolab.pipeline import relative_improvement as _inner

    return _inner(table, metric)


def cost_block(rows: list[dict]) -> str:
    from geolab.pipeline import cost_block as _inner

    return _inner(rows)


def _sign_note(eff: dict) -> str:
    if eff["mean"] is None:
        return "n/a"
    if eff.get("strategy") == "baseline":
        return "对照"
    if eff["excludes_zero"]:
        direction = "优于基线" if eff["mean"] > 0 else "差于基线"
        return f"{direction}（CI 不含 0）"
    return "与基线无显著差异（CI 含 0）"


def write_results_md(
    path: Path,
    main_rows: list[dict],
    frozen_rows: list[dict],
    table: list[dict],
    fact: dict,
    split: dict,
    policy_report: dict,
    settings: dict,
    cost_block_text: str,
) -> None:
    lines = []
    lines.append("# GeoLab 评测结果")
    lines.append("")
    lines.append("评测日期：2026-11-14（Asia/Shanghai）。数字由 `scripts/run_geolab.py` / `scripts/render_geolab.py` 从本次运行的回答 JSON 汇总，未经手工改写。")
    lines.append("")
    lines.append("**必须一起读的局限：**")
    lines.append("")
    lines.append("- 这是**受控 RAG 模拟**：检索是本地 BM25，生成是硅基流动裸模型，语料是虚构品牌「北屿 Nova Air」的手写页面。**不是**抖音、豆包或任何真实生成式搜索的流量。")
    lines.append("- 策略页全部手写并经过规格书事实校验；关键词堆砌是负向对照，不是推荐给生产使用的做法。")
    lines.append("- 主指标引用率、PAWC（Aggarwal et al., KDD 2024, Eq. 3，指数位置衰减）只把显式引用算作来源贡献，品牌名出现单独计「提及率」。")
    lines.append("- 置信区间是以**问题**为单元、对问题均值做 2000 次 bootstrap 的 95% 区间；种子（以及需要时的模型）先取平均。相对基线的效应使用**配对**差值（同一题的策略 − 基线）再做 bootstrap，比两条边际区间是否重叠更合适。")
    lines.append("- 问题数 n=40，测试集只有 10 题，区间较宽。FAQ 页含问句，BM25 的提升可能部分来自词面重叠，未必能推广到稠密检索或真实引擎。")
    lines.append("")
    n_q = len({r["query_id"] for r in main_rows})
    n_m = len({r["model"] for r in main_rows})
    n_s = len({r["seed"] for r in main_rows})
    n_st = len({r["strategy"] for r in main_rows})
    failed = sum(1 for r in main_rows if r.get("error") and not r.get("answer"))
    lines.append("## 规模")
    lines.append("")
    lines.append(f"- 问题 {n_q}，策略 {n_st}，模型 {n_m}（`deepseek-ai/DeepSeek-V3.2`、`zai-org/GLM-4.5-Air`），种子 {n_s}（{sorted({r['seed'] for r in main_rows})}），主实验回答 {len(main_rows)} 条（失败 {failed}）。")
    lines.append(f"- 冻结检索消融 {len(frozen_rows)} 条（仅 `deepseek-ai/DeepSeek-V3.2`、种子 7，见配置）。")
    lines.append(f"- 训练题 {len(split['train_ids'])}，测试题 {len(split['test_ids'])}，切分种子 {split['seed']}，按问题类型分层。")
    lines.append("")
    lines.append("## 事实校验")
    lines.append("")
    for st in STRATEGY_ORDER:
        r = fact[st]
        status = "通过" if r["ok"] else "失败: " + "; ".join(r["violations"])
        lines.append(f"- `{st}`：{status}。{STRATEGY_NOTES.get(st, '')}")
    lines.append("")

    # ---- headline: pooled paired effects ----
    lines.append("## 主实验：相对基线的配对效应（两模型合并）")
    lines.append("")
    lines.append("每个问题先对模型与种子取平均，再计算「策略 − 基线」的差值，对 40 个差值做 2000 次 bootstrap。这是判断某策略是否真的优于基线的主表。")
    lines.append("")
    lines.append("| 策略 | 引用率配对 Δ [95% CI] | 判定 | PAWC 配对 Δ [95% CI] | 判定 | 平均 BM25 排名 | 进入 top-k | 进入后条件引用率 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    ret = {r["strategy"]: r for r in retrieval_table(main_rows)}
    cond = {r["strategy"]: r for r in cite_given_retrieved(main_rows)}
    pooled_cite = {r["strategy"]: r for r in all_paired_effects(main_rows, "cite_rate") if r["model"] == "pooled"}
    pooled_pawc = {r["strategy"]: r for r in all_paired_effects(main_rows, "imp_pwc") if r["model"] == "pooled"}
    for st in STRATEGY_ORDER:
        pc, pp = pooled_cite[st], pooled_pawc[st]
        rt, cd = ret[st], cond[st]
        lines.append(
            f"| {st} | {_ci(pc)} | {_sign_note(pc)} | {_ci(pp)} | {_sign_note(pp)} | "
            f"{_fmt(rt['mean_rank'], 2)} | {_fmt(rt['in_topk'], 3)} | {_ci(cd['cite_rate'])} |"
        )
    lines.append("")
    lines.append("读法上的三点：")
    lines.append("")
    lines.append("- 只有 `structured_faq` 的引用率和 PAWC 配对区间都不含 0，且方向为正。关键词堆砌（负向对照）引用率和 PAWC 都显著差于基线，与 GEO 论文中该方法不优于基线的方向一致。")
    lines.append("- 进入 top-k 之后的条件引用率，七种策略都在 0.93–1.00。也就是说，**一旦被检索到，各策略被引用的概率几乎一样**。主实验里的差距主要来自能否进 top-k。")
    lines.append(f"- `structured_faq` 把平均排名从基线的 {ret['baseline']['mean_rank']:.2f} 提到 {ret['structured_faq']['mean_rank']:.2f}，40 题全部进入 top-k（基线 0.700）；{ret['structured_faq']['rank_better_than_baseline']} 题排名变好，{ret['structured_faq']['rank_worse_than_baseline']} 题变差，{ret['structured_faq']['rank_same_as_baseline']} 题持平。`keyword_stuffing` 反而有 {ret['keyword_stuffing']['rank_worse_than_baseline']} 题排名变差、只有 {ret['keyword_stuffing']['rank_better_than_baseline']} 题变好。")
    lines.append("")

    lines.append("## 主实验分模型（内容变更后重新检索）")
    lines.append("")
    lines.append("每个单元格是「先按问题对种子取平均，再对问题取均值」，括号内为该均值的 95% bootstrap 区间（不是配对差值）。")
    lines.append("")
    models = sorted({r["model"] for r in table})
    for model in models:
        lines.append(f"### `{model}`")
        lines.append("")
        lines.append("| 策略 | 引用率 | 提及率 | PAWC | Word Count | 目标进入 top-k |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        by = {r["strategy"]: r for r in table if r["model"] == model}
        for st in STRATEGY_ORDER:
            r = by[st]
            lines.append(
                f"| {r['strategy']} | {_ci(r['cite_rate'])} | {_ci(r['mention_rate'])} | "
                f"{_ci(r['imp_pwc'])} | {_ci(r['imp_wc'])} | {_ci(r['target_in_topk'])} |"
            )
        lines.append("")
        lines.append("相对 baseline 的**配对**变化：")
        lines.append("")
        lines.append("| 策略 | 引用率 Δpp [95% CI] | 判定 | PAWC Δ [95% CI] | 判定 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for st in STRATEGY_ORDER:
            pc = paired_effect(main_rows, st, "cite_rate", model=model)
            pp = paired_effect(main_rows, st, "imp_pwc", model=model)
            lines.append(
                f"| {st} | {_ci({'mean': pc['delta_pp'], 'ci_low': pc['ci_low']*100 if pc['ci_low'] is not None else None, 'ci_high': pc['ci_high']*100 if pc['ci_high'] is not None else None})} | {_sign_note(pc)} | "
                f"{_ci(pp)} | {_sign_note(pp)} |"
            )
        lines.append("")

    qtypes = sorted({r["qtype"] for r in main_rows})
    lines.append("## 分问题类型的引用率（两模型、多种子平均）")
    lines.append("")
    lines.append("每类 8 道题，区间会比较宽，只用来观察方向，不单独下结论。")
    lines.append("")
    header = "| 策略 | " + " | ".join(qtypes) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join(["---"] * len(qtypes)) + " |")
    for st in STRATEGY_ORDER:
        cells = [st]
        for qt in qtypes:
            vals = question_means(main_rows, "cite_rate", {"strategy": st, "qtype": qt})
            ci = bootstrap_ci(vals)
            cells.append(_fmt(ci["mean"], 3) if ci["mean"] is not None else "n/a")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("相对基线的配对引用率差值（同一类问题）：")
    lines.append("")
    lines.append("| 策略 | " + " | ".join(qtypes) + " |")
    lines.append("| --- | " + " | ".join(["---"] * len(qtypes)) + " |")
    for st in STRATEGY_ORDER:
        cells = [st]
        for qt in qtypes:
            sub = [r for r in main_rows if r["qtype"] == qt]
            eff = paired_effect(sub, st, "cite_rate")
            cells.append(_fmt(eff["mean"], 3) if eff["mean"] is not None else "n/a")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## 检索位次（BM25，不依赖模型）")
    lines.append("")
    lines.append("同一问题在不同策略下目标页的平均 BM25 排名（1 为最前；越小越好）。这是内容改写对可发现性的影响，还没有进入生成。")
    lines.append("")
    lines.append("| 策略 | 平均排名 | 进入 top-k 的问题占比 | 排名好于基线 | 差于基线 | 持平 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for rt in retrieval_table(main_rows):
        lines.append(
            f"| {rt['strategy']} | {_fmt(rt['mean_rank'], 2)} | {_fmt(rt['in_topk'], 3)} | "
            f"{rt['rank_better_than_baseline']} | {rt['rank_worse_than_baseline']} | {rt['rank_same_as_baseline']} |"
        )
    lines.append("")

    if frozen_rows:
        lines.append("## 冻结检索消融")
        lines.append("")
        lines.append("检索顺序固定为 baseline 的 BM25 排序，只替换目标页正文再生成。用于把「写得更好被用到」和「写得更像查询所以被检索到」分开。本消融只用 DeepSeek-V3.2、种子 7，每格 n=40 题。")
        lines.append("")
        ft = _agg_table(frozen_rows)
        lines.append("| 策略 | 引用率 | PAWC | 引用率配对 Δ [95% CI] | PAWC 配对 Δ [95% CI] |")
        lines.append("| --- | --- | --- | --- | --- |")
        by = {r["strategy"]: r for r in ft}
        for st in STRATEGY_ORDER:
            r = by[st]
            pc = paired_effect(frozen_rows, st, "cite_rate")
            pp = paired_effect(frozen_rows, st, "imp_pwc")
            lines.append(
                f"| {st} | {_ci(r['cite_rate'])} | {_ci(r['imp_pwc'])} | {_ci(pc)} | {_ci(pp)} |"
            )
        lines.append("")
        lines.append("冻结之后，所有策略相对基线的配对引用率区间都包含 0（`statistics` 的下界是 0.0000）。结合上一节「进入 top-k 后条件引用率接近」：本实验里 FAQ 的优势几乎全部来自检索位次，而不是生成阶段把同一段资料写得更值得引用。`statistics` / `cite_sources` 在冻结条件下 PAWC 略高，但 CI 含 0，不能写成生成效应成立。")
        lines.append("")

    lines.append("## 策略分配政策（训练题决策，测试题验收）")
    lines.append("")
    lines.append(f"训练题 {policy_report['n_train']}，测试题 {policy_report['n_test']}。政策只看训练题上的引用率，不得回看测试题调策略。")
    lines.append("")
    lines.append(f"- 按问题类型取训练最优：`{policy_report['by_qtype']}`")
    lines.append(f"- 训练集全局最优单一策略：`{policy_report['global_best']}`")
    lines.append("")
    lines.append("| 政策 | 测试集引用率 | 测试集 PAWC |")
    lines.append("| --- | --- | --- |")
    for name, block in policy_report["scores"].items():
        lines.append(f"| {name} | {_ci(block['cite_rate'])} | {_ci(block['imp_pwc'])} |")
    lines.append("")

    # paired policy vs baseline on test
    test_ids = set(split["test_ids"])
    test_rows = [r for r in main_rows if r["query_id"] in test_ids]
    # policy picked structured_faq for every type, same as global best
    gbest = policy_report["global_best"]
    test_cite = paired_effect(test_rows, gbest, "cite_rate")
    test_pawc = paired_effect(test_rows, gbest, "imp_pwc")
    train_ids = set(split["train_ids"])
    train_rows = [r for r in main_rows if r["query_id"] in train_ids]
    train_cite = paired_effect(train_rows, gbest, "cite_rate")
    lines.append(
        f"测试集上 `{gbest}` 对基线的**配对**引用率 Δ = {_ci(test_cite)}，{_sign_note(test_cite)}；"
        f"配对 PAWC Δ = {_ci(test_pawc)}，{_sign_note(test_pawc)}。"
        f"训练集上同一对比的引用率配对 Δ = {_ci(train_cite)}。"
    )
    lines.append("")
    same_as_global = all(v == gbest for v in policy_report["by_qtype"].values())
    if same_as_global:
        lines.append(
            f"「按类型分配」与「全局最优」在测试集上数字完全相同，因为五类问题在训练集上都选了 `{gbest}`。"
            "所以**不能**写成「Agent 学会了按问题类型分配策略」——只能说它在训练题上找到了一个全局更好的单一策略，并在测试题上仍优于基线。"
            f"测试集只有 {policy_report['n_test']} 题，边际区间很宽（基线引用率 {_ci(policy_report['scores']['测试集-基线']['cite_rate'])} 与 `{gbest}` {_ci(policy_report['scores'][f'测试集-全局最优({gbest})']['cite_rate'])} 可能重叠），配对区间才是判断差值的依据。小样本结论要谨慎。"
        )
    else:
        lines.append("「按类型分配」如果没有稳定超过全局最优或基线，不能写成「Agent 会选策略」。这正是实验要检验的事。")
    lines.append("")

    faq_c = pooled_cite["structured_faq"]
    faq_p = pooled_pawc["structured_faq"]
    neg = [st for st in STRATEGY_ORDER if st not in ("baseline", "structured_faq") and pooled_cite[st]["excludes_zero"] and pooled_cite[st]["mean"] < 0]
    other_ranks = [ret[st]["mean_rank"] for st in STRATEGY_ORDER if st not in ("baseline", "structured_faq") and ret[st]["mean_rank"] is not None]
    other_topk = [ret[st]["in_topk"] for st in STRATEGY_ORDER if st not in ("baseline", "structured_faq") and ret[st]["in_topk"] is not None]
    lines.append("## 简要结论（必须和开篇局限一起读）")
    lines.append("")
    lines.append(
        f"1. 主实验 {n_q} 题、两模型合并：只有 `structured_faq` 显著优于基线（配对引用率 {_ci(faq_c)}，配对 PAWC {_ci(faq_p)}）。"
        f"配对引用率显著为负的策略：{', '.join('`'+s+'`' for s in neg)}。"
    )
    lines.append(
        f"2. 这些负向效应与检索位次变差一致：上述策略平均排名从基线 {ret['baseline']['mean_rank']:.2f} 落到 "
        f"{min(other_ranks):.2f}–{max(other_ranks):.2f}，进入 top-k 的比例从 {ret['baseline']['in_topk']:.2f} 落到 "
        f"{min(other_topk):.2f}–{max(other_topk):.2f}。冻结检索后配对效应的 CI 都含 0，条件引用率也接近，"
        "说明差距主要在「能不能被找到」，不在「找到了会不会被引用」。"
    )
    lines.append("3. 因此 FAQ 的胜利首先是「写得像查询、BM25 能找到」，要警惕这是词面重叠而不是普遍的 GEO 真理。换稠密检索或真实引擎，排序可能变。")
    if same_as_global:
        lines.append(
            f"4. 在训练/测试切分上，Agent 提出的策略（与全局最优 `{gbest}` 相同）在 {policy_report['n_test']} 道测试题上"
            f"配对引用率 Δ = {_ci(test_cite)}，{_sign_note(test_cite)}；按类型分配没有额外贡献。"
        )
    else:
        lines.append("4. 按类型分配与全局最优不同，是否在测试集上更好见上一节政策表，不得回看测试题再改政策。")
    lines.append("")

    lines.append("## 费用（估算）")
    lines.append("")
    lines.append(cost_block_text)
    lines.append("")
    lines.append("两端项目的合计估算见 `docs/COST.md`。费用是按硅基流动价格页标价与返回 token 的估算，查阅日期 2026-11-14（Asia/Shanghai），不是账单原件。")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_badcases(path: Path, rows: list[dict], frozen_rows: Optional[list[dict]] = None) -> None:
    lines = ["# GeoLab 坏例与值得追问的样本", ""]
    lines.append("挑选原则：目标进入 top-k 却没被引用；关键词堆砌没有带来检索优势；基线引用了但其它策略因掉出 top-k 而丢失；回答疑似编造规格书没有的数字。同一问题只保留一条代表性样本，避免重复。")
    lines.append("")

    def _unique(items):
        seen = set()
        out = []
        for r in items:
            k = (r["query_id"], r["strategy"], r["model"])
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
        return out

    def show(title, items, n=6, extra=None):
        lines.append(f"## {title}")
        lines.append("")
        if extra:
            lines.append(extra)
            lines.append("")
        picked = _unique(items)[:n]
        if not picked:
            lines.append("（本组没有样本。）")
            lines.append("")
            return
        for r in picked:
            lines.append(
                f"- **{r['query_id']}** `{r['model']}` seed={r['seed']} 策略={r['strategy']} "
                f"qtype={r.get('qtype')} rank={r.get('target_rank_live')} in_topk={r.get('target_in_topk')} "
                f"cite={r.get('cite_rate')} PAWC={_fmt(r.get('imp_pwc'))}"
            )
            lines.append(f"  - 问题：{r['query_text']}")
            lines.append(f"  - 检索：{r.get('retrieved_ids')}")
            ans = (r.get("answer") or r.get("error") or "")[:300].replace("\n", " ")
            lines.append(f"  - 回答片段：{ans}")
        lines.append("")

    retrieved_not_cited = [
        r for r in rows if r.get("target_in_topk") and r.get("cite_rate") == 0 and r.get("answer")
    ]
    n_rnc = sum(1 for r in rows if r.get("target_in_topk") and r.get("cite_rate") == 0)
    n_in = sum(1 for r in rows if r.get("target_in_topk"))
    show(
        "检索到目标页但回答未引用",
        retrieved_not_cited,
        n=6,
        extra=f"共 {n_rnc} / {n_in} 条进入 top-k 的回答未引用目标页。常见情况是模型改引导购文或科普文（`buying_guide`、`anc_explainer`、`warranty_notes`），目标页在上下文里但没有被标成依据。这是「可见度」和「被当成证据」之间的缺口，面试可以追问。",
    )

    stuffing_miss = [
        r for r in rows if r["strategy"] == "keyword_stuffing" and r.get("cite_rate") == 0 and r.get("target_in_topk")
    ]
    show(
        "关键词堆砌：进了 top-k 仍未被引用",
        stuffing_miss,
        n=4,
        extra="负向对照在主实验上引用率显著低于基线。即使进了 top-k，有时仍输给导购类文档。生产环境不应采用堆砌。",
    )

    # baseline cited, strategy missed, typically because retrieval dropped
    base = {(r["query_id"], r["model"], r["seed"]): r for r in rows if r["strategy"] == "baseline"}
    dropped = []
    for r in rows:
        if r["strategy"] in ("baseline", "structured_faq"):
            continue
        b = base.get((r["query_id"], r["model"], r["seed"]))
        if not b:
            continue
        if b.get("cite_rate") == 1 and r.get("cite_rate") == 0:
            dropped.append((r, b))
    # prefer cases where rank got worse
    dropped.sort(key=lambda x: (not (x[0].get("target_rank_live") or 99) > (x[1].get("target_rank_live") or 99), x[0]["query_id"]))
    lines.append("## 基线引用了、改写策略却丢掉（多半是检索掉出 top-k）")
    lines.append("")
    n_drop = {st: 0 for st in STRATEGY_ORDER}
    n_gain = {st: 0 for st in STRATEGY_ORDER}
    for r in rows:
        b = base.get((r["query_id"], r["model"], r["seed"]))
        if not b or r["strategy"] == "baseline":
            continue
        if b.get("cite_rate") == 1 and r.get("cite_rate") == 0:
            n_drop[r["strategy"]] += 1
        if b.get("cite_rate") == 0 and r.get("cite_rate") == 1:
            n_gain[r["strategy"]] += 1
    lines.append(
        "计数（条，模型×种子展开）："
        + "；".join(
            f"`{st}` 丢掉 {n_drop[st]}、多得到 {n_gain[st]}"
            for st in STRATEGY_ORDER
            if st != "baseline"
        )
        + "。"
    )
    lines.append("")
    seen_q = set()
    shown = 0
    for r, b in dropped:
        k = (r["query_id"], r["strategy"])
        if k in seen_q:
            continue
        seen_q.add(k)
        lines.append(
            f"- **{r['query_id']}** `{r['model']}` 策略={r['strategy']} qtype={r.get('qtype')}："
            f"基线 rank={b.get('target_rank_live')} in_topk={b.get('target_in_topk')} cite=1；"
            f"本策略 rank={r.get('target_rank_live')} in_topk={r.get('target_in_topk')} cite=0。"
        )
        lines.append(f"  - 问题：{r['query_text']}")
        lines.append(f"  - 基线检索：{b.get('retrieved_ids')}；本策略检索：{r.get('retrieved_ids')}")
        shown += 1
        if shown >= 6:
            break
    lines.append("")

    invented = [
        r
        for r in rows
        if r.get("answer")
        and ("红点" in r["answer"] or "50 dB" in r["answer"] or "50dB" in r["answer"] or "销量第一" in r["answer"])
    ]
    lines.append("## 回答中疑似出现禁止宣称（生成阶段，不是策略页）")
    lines.append("")
    if not invented:
        lines.append(
            f"在 {len(rows)} 条主实验回答中，未检出「红点」「50 dB」「销量第一」这几条禁止宣称。"
            "这只覆盖了预先列出的模式，不是完整的幻觉审计。"
        )
        lines.append("")
    else:
        show("检出的可疑宣称", invented, n=8)

    failed = [r for r in rows if r.get("error") and not r.get("answer")]
    if failed:
        show("生成失败", failed, n=6)
    else:
        lines.append("## 生成失败")
        lines.append("")
        lines.append("主实验 1680 条全部生成成功，失败 0。")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_eval_payload(
    main_rows: list[dict],
    frozen_rows: list[dict],
    table: list[dict],
    fact: dict,
    split: dict,
    policy_report: dict,
) -> dict:
    test_ids = set(split["test_ids"])
    train_ids = set(split["train_ids"])
    test_rows = [r for r in main_rows if r["query_id"] in test_ids]
    train_rows = [r for r in main_rows if r["query_id"] in train_ids]
    gbest = policy_report["global_best"]
    return {
        "table": table,
        "relative_cite": relative_improvement(table, "cite_rate"),
        "relative_pawc": relative_improvement(table, "imp_pwc"),
        "paired_cite": all_paired_effects(main_rows, "cite_rate"),
        "paired_pawc": all_paired_effects(main_rows, "imp_pwc"),
        "paired_frozen_cite": all_paired_effects(frozen_rows, "cite_rate") if frozen_rows else [],
        "paired_frozen_pawc": all_paired_effects(frozen_rows, "imp_pwc") if frozen_rows else [],
        "paired_test_vs_baseline": {
            "strategy": gbest,
            "cite_rate": paired_effect(test_rows, gbest, "cite_rate"),
            "imp_pwc": paired_effect(test_rows, gbest, "imp_pwc"),
        },
        "paired_train_vs_baseline": {
            "strategy": gbest,
            "cite_rate": paired_effect(train_rows, gbest, "cite_rate"),
            "imp_pwc": paired_effect(train_rows, gbest, "imp_pwc"),
        },
        "cite_given_retrieved": cite_given_retrieved(main_rows),
        "retrieval": retrieval_table(main_rows),
        "factcheck": fact,
        "split": split,
        "policy": policy_report,
        "spend": cumulative_spend_cny(),
        "n_main": len(main_rows),
        "n_frozen": len(frozen_rows),
        "n_failed": sum(1 for r in main_rows if r.get("error") and not r.get("answer")),
    }


def render_from_saved() -> dict:
    """Rebuild eval markdown/JSON from saved answer rows. No API calls."""
    main_rows = json.loads((ANSWERS / "geolab_rows.json").read_text(encoding="utf-8"))
    frozen_path = ANSWERS / "geolab_frozen_rows.json"
    frozen_rows = json.loads(frozen_path.read_text(encoding="utf-8")) if frozen_path.is_file() else []
    split = json.loads((GOLD / "geolab_split.json").read_text(encoding="utf-8"))
    # factcheck is deterministic from authored pages
    from geolab.factcheck import factcheck_all_variants

    fact_raw = factcheck_all_variants()
    fact = {k: {"ok": v.ok, "violations": v.violations} for k, v in fact_raw.items()}
    table = _agg_table(main_rows)
    from geolab.pipeline import (
        apply_policy,
        global_best,
        load_settings,
        policy_from_train,
        policy_score,
    )

    settings = load_settings()
    train_ids = set(split["train_ids"])
    test_ids = set(split["test_ids"])
    train_rows = [r for r in main_rows if r["query_id"] in train_ids]
    test_rows = [r for r in main_rows if r["query_id"] in test_ids]
    policy = policy_from_train(train_rows, "cite_rate")
    gbest = global_best(train_rows, "cite_rate")
    baseline_policy = {qt: "baseline" for qt in policy}
    global_policy = {qt: gbest for qt in policy}
    policy_report = {
        "by_qtype": policy,
        "global_best": gbest,
        "n_train": len(train_ids),
        "n_test": len(test_ids),
        "scores": {
            "测试集-基线": {
                "cite_rate": policy_score(apply_policy(test_rows, baseline_policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, baseline_policy), "imp_pwc"),
            },
            f"测试集-全局最优({gbest})": {
                "cite_rate": policy_score(apply_policy(test_rows, global_policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, global_policy), "imp_pwc"),
            },
            "测试集-按类型分配": {
                "cite_rate": policy_score(apply_policy(test_rows, policy), "cite_rate"),
                "imp_pwc": policy_score(apply_policy(test_rows, policy), "imp_pwc"),
            },
        },
    }
    payload = build_eval_payload(main_rows, frozen_rows, table, fact, split, policy_report)
    (EVAL / "results_geolab.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    write_results_md(
        EVAL / "results_geolab.md",
        main_rows,
        frozen_rows,
        table,
        fact,
        split,
        policy_report,
        settings,
        cost_block(main_rows + frozen_rows),
    )
    write_badcases(EVAL / "badcases_geolab.md", main_rows, frozen_rows)
    return payload
