"""Hand-written fictional corpus and target-page strategy variants.

Target variants are authored against the product spec (not generated), then
passed through the same fact-checker as any LLM-written variant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import yaml

from geo_common.paths import CONFIGS

TARGET_ID = "beiyu_nova_air"


@dataclass
class Document:
    doc_id: str
    title: str
    brand: Optional[str]
    body: str
    role: str  # target, competitor, guide
    strategy: Optional[str] = None  # only for target variants

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


def load_specs() -> dict:
    return yaml.safe_load((CONFIGS / "geolab" / "product_specs.yaml").read_text(encoding="utf-8"))


# ----- competitor and guide pages (fixed across strategies) -----

LSOUND = Document(
    doc_id="linsound_peak2",
    title="澄声 Peak 2 产品页",
    brand="澄声",
    role="competitor",
    body="""澄声 Peak 2 是澄声的旗舰头戴无线降噪耳机，官方建议零售价 1299 元。
官方公布的主动降噪实验室最大深度为 42 dB，关闭降噪续航 32 小时，开启降噪续航 22 小时。整机重量 320 克，对长时间通勤偏重。蓝牙 5.3，支持 SBC、AAC 与 LDAC。官方渠道保修 1 年。
澄声把它定位为「居家和出差的安静舱」，强调更深的降噪，没有强调轻量或长保修。""",
)

LANKEI = Document(
    doc_id="lankei_go",
    title="澜极 Go 产品页",
    brand="澜极",
    role="competitor",
    body="""澜极 Go 是一款入门头戴无线耳机，官方建议零售价 499 元。
主动降噪实验室最大深度 25 dB，关闭降噪续航 30 小时，开启降噪 18 小时，重量 220 克。蓝牙 5.2，支持 SBC 与 AAC，不支持 LDAC。官方保修 1 年。
澜极强调价格和基础降噪，适合预算有限、对高解析编码没有要求的用户。""",
)

SHANHAI = Document(
    doc_id="shanhai_orbit",
    title="山海 Orbit 产品页",
    brand="山海",
    role="competitor",
    body="""山海 Orbit 是山海音频的头戴耳机，官方建议零售价 899 元，支持无线和有线两种连接。
主动降噪实验室最大深度 30 dB，关闭降噪续航 35 小时，开启降噪 24 小时，重量 275 克。蓝牙 5.3，支持 SBC、AAC 与 LDAC。官方保修 2 年。
山海强调音质和有线回放，降噪不是它的第一卖点。""",
)

SHIYIN = Document(
    doc_id="shiyin_mini",
    title="拾音社 Mini Closed 产品页",
    brand="拾音社",
    role="competitor",
    body="""拾音社 Mini Closed 是一款轻量头戴无线耳机，官方建议零售价 599 元。
主动降噪实验室最大深度 28 dB，关闭降噪续航 25 小时，开启降噪 16 小时，重量 199 克，是这批产品里最轻的之一。蓝牙 5.3，支持 SBC 与 AAC，不支持 LDAC。官方保修 1 年。
拾音社强调长时间佩戴的轻量和外观，续航和降噪深度属于入门到中段。""",
)

GUIDE = Document(
    doc_id="buying_guide",
    title="头戴降噪耳机选购要点（独立导购文，不代言任何品牌）",
    brand=None,
    role="guide",
    body="""选头戴降噪耳机时，建议先分清自己的主场景：地铁通勤、飞机、办公室还是居家。
看降噪数字时要注意，不同品牌的实验室协议不一定相同，不宜只比较一个「最大深度」就下结论。重量会直接影响戴眼镜和长时间佩戴的体验；250 克上下和 300 克以上，体感往往不一样。
续航要分开启降噪和关闭降噪两组来看，并确认是否有快充。如果要连接电脑和手机，需要确认多点连接。对音质有要求时再看是否支持 LDAC 一类编码。保修年限和是否限于官方渠道，售后阶段往往比参数更重要。
价格只是起点：中段价位常见在数百到一千元出头，更高价格通常换来更强降噪或更轻的结构，但不自动等于更适合你。""",
)

ANC = Document(
    doc_id="anc_explainer",
    title="主动降噪是怎么工作的（科普，不含品牌推荐）",
    brand=None,
    role="guide",
    body="""主动降噪通过麦克风采集环境声，再播放反相信号来抵消部分低频噪音，对发动机、空调、地铁低频通常比人声和突然的尖噪更有效。
