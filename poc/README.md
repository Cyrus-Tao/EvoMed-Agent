# EvoMed-Agent 最小原型（PoC）· 关键技术验证

> 第十一届华为 ICT 大赛（中国赛·创新赛）赛题 3
> 基于华为 ModelEngine Nexent 打造可进化决策智能体

本目录是**可运行的最小原型**，用于验证 EvoMed-Agent 五层架构中的四项关键技术假设。
**零第三方依赖、无需 GPU、无需 API Key**，Python 3.9+ 直接运行即可复现全部实验结果。

---

## 1. 快速开始

```bash
cd poc
python run_poc.py                # 离线运行（mock 推理器，结果完全可复现）
python run_poc.py --save-traces  # 额外落盘 5 条完整决策链 trace.json
python run_poc.py --llm http     # 接入真实大模型（需先配置环境变量）
```

接入真实模型时配置：

```bash
export EVOMED_LLM_BASE_URL="https://api.deepseek.com/v1"
export EVOMED_LLM_API_KEY="sk-xxxxxx"
export EVOMED_LLM_MODEL="deepseek-chat"
```

首次运行会自动合成最小验证数据集（固定随机种子 20261016）：
30 条病例（10 个病种）+ 10 条指南片段 + 23 份异构原始资产。
数据由公开医学常识模板合成，**不含任何真实患者信息，可安全开源**。

---

## 2. 原型覆盖的架构层次

| 层 | 对应赛题任务 | 本原型实现 | 正式系统（Nexent 上）将替换为 |
| --- | --- | --- | --- |
| L0 资产认知 | ① | `src/asset_card.py`：23 份异构资产 → 统一资产卡片（质量分 / 敏感度 / 可检索切片） | Docling 解析 + Nexent 个人级知识库（20+ 格式） |
| L1 本体演化 | ② | `src/ontology.py`：术语抽取 → 关系候选 → SHACL 式校验 → 版本化增量更新 | OntoLearner + OntoAligner（对齐 DOID/MONDO/ICD-10）+ pySHACL |
| L2 图谱检索 | ④ 前段 | `src/retrieval.py`：BM25 稀疏路 + TF-IDF 稠密路双路召回，本体约束做查询扩展 | LightRAG / HippoRAG + all-MiniLM-L6-v2 + FAISS IVF_FLAT |
| L3 双驱决策 | ③ 核心 | `src/agent.py`：AgentDiagnosis 四阶段（初始诊断 → 四步 CoT → RAG 增强 → 决策融合）+ 四维置信度 + 低置信拒答 | Nexent Agent Runtime + MCP Server 挂载 + Skill 渐进式披露 |
| L4 溯源进化 | ④⑤ | `src/trace.py`：trace.json 全链路落盘；反馈回流驱动本体版本演进 | Nexent 智能体版本管理 + 平台评测子系统 + 记忆蒸馏 |

---

## 3. 验证了什么（实测结果）

测试集 15 条、反馈集 15 条，二者**严格不重叠**（反馈不会泄漏测试集答案）。

| 指标 | v0 基线 | v1 +本体+RAG | v2 +反馈进化 | Δ(v1−v0) | Δ(v2−v1) |
| --- | --- | --- | --- | --- | --- |
| Accuracy | 0.2667 | 0.9333 | **1.0000** | +0.6666 | +0.0667 |
| 有效作答准确率 | n/a（全部拒答） | 0.9333 | **1.0000** | — | +0.0667 |
| Macro-P | 0.2083 | 0.8667 | **1.0000** | +0.6584 | +0.1333 |
| Macro-R | 0.2000 | 0.9000 | **1.0000** | +0.7000 | +0.1000 |
| Macro-F1 | 0.1900 | 0.8800 | **1.0000** | +0.6900 | +0.1200 |
| 证据召回命中率 | 0.0000 | 1.0000 | 0.9333 | +1.0000 | −0.0667 |
| 证据可溯率 | 0.0000 | 1.0000 | 1.0000 | +1.0000 | 0.0000 |
| 拒答率 | 1.0000 | 0.0000 | 0.0000 | — | — |
| 平均端到端时延 | — | — | — | — | — |

> 时延列留空：mock 推理器不涉及真实网络与模型推理，测出的毫秒数无意义。该指标在 W7 接入真实模型后采集。
>
> **关于 v2 证据召回命中率的 −0.0667**：这是真实存在的负增量，不掩饰。原因是本体从 30 条关系扩展到 48 条后，查询扩展命中的症状变多，个别样本的召回集合被稀释，Top-K 中恰好丢失了指向金标疾病的那条证据。但它**未影响最终结果**——该样本的 Accuracy 仍为正确（v2 Accuracy 反而升到 1.0），说明决策融合阶段对召回噪声有一定鲁棒性。正式实验中我们会把 K 从 3 提到 5 并引入证据重排，观察该指标是否回正。

### 四项关键结论

