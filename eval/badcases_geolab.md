# GeoLab 坏例与值得追问的样本

挑选原则：目标进入 top-k 却没被引用；关键词堆砌没有带来检索优势；基线引用了但其它策略因掉出 top-k 而丢失；回答疑似编造规格书没有的数字。同一问题只保留一条代表性样本，避免重复。

## 检索到目标页但回答未引用

共 33 / 750 条进入 top-k 的回答未引用目标页。常见情况是模型改引导购文或科普文（`buying_guide`、`anc_explainer`、`warranty_notes`），目标页在上下文里但没有被标成依据。这是「可见度」和「被当成证据」之间的缺口，面试可以追问。

- **G10** `deepseek-ai/DeepSeek-V3.2` seed=17 策略=cite_sources qtype=对比 rank=3 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：更轻和降噪数字更高，该优先考虑哪一个？
  - 检索：['buying_guide', 'anc_explainer', 'beiyu_nova_air', 'shanhai_orbit']
  - 回答片段：优先考虑哪个，取决于您的主要使用场景和个人体验偏好，而非单纯比较数字。  - **如果您的核心需求是长时间舒适佩戴**（例如通勤、办公室或长途飞行），**更轻的重量**（如 249 克）对戴眼镜和减轻头部压力至关重要 [1]。重量差异在体感上明显 [1]。 - **如果您的核心需求是应对特定低频噪音环境**（如地铁、飞机），可关注降噪能力。但需注意，**降噪数字（如 38 dB）是特定实验室条件下的测量结果**，不同品牌协议不同，不宜直接比较 [1][2]。实际效果还取决于被动隔音和产品调校 [2]。  **结论**：对于多数日常场景，优先考虑**佩戴舒适度（重量）** 可能更实际。若对特定噪
- **G10** `deepseek-ai/DeepSeek-V3.2` seed=17 策略=freshness qtype=对比 rank=3 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：更轻和降噪数字更高，该优先考虑哪一个？
  - 检索：['buying_guide', 'anc_explainer', 'beiyu_nova_air', 'shanhai_orbit']
  - 回答片段：优先考虑哪个，取决于您的主场景和个人偏好，而非单纯比较数字 [1]。  **更轻（如 249 克）** 能提升长时间佩戴的舒适度，尤其对戴眼镜的用户影响更明显 [1]。**降噪数字更高（如 38 dB）** 是实验室指标，实际效果因环境、频段和被动隔音而异，不能直接等同于在所有场景下都更好 [1][2]。  **建议**：若您主要用于**通勤、飞机**等嘈杂环境，可侧重考察降噪的实际表现（包括风噪抑制 [2]）和佩戴密封性 [2]。若主要用于**办公室、居家**等长时间佩戴场景，重量和舒适度可能更关键 [1]。资料未提供两者在具体场景下的直接对比，建议根据场景需求权衡 [1]。
- **G10** `deepseek-ai/DeepSeek-V3.2` seed=17 策略=keyword_stuffing qtype=对比 rank=3 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：更轻和降噪数字更高，该优先考虑哪一个？
  - 检索：['buying_guide', 'anc_explainer', 'beiyu_nova_air', 'shanhai_orbit']
  - 回答片段：根据资料，优先考虑哪一个取决于您的主场景和个人需求。  - **降噪数字更高**：不同品牌的测试协议不同，不宜只看“最大深度”直接比较 [1]。降噪效果对低频噪音（如发动机、地铁）更有效，且受被动隔音和佩戴贴合度影响 [2]。数字更高不一定在所有环境下都表现更好。 - **更轻**：重量直接影响长时间佩戴的体验，特别是对于戴眼镜的用户 [1]。250克上下和300克以上体感差异明显 [1]。  **结论**：若您的主场景是**长时间佩戴**（如长途飞行、办公室），或**戴眼镜**，应优先考虑更轻的重量以提升舒适度 [1]。若您的主场景是**对抗特定低频噪音**（如地铁、飞机引擎），且能确保良好