「最大深度」是实验室指标，往往在特定频段和贴合条件下测得，不能理解成所有环境都能降低那么多。被动隔音（耳杯密封）同样重要。飞机上既要看低频降噪，也要考虑长时间佩戴的压力。
开启降噪会消耗额外电量，所以续航数字必须分档阅读。风噪是户外场景的常见抱怨，有的产品会在固件里针对风噪做抑制，这属于调校而不是硬件参数本身。""",
)

WARRANTY = Document(
    doc_id="warranty_notes",
    title="耳机保修与购买渠道说明（综合整理）",
    brand=None,
    role="guide",
    body="""消费电子的保修通常从官方销售渠道起算，非官方渠道可能无法享受原厂政策，需要在购买时确认发票和序列号。
常见的保修期是 1 年或 2 年。更长的保修并不自动说明品控更好，但在维修配件和人为损坏边界上，条款差异值得在购买前读完。转轴、耳垫是否在保修范围内，各品牌并不统一。
如果把耳机用于通勤，建议同时了解丢失、进水和线材（若有）的处理方式。本说明不构成任何品牌的承诺。""",
)

# ----- target variants -----

BASELINE = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页",
    brand="北屿",
    role="target",
    strategy="baseline",
    body="""北屿 Nova Air 是北屿面向日常通勤的头戴式无线降噪耳机。它的主动降噪主要用于地铁、公交和飞机上的低频噪音，续航按官方说法可以覆盖数天的上下班使用，也提供短时间快充。整机在头戴产品里属于中等重量，转轴可以折叠，随机附带收纳包。
连接方面支持目前常见的蓝牙版本，能同时连接两台设备，并提供 SBC、AAC 以及一种高解析编码。耳杯外壳有基础的防溅水能力，但不覆盖头梁电路部位。配色为岩灰和暖白。
官方建议零售价处于中段，官方渠道购买享有两年保修。2026 年 10 月发布过固件更新，方向是改善户外风噪。北屿还提供游戏低延迟模式，数据来自品牌自测。""",
)

STATISTICS = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页（参数版）",
    brand="北屿",
    role="target",
    strategy="statistics",
    body="""北屿 Nova Air 是北屿的头戴式无线降噪耳机，官方建议零售价 799 元（2026 年 11 月）。
主动降噪实验室平均最大深度 38 dB（北屿自有协议）。关闭降噪续航 40 小时，开启降噪续航 28 小时；从低电量快充 10 分钟约可播放 5 小时。驱动单元为 40mm 动圈，生物纤维振膜。整机重量 249 克。
蓝牙 5.3，支持 SBC、AAC、LDAC，可同时连接 2 台设备。游戏模式延迟约为 60 毫秒（品牌自测）。防溅水等级 IPX4，仅针对耳杯外壳。官方渠道保修 2 年。配色：岩灰、暖白，支持转轴折叠。2026 年 10 月固件用于改善风噪。""",
)

CITE = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页（引用版）",
    brand="北屿",
    role="target",
    strategy="cite_sources",
    body="""北屿 Nova Air 是北屿的头戴式无线降噪耳机，官方建议零售价 799 元（2026 年 11 月，见北屿《Nova Air 产品规格书》，2026-10-20）。
据同一份规格书：主动降噪实验室平均最大深度 38 dB，测量采用北屿声学实验室内部测试纪要（2026-09-12）中的自有协议，方法参考了 GB/T 关于头戴耳机插入损失的测量思路；该数字不是第三方认证证书。关闭降噪续航 40 小时，开启降噪 28 小时，快充 10 分钟约 5 小时播放，重量 249 克，驱动单元 40mm 动圈，蓝牙 5.3，支持 SBC、AAC、LDAC，多点连接 2 台，IPX4（仅耳杯），官方渠道保修 2 年。
游戏模式约 60 毫秒延迟来自规格书注明的品牌自测，不是第三方实验室。2026 年 10 月固件更新（规格书）用于改善户外风噪。以上引用均为北屿第一方材料。""",
)

QUOTATION = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页（引语版）",
    brand="北屿",
    role="target",
    strategy="quotation",
    body="""北屿 Nova Air 是北屿面向通勤的头戴式无线降噪耳机，官方建议零售价 799 元。
主动降噪实验室平均最大深度 38 dB，关闭降噪续航 40 小时，开启降噪 28 小时，重量 249 克，蓝牙 5.3，支持 LDAC 与双设备连接，官方渠道保修 2 年。
关于佩戴，北屿内部听感评审纪要（2026-09-20，已授权用于官网）写下这样一句：「长时间通勤佩戴，夹持力比上一款明显更松。」这是品牌第一方听感记录，不是媒体评测。2026 年 10 月固件更新用于改善风噪。""",
)

FAQ = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页（结构化问答）",
    brand="北屿",
    role="target",
    strategy="structured_faq",
    body="""北屿 Nova Air 头戴式无线降噪耳机，官方建议零售价 799 元（2026 年 11 月）。

