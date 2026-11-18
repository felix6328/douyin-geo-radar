# GeoRadar 与 GeoLab｜面向 GEO / 增长投放的两个 Agent 项目

个人项目，为投递「抖音 AI Agent 产品（增长投放方向）实习生」而做。  
**不是**字节跳动、抖音或豆包的生产系统，也没有使用这些产品的真实流量或内部数据。

两个项目共用本仓库，产品观是同一句：

**能用规则和检索算死的，不交给模型吹；模型只做规则写不死的判断和假设，并且每条结论必须带可复核的证据。监测不是因果，模拟不是线上流量。**

| 项目 | 一句话 | 对应 JD |
| --- | --- | --- |
| **GeoRadar** | 品牌可见度监测与归因：把多模型、多次采样的回答，变成 SOV、提及率、首位率、来源类型和稳定性指标，再产出带证据的可干预机会与待验证假设。 | 策略挖掘、效果分析与洞察迭代、评测 |
| **GeoLab** | 内容策略对照实验台：在虚构品牌的受控语料上，用对照实验检验统计、引用、引言、结构化 FAQ、时效，以及关键词堆砌（负向对照）会不会提高被引用率和位置加权可见度。 | Agent 能力与 Skills、实验设计、效果评估 |

技术栈：Python 3.13、httpx（硅基流动官方 OpenAI 兼容接口）、jieba + rank-bm25、FastAPI 工作台。不依赖 LangChain。

## 必须先读的诚实边界