- **G11** `deepseek-ai/DeepSeek-V3.2` seed=29 策略=baseline qtype=对比 rank=2 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：支持高解析编码和只支持基础编码，日常听歌差别大吗？
  - 检索：['lankei_go', 'beiyu_nova_air', 'buying_guide', 'shanhai_orbit']
  - 回答片段：根据资料，支持高解析编码（如LDAC）与只支持基础编码（如SBC/AAC）在日常听歌时，差别是否明显取决于用户对音质的要求 [3]。  如果用户对音质有要求，那么支持LDAC等编码可以提供更高解析度的音频传输，带来音质上的提升 [3]。例如，山海 Orbit 支持 LDAC，其产品强调音质 [4]。  如果用户对高解析编码没有要求，那么只支持 SBC/AAC 的基础编码耳机（如澜极 Go）已能满足日常听歌需求 [1]。导购文也指出，选择时应先分清主场景，音质编码并非首要考虑因素 [3]。  **总结**：对音质敏感的用户差别较大，对音质不敏感的用户差别不大。
- **G11** `zai-org/GLM-4.5-Air` seed=29 策略=baseline qtype=对比 rank=2 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：支持高解析编码和只支持基础编码，日常听歌差别大吗？
  - 检索：['lankei_go', 'beiyu_nova_air', 'buying_guide', 'shanhai_orbit']
  - 回答片段：支持高解析编码和只支持基础编码在日常听歌时可能有差别，取决于用户对音质的要求[3]。澜极 Go 只支持 SBC 与 AAC，适合对高解析编码没有要求的用户[1]。而山海 Orbit 支持 LDAC 高解析编码，强调音质[4]。如果用户追求更高音质，高解析编码能提供更好的音频体验；若仅日常使用，基础编码已足够[3]。
- **G14** `deepseek-ai/DeepSeek-V3.2` seed=29 策略=baseline qtype=对比 rank=2 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：保修两年和保修一年的产品，还要看哪些条款？
  - 检索：['warranty_notes', 'beiyu_nova_air', 'buying_guide', 'linsound_peak2']
  - 回答片段：除了保修年限，还需关注以下条款：   1. **保修范围**：转轴、耳垫是否在保修内，各品牌不统一 [1]。   2. **人为损坏边界**：条款差异值得在购买前读完 [1]。   3. **特定场景处理**：用于通勤时，建议了解丢失、进水和线材的处理方式 [1]。   4. **购买渠道限制**：非官方渠道可能无法享受原厂保修，需确认发票和序列号 [1]。售后阶段保修渠道往往比参数更重要 [3]。   5. **配件与维修**：更长的保修并不自动说明品控更好，但在维修配件上可能有差异 [1]。    （注：资料未提供具体品牌的详细保修条款文本，以上为通用要点归纳。）

## 关键词堆砌：进了 top-k 仍未被引用

负向对照在主实验上引用率显著低于基线。即使进了 top-k，有时仍输给导购类文档。生产环境不应采用堆砌。

- **G10** `deepseek-ai/DeepSeek-V3.2` seed=17 策略=keyword_stuffing qtype=对比 rank=3 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：更轻和降噪数字更高，该优先考虑哪一个？
  - 检索：['buying_guide', 'anc_explainer', 'beiyu_nova_air', 'shanhai_orbit']
  - 回答片段：根据资料，优先考虑哪一个取决于您的主场景和个人需求。  - **降噪数字更高**：不同品牌的测试协议不同，不宜只看“最大深度”直接比较 [1]。降噪效果对低频噪音（如发动机、地铁）更有效，且受被动隔音和佩戴贴合度影响 [2]。数字更高不一定在所有环境下都表现更好。 - **更轻**：重量直接影响长时间佩戴的体验，特别是对于戴眼镜的用户 [1]。250克上下和300克以上体感差异明显 [1]。  **结论**：若您的主场景是**长时间佩戴**（如长途飞行、办公室），或**戴眼镜**，应优先考虑更轻的重量以提升舒适度 [1]。若您的主场景是**对抗特定低频噪音**（如地铁、飞机引擎），且能确保良好
- **G38** `deepseek-ai/DeepSeek-V3.2` seed=17 策略=keyword_stuffing qtype=售后 rank=4 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：购买时应该确认哪些保修和渠道条件？
  - 检索：['warranty_notes', 'buying_guide', 'anc_explainer', 'beiyu_nova_air']
  - 回答片段：购买时应确认保修年限（常见为1或2年）[1]，并确认是否限于官方渠道[2]。需确认发票和序列号，非官方渠道可能无法享受原厂保修[1]。此外，应了解转轴、耳垫、丢失、进水及线材损坏是否在保修范围内[1]。续航需分开启/关闭降噪确认[2][3]，并确认是否支持快充[2]。如需连接多设备，需确认多点连接[2]。对音质有要求时，可确认是否支持LDAC等编码[2]。