- **KV-1 检索增强有效**：Accuracy 0.2667 → 0.9333（Δ=+0.6666）。复现了团队论文 *AgentDiagnosis* 的核心发现——**RAG 的增益远大于 CoT**。
- **KV-2 本体约束提升检索**：证据召回命中率 0 → 1.0。本体 `has_symptom` 关系驱动的查询扩展，让多跳检索能命中正确疾病的证据。
- **KV-3 决策链可溯源**：可溯率 1.0，每条决策产出字段完整的 `trace.json`（输入证据 / 工具调用 / 中间结论 / 置信度 / 本体版本），可回放可审计。
- **KV-4 进化闭环成立**：把反馈集上答错样本的正确「症状—疾病」关联回流进本体，本体由 v0.1.0（30 条关系）演进到 v0.2.0（48 条关系），Accuracy 0.9333 → 1.0000。**这就是"可进化"的直接证据。**

### 一个值得讲的发现

v0 基线的**拒答率是 100%**——没有任何证据支撑时，四维置信度全部低于阈值，系统选择"不知道"而不是硬猜。接入检索后拒答率降到 0，且准确率 93%。
这恰好回应了医疗场景最关键的诉求：**宁可拒答，不可错答**。

---

## 4. 目录结构

```
poc/
├── run_poc.py              一键运行入口（三代对照 + 指标输出）
├── data/
│   ├── gen_data.py         数据集合成器（固定种子，可复现）
│   ├── cases.jsonl         病例 30 条
│   ├── guidelines.jsonl    指南片段 10 条
│   ├── raw_assets.jsonl    异构原始资产 23 份（txt/md/csv）
│   └── dataset_meta.json   数据集元信息
├── src/
│   ├── asset_card.py       L0 资产卡片
│   ├── ontology.py         L1 本体构建 / 对齐接口 / 校验 / 增量更新
│   ├── retrieval.py        L2 双路召回 + 本体约束扩展 + 证据合并
│   ├── agent.py            L3 AgentDiagnosis 四阶段内核
│   ├── llm.py              LLM 适配（mock 离线 / http 真实模型）
│   ├── trace.py            L4 trace.json 溯源
│   └── evaluate.py         7 项指标
└── out/                    运行产物
    ├── asset_cards.json    资产卡片
    ├── ontology_0.1.0.json / ontology_0.2.0.json   本体两个版本
    ├── trace_sample.json   决策链样例
    ├── traces/             批量 trace
    └── metrics.json        全量指标与 KV 结论
```

---

## 5. 诚实的局限性说明

提交给指导老师时，以下几点务必一并说明，避免被误解为"用假数据刷指标"：

1. **mock 推理器不是大模型**。它是一个确定性规则推理器，用来在离线环境下验证**架构链路与相对增益**。v0/v1/v2 的**绝对数值没有临床意义**，有意义的是代际增量 Δ。正式实验将在 W5–W7 用 DeepSeek-7B / Qwen-7B 在 Nexent 平台上重跑。
2. **数据规模极小**。30 条病例 / 10 个病种仅够跑通链路，指标波动大（v2 的 1.0000 有偶然成分）。正式评测接入公开中文医疗基准（CMB、MedQA-zh 等），目标样本量 ≥1000。
3. **标准术语对齐未实装**。本体 `std_refs` 字段保留接口并置为 `pending`，**没有编造任何 DOID / ICD-10 编码**。真实对齐在 W3–W4 用 OntoAligner 完成。
4. **噪声已做确定性绑定**。mock 的随机扰动按 `(样本, 疾病)` 派生，确保 v1 与 v2 在同一扰动下作答——否则指标差异会混入随机性，无法归因到"本体进化"本身。这是实验中踩过的一个坑，已修正。
5. **可复现性做了硬性保证**。Python 对字符串的哈希默认随机化（`PYTHONHASHSEED`），集合迭代顺序会随进程变化，进而影响检索 Top-K 的并列排序——实测曾出现同一份代码两次跑出 v2 Accuracy 1.0 与 0.9333 两种结果。`run_poc.py` 现会在启动时强制以 `PYTHONHASHSEED=0` 重新执行自身，已验证连续 4 次运行及 `--save-traces` 模式的 `metrics.json` **完全一致**。

---

## 6. 与 Nexent 平台的对接计划

原型刻意与 Nexent 解耦，以便离线验证；下一步按三条通道外挂注入平台，**不改内核**：

- **SDK 通道**：`agent.py` 的四阶段内核改写为 `sdk/nexent/core/agents` 下的自定义 Agent
- **MCP 通道**：`retrieval.py`、`trace.py`、`ontology.py` 封装为 5 个 MCP Server（`asset-scanner` / `ontology-builder` / `graph-retriever` / `trace-writer` / `evaluator`）
- **Skill 通道**：四阶段流程与复盘逻辑注册为渐进式披露的 Skill（当前已识别 S2/S3/S4 三个可复用模板）

锁定 **Nexent v2.7.0** tag 进行开发。