- GeoRadar 调用的是硅基流动上的**裸模型**：`deepseek-ai/DeepSeek-V3.2`、`Qwen/Qwen3.6-35B-A3B`、`zai-org/GLM-4.5-Air`。它们**没有实时搜索**，不能当成豆包、元宝、通义或抖音站内 AI 的品牌露出。跨模型差异反映的是参数知识和对齐，不是这些 App 的真实流量。
- 曾试用 `zai-org/GLM-5.3-Flash`，在本接口上无法关闭思考链（单次仍有数百 reasoning tokens、时延数十秒），因此平台代表和抽取器改用 `GLM-4.5-Air`（思考可关，时延约 1 秒量级）。
- GeoLab 的品牌「北屿 / 澄声 / 澜极 / 山海 / 拾音社」全部虚构；检索是本地 BM25，生成仍是裸模型。这是模拟生成式引擎，**不是**对真实 GEO 平台的投放。
- 策略形态参考 Aggarwal et al., *GEO: Generative Engine Optimization*, KDD 2024（DOI: [10.1145/3637528.3671900](https://doi.org/10.1145/3637528.3671900)，arXiv: [2311.09735](https://arxiv.org/abs/2311.09735)）。PAWC 使用论文公式 (3)：\(\mathrm{Imp}_{pwc}(c_i,r)=\frac{\sum_{s\in S_{c_i}}|s|\cdot e^{-\mathrm{pos}(s)/|S|}}{\sum_{s\in S_r}|s|}\)，多源共引时词数均分。中文 \(|s|\) 按 jieba 分词、去掉标点。显式引用（`[id]` / `[1]`）才计入 PAWC；仅出现品牌名只计入提及率。
- 关键词堆砌是**负向对照**，且必须通过规格书事实校验。生产环境不应采用。禁止在生成内容里编造奖项、第三方认证或规格书没有的数字。
- 查询集和抽取金标由脚本起草，**【未经人工审阅】**。审完之前，不要把抽取器「准确率」写进简历。
- 费用是按硅基流动[价格页](https://www.siliconflow.cn/pricing)标价与返回 token 的**估算**，查阅日期 2026-11-14（Asia/Shanghai），不是账单原件。

## 没有 Key 时能复现什么（2026-11-17 实测）

在不含任何 Key 的副本上运行 `scripts/run_georadar.py` 与 `scripts/run_geolab.py`：生成回答全部命中 `data/cache`（新调用 0、费用 0），
GeoRadar 的提及率 0.6153、跨采样 Jaccard 0.6054 / 首位一致率 0.6167，GeoLab 主表（FAQ 配对引用率 +0.29 [0.13, 0.46]、关键词堆砌 −0.23 等）与仓库记录一致；18 个单元测试通过。
**不能**离线复现的是「规则层 vs LLM 抽取一致性」和「洞察 Agent」两节：没有 Key 时会被写成空结果，因此离线复跑请加 `--skip-llm-extract --skip-insight`，不要覆盖仓库里的这两节。

## 如何运行

需要：Python 3.11+（开发时为 3.13）、可访问 `https://api.siliconflow.cn/v1`。建议把**只有** `SILICONFLOW_API_KEY=...` 这一行放进仓库根目录的 `.env.local`（权限 600）。加载器只解析这一行，不会把其它变量读进进程。不要使用 `DEEPSEEK_*`（可能指向第三方中转）。`.env.local` 已在 `.gitignore`，不要提交，也不要打进压缩包。

没有 key 时，规则层、检索、事实校验和单元测试仍可运行，但不得填写模型回答上的 SOV / 引用率 / PAWC，也不得填写费用（记 0）。

```bash
git clone <本仓库> geo && cd geo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PWD

# 单元测试（不调用模型）
python -m pytest tests/ -q

# GeoRadar：150 条查询 × 3 个模型 × 2 次采样，再做抽取、指标、洞察
python scripts/run_georadar.py

# GeoLab：40 条查询 × 7 种策略 × 2 个模型 × 3 个种子，外加冻结检索消融
# 已跑过的请求走磁盘缓存，不重复计费；中断后再跑也不会丢已缓存的回答。
python scripts/run_geolab.py

# 只根据已保存的回答重出报告（不调 API）
python scripts/render_geolab.py

# 核对 COST.md 与费用日志是否一致（不调 API；日志本身不入库）
python scripts/write_cost.py

# 工作台（查看已生成的报告）
./scripts/run_app.sh    # http://127.0.0.1:8766
```

已经测完的报告在 `eval/results_georadar.md`、`eval/badcases_georadar.md`、`eval/results_geolab.md`、`eval/badcases_geolab.md`。重新跑评测会走磁盘缓存（不重复计费），数字以脚本汇总为准。累计估算费用见 `COST.md`。

费用上限默认 28 元（`configs/settings.yaml` 的 `api.spend_cap_cny`），超出则停止新的调用。

## 本次实测摘要

数字全部来自脚本，细节、区间和坏例以 `eval/` 为准。费用估算见 `COST.md`（合计约 ¥9.62，不是账单）。

**GeoRadar**（150 条中文消费问题 × 3 个裸模型 × 2 次采样，900 条回答全部成功）：

- 自发提及分析集（排除问题已含品牌的题，720 条）里，至少提及一个词典品牌的占比 **0.6153**。
- 跨采样稳定性（360 对）：品牌集合平均 Jaccard **0.6054**，首位一致率 **0.6167**。跨模型 Jaccard 约 0.50–0.62。
- 前三品牌 SOV：索尼 **0.0701**，Bose **0.0546**，携程 **0.0516**。分品类更集中，例如耳机里索尼 SOV **0.2669**、咖啡里星巴克 **0.2349**、新能源车里比亚迪 **0.1981**。
- 含 URL 的回答 **0 / 900**。规则层与 LLM 抽取的品牌集合平均 Jaccard **0.8985**——这是两套自动抽取的一致性，**【金标未经人工审阅】**，不能写成准确率。
- 洞察 Agent 的引用有 3 条校验未通过，报告里已标明，不得当结论。

**GeoLab**（40 题 × 7 策略 × 2 模型 × 3 种子 = 1680 条，失败 0；另有 280 条冻结检索消融）：

- 七种手写策略页全部通过规格书事实校验。关键词堆砌是负向对照。
- 两模型合并、问题级配对（策略 − 基线，2000 次 bootstrap 95% 区间）：只有 `structured_faq` 显著优于基线，引用率 Δ **+0.2917 [0.1333, 0.4583]**，PAWC Δ **+0.0966 [0.0523, 0.1428]**。`statistics`、`cite_sources`、`quotation`、`freshness`、`keyword_stuffing` 的引用率配对效应都显著为负。
- FAQ 的平均 BM25 排名从基线 **3.45** 提到 **1.38**，40 题全部进入 top-k（基线 0.700）。进入 top-k 之后的条件引用率，七种策略都在 **0.93–1.00**。冻结检索后，所有策略相对基线的配对引用率 CI 都含 0。因此本实验里 FAQ 的优势几乎全部来自检索，不是生成阶段更「会写」；FAQ 页含问句，可能有词面重叠，不能当成普遍的 GEO 结论。
- 关键词堆砌 26/40 题排名差于基线、仅 8 题更好；配对引用率 Δ **-0.2250 [-0.4125, -0.0208]**，与论文中该方法不优于基线的方向一致。
- 训练题上 Agent 给五类问题都选了 `structured_faq`，与全局最优相同。测试集（10 题）配对引用率 Δ **+0.3667 [0.0333, 0.7000]**，优于基线；**不能**写成「Agent 学会了按类型分配」——按类型与全局最优数字完全一样。测试集很小，边际区间有重叠，判断靠配对区间。

## 代码导读（面试用）

- `configs/settings.yaml`：模型、采样次数、费用上限。三个「平台」是三个模型家族，配置里写明了无搜索。
- `configs/brands/dictionary.yaml`、`georadar/brands.py`：品类品牌词典。泛化词（苹果、理想、小米）必须满足邻近上下文，并有排除规则（苹果醋、小米粥）。`tests/test_extract_rules.py` 覆盖这些边界。
- `configs/queries/georadar_queries.yaml`：150 条中文消费者问题，五类各 30 条。计算自发 SOV 时排除「品牌对比 / 品牌咨询」（问题里已经有品牌）。
- `georadar/generate.py`：生成提示明确要求「没有联网、不要编网址」。
- `georadar/sources.py` + `georadar/extract_llm.py`：规则抽 URL 和「据…报道」，LLM 抽情感、理由和首选；理由必须能在原文里找到 quote。
- `georadar/metrics.py`：SOV、提及率、首位率、跨采样 Jaccard、跨模型 Jaccard。
- `configs/skills/*.yaml` + `georadar/insights.py`：分析框架 Skills。洞察 Agent 只能引用证据包里的编号，校验失败的条目不得当结论。
- `configs/geolab/product_specs.yaml`：虚构产品规格书，是事实校验的唯一真源。
- `geolab/corpus.py`：七种手写策略页；`geolab/factcheck.py` 拒绝红点奖、未申报数字、目标页贬低竞品。所有策略页必须先通过校验才能进入实验（`tests/test_factcheck.py`）。面试取舍：先护栏、后效果，避免「用编造的权威感换引用」。
- `geolab/retrieve.py`：jieba + BM25，不用稠密检索。取舍是可控、可复现、不另付 embedding 费用；代价是 FAQ 这种带问句的页面可能靠词面重叠赢，换稠密检索排序可能变。主实验在内容变更后重检索；`frozen_retrieval_ablation` 冻结 baseline 的排序、只换正文，用来把「被找到」和「被引用」分开——本轮结果里，后者几乎没有策略差异。
- `geolab/pawc.py`：Aggarwal et al. KDD 2024 公式 (3)，`tests/test_pawc.py` 核对单源和共引均分。只把显式 `[id]` / `[1]` 算作来源贡献，品牌名出现只进提及率，防止把「提到了」写成「被当成证据」。
- `geolab/pipeline.py` + `geolab/report.py`：多种子；以**问题**为单元做 bootstrap；相对基线用**配对**差值（同一题的策略 − 基线）。训练题上形成「按类型分配」和「全局最优」，测试题上验收，不得回看测试题调策略。本轮两者相同，所以不能声称 Agent 会按类型选策略。`scripts/render_geolab.py` 可在不调 API 的情况下从保存的回答重出报告。
- `geolab/statsutil.py`：配对区间比「两条边际 CI 是否重叠」更合适。本轮测试集 10 题的边际区间有重叠，配对区间才把 0 排除在外——面试要能讲清这一点，也要承认小样本。
- `geo_common/envload.py`、`geo_common/llm.py`：只读 `SILICONFLOW_API_KEY`，官方地址，磁盘缓存（中断后续跑不丢、不重复计费），费用 jsonl 不含密钥，思考链默认关闭，进程级费用上限 28 元。

## 你需要自己做的

1. 通读 150 条 GeoRadar 查询和 `data/gold/georadar_extractor_gold_draft.json` 里的自动金标，审完之前简历要保留「自建测试题 / 未经人工审阅」。
2. 在自己电脑上按 README 跑通演示，能讲清 SOV 口径、PAWC 公式、训练/测试切分，以及「为什么不能把结果说成抖音效果」。
3. 读懂坏例：跨模型首位不一致、跨采样不稳定、裸模型给出 URL、检索到却未引用、关键词堆砌的代价。
4. 不要写成与字节跳动合作，也不要补访谈人数除非你真的访谈过。不要把模拟提升写成「在抖音或豆包上有效」，也不要把 FAQ 的检索优势写成普遍的 GEO 定律，或把「按类型分配」写成 Agent 的独特能力。
5. GeoLab 的 40 条查询和 GeoRadar 的抽取金标都要自己审一遍。审完之前，简历保留「自建测试题 / 未经人工审阅」。

## 补充调研（2026-11-17）

5 篇公开报道中的 10 条商家/行业样本：商家普遍无法验证 AI 推荐效果，支持「多次采样监测」的设计；堆关键词、伪造背书等做法与 GeoLab 的负对照一致。这是二手调研，缺少平台侧视角。见 [docs/research/调研报告.md](docs/research/调研报告.md)。