- **G38** `zai-org/GLM-4.5-Air` seed=7 策略=keyword_stuffing qtype=售后 rank=4 in_topk=True cite=0.0 PAWC=0.0000
  - 问题：购买时应该确认哪些保修和渠道条件？
  - 检索：['warranty_notes', 'buying_guide', 'anc_explainer', 'beiyu_nova_air']
  - 回答片段：购买时应确认保修年限和是否限于官方渠道，非官方渠道可能无法享受原厂政策 [1][2]。需确认发票和序列号，并了解转轴、耳垫等是否在保修范围内 [1]。对于通勤场景，还需了解丢失、进水和线材的处理方式 [1]。建议选择官方渠道购买以确保保修权益 [1][2]。

## 基线引用了、改写策略却丢掉（多半是检索掉出 top-k）

计数（条，模型×种子展开）：`statistics` 丢掉 105、多得到 0；`cite_sources` 丢掉 104、多得到 22；`quotation` 丢掉 125、多得到 9；`structured_faq` 丢掉 9、多得到 79；`freshness` 丢掉 119、多得到 17；`keyword_stuffing` 丢掉 84、多得到 30。

- **G01** `deepseek-ai/DeepSeek-V3.2` 策略=statistics qtype=推荐：基线 rank=3 in_topk=True cite=1；本策略 rank=8 in_topk=False cite=0。
  - 问题：通勤用的头戴降噪耳机有什么推荐？
  - 基线检索：['anc_explainer', 'buying_guide', 'beiyu_nova_air', 'linsound_peak2']；本策略检索：['anc_explainer', 'buying_guide', 'linsound_peak2', 'shanhai_orbit']
- **G01** `deepseek-ai/DeepSeek-V3.2` 策略=cite_sources qtype=推荐：基线 rank=3 in_topk=True cite=1；本策略 rank=5 in_topk=False cite=0。
  - 问题：通勤用的头戴降噪耳机有什么推荐？
  - 基线检索：['anc_explainer', 'buying_guide', 'beiyu_nova_air', 'linsound_peak2']；本策略检索：['anc_explainer', 'buying_guide', 'linsound_peak2', 'shanhai_orbit']
- **G01** `deepseek-ai/DeepSeek-V3.2` 策略=quotation qtype=推荐：基线 rank=3 in_topk=True cite=1；本策略 rank=7 in_topk=False cite=0。
  - 问题：通勤用的头戴降噪耳机有什么推荐？
  - 基线检索：['anc_explainer', 'buying_guide', 'beiyu_nova_air', 'linsound_peak2']；本策略检索：['anc_explainer', 'buying_guide', 'linsound_peak2', 'shanhai_orbit']
- **G01** `deepseek-ai/DeepSeek-V3.2` 策略=freshness qtype=推荐：基线 rank=3 in_topk=True cite=1；本策略 rank=8 in_topk=False cite=0。
  - 问题：通勤用的头戴降噪耳机有什么推荐？
  - 基线检索：['anc_explainer', 'buying_guide', 'beiyu_nova_air', 'linsound_peak2']；本策略检索：['anc_explainer', 'buying_guide', 'linsound_peak2', 'shanhai_orbit']
- **G03** `deepseek-ai/DeepSeek-V3.2` 策略=statistics qtype=推荐：基线 rank=2 in_topk=True cite=1；本策略 rank=7 in_topk=False cite=0。
  - 问题：想买一款能同时连手机和电脑的降噪耳机，有哪些选择？
  - 基线检索：['buying_guide', 'beiyu_nova_air', 'anc_explainer', 'shiyin_mini']；本策略检索：['buying_guide', 'anc_explainer', 'shiyin_mini', 'lankei_go']
- **G03** `deepseek-ai/DeepSeek-V3.2` 策略=cite_sources qtype=推荐：基线 rank=2 in_topk=True cite=1；本策略 rank=8 in_topk=False cite=0。
  - 问题：想买一款能同时连手机和电脑的降噪耳机，有哪些选择？
  - 基线检索：['buying_guide', 'beiyu_nova_air', 'anc_explainer', 'shiyin_mini']；本策略检索：['buying_guide', 'anc_explainer', 'warranty_notes', 'shiyin_mini']

## 回答中疑似出现禁止宣称（生成阶段，不是策略页）

在 1680 条主实验回答中，未检出「红点」「50 dB」「销量第一」这几条禁止宣称。这只覆盖了预先列出的模式，不是完整的幻觉审计。

## 生成失败

主实验 1680 条全部生成成功，失败 0。