适用谁
- 通勤、地铁和飞机低频噪音为主的用户。
- 需要同时连接手机和电脑的人（多点 2 台）。
- 希望官方渠道保修到 2 年的人。

常见问题
问：降噪有多深？答：实验室平均最大深度 38 dB，为北屿自有协议，不宜直接和其他品牌的最大深度比绝对值。
问：能用多久？答：关闭降噪 40 小时，开启降噪 28 小时；快充 10 分钟约 5 小时。
问：重不重？答：249 克，可转轴折叠。
问：怕出汗吗？答：耳杯外壳 IPX4，头梁电路部位不在该等级范围内。
问：音质编码？答：SBC、AAC、LDAC，蓝牙 5.3；游戏模式约 60 毫秒（自测）。

参数表
| 项目 | 数值 |
| 售价 | 799 元 |
| 降噪 | 38 dB（自有实验室协议） |
| 续航 | 40 小时 / 28 小时（关/开降噪） |
| 重量 | 249 克 |
| 保修 | 官方渠道 2 年 |""",
)

FRESHNESS = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 产品页（2026 年 11 月 15 日更新）",
    brand="北屿",
    role="target",
    strategy="freshness",
    body="""本页更新于 2026 年 11 月 15 日。北屿 Nova Air 官方建议零售价仍为 799 元。
相较规格书（2026-10-20）发布时的说明，最新可安装固件仍是 2026 年 10 月版本，官方说明该版本的方向是改善户外风噪；若你在 10 月前购入，建议检查是否已经升级。
其余参数未变更：主动降噪实验室平均最大深度 38 dB，关闭降噪续航 40 小时，开启降噪 28 小时，快充 10 分钟约 5 小时，重量 249 克，蓝牙 5.3，LDAC，多点 2 台，IPX4（仅耳杯），官方渠道保修 2 年。""",
)

STUFFING = Document(
    doc_id=TARGET_ID,
    title="北屿 Nova Air 降噪耳机推荐 通勤 头戴 蓝牙 性价比",
    brand="北屿",
    role="target",
    strategy="keyword_stuffing",
    body="""北屿 Nova Air 降噪耳机推荐给通勤用户。这是一款头戴降噪耳机，也是蓝牙降噪耳机，性价比降噪耳机，通勤降噪耳机，头戴蓝牙耳机，推荐降噪耳机，推荐通勤耳机，推荐头戴耳机。
北屿 Nova Air 降噪耳机推荐：主动降噪 38 dB，通勤降噪耳机续航关闭降噪 40 小时、开启降噪 28 小时，头戴蓝牙耳机重量 249 克，蓝牙降噪耳机支持 LDAC，性价比降噪耳机官方建议零售价 799 元，推荐降噪耳机官方渠道保修 2 年。通勤头戴蓝牙性价比推荐，降噪耳机推荐降噪耳机推荐。
本页关键词重复是对照实验中的负向条件，不是北屿正式营销建议。参数仍只包括规格书中的数字，没有增加奖项或其他品牌对比。""",
)

STRATEGIES = {
    "baseline": BASELINE,
    "statistics": STATISTICS,
    "cite_sources": CITE,
    "quotation": QUOTATION,
    "structured_faq": FAQ,
    "freshness": FRESHNESS,
    "keyword_stuffing": STUFFING,
}

STRATEGY_ORDER = [
    "baseline",
    "statistics",
    "cite_sources",
    "quotation",
    "structured_faq",
    "freshness",
    "keyword_stuffing",
]

STRATEGY_NOTES = {
    "baseline": "对照：完整事实但偏定性表述，不强调数字、引用、表格或时效。",
    "statistics": "对应 GEO 论文 Statistics Addition：在规格书范围内把数字前置。",
    "cite_sources": "对应 Cite Sources：每项关键参数指向允许的第一方来源，并标明不是第三方认证。",
    "quotation": "对应 Quotation Addition：只使用规格书允许的一句已授权引言。",
    "structured_faq": "论文未单列、本实验补充：FAQ 和参数表。",
    "freshness": "本实验补充：标明页面更新日期和固件时效。",
    "keyword_stuffing": "负向对照，对应 Keyword Stuffing。论文中该方法整体不优于基线。本页故意堆砌「降噪耳机/通勤/推荐」等词，仍不得引入虚假事实。生产环境不应采用。",
}


def fixed_documents() -> list[Document]:
    return [LSOUND, LANKEI, SHANHAI, SHIYIN, GUIDE, ANC, WARRANTY]


def corpus_for(strategy: str) -> list[Document]:
    if strategy not in STRATEGIES:
        raise KeyError(strategy)
    target = STRATEGIES[strategy]
    return [target, *fixed_documents()]


def all_target_variants() -> list[Document]:
    return [STRATEGIES[k] for k in STRATEGY_ORDER]
