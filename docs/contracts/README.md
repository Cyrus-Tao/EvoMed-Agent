# EvoMed-Agent 数据契约

冻结版本 **v1.0.0**（2026-11-04）｜队名：**衍医队**｜项目：EvoMed-Agent

## 这是什么

L0 资产认知、L1 本体演化、L4 溯源进化与评测四个模块之间的数据格式约定。三个人并行开发，契约先于代码：任何模块产出或消费这些 JSON，都必须先通过校验。

**契约结构严格对齐 EvoMed-PoC 现有产物**，不是理想化设计稿——保证今天就能跑通校验。

## 文件清单

| 文件 | 主责 | 校验对象 | 状态 |
| --- | --- | --- | --- |
| `asset_card.schema.json` | A | `poc/out/asset_cards.json`（卡片数组） | frozen |
| `ontology.schema.json` | B | `poc/out/ontology_v0.1.0.json`、`ontology_0.2.0.json` | frozen |
| `trace.schema.json` | A | `poc/out/trace_sample.json`、`traces/*.json` | frozen |
| `eval_split.schema.json` | B | 尚无产物文件，W7 接入 Nexent 时落盘为配置 | frozen（配置契约） |

## 决策记录

| 编号 | 日期 | 决策 | 备选 | 理由 | 影响范围 | 决策人 |
| --- | --- | --- | --- | --- | --- | --- |
| D-001 | 2026-11-04 | L1 标准对齐统一使用 **ICD-10**，字段名固定 `std_refs.icd10` | ICD-11 | 8 周 3 人，扁平码表落地快；现成工具链（medical-terminologies-mcp 等）为 ICD-10；开源许可干净；PPT 与讲稿原本已是 ICD-10，改动面最小 | `ontology.schema.json`、4 份 Word、架构图、PoC 代码与产物、全部材料文字 | 全队 + 指导老师 |
| D-002 | 2026-11-04 | 报名队名为 **「衍医队」** | Dx³ 诊立方 | 与正式材料目录名、答辩讲稿口径一致 | 报名表、答辩开场、开源仓库 owner | 全队 |
| D-003 | 2026-11-04 | ICD-10 对齐目标采用**《疾病分类与代码国家临床版 2.0（2022 汇总版）》**；**完整码表不随仓库分发**，仅保留评测所需最小映射子集；DOID（CC0）升为主对齐标准，ICD-10 降为二级标注 | 整表入库 / WHO 原版 / GB/T 14396-2016 / 医保版 2.0 | 四份版本均未授予再分发许可；WHO 更把「与其他分类/术语的映射及翻译」排除在 ICD-10 许可之外；国临版 2.0 是国内病案首页现行口径，与中文语料天然对齐 | `docs/04-参考资料清单.md`、`docs/ICD10_SOURCE.md`、`NOTICE`、L1 对齐模块、A3 本体对齐准确率口径 | 全队 + 指导老师 |

> 采用 ICD-10 不等于否定 ICD-11：对齐模块设计为插件式，ICD-11 中文版在国内普及后可热替换，届时按变更规则升级契约到 v1.1.0。这恰好为赛题任务②「与行业标准动态对齐」提供真实演进案例。

> **D-003 补述**：D-001 定的是「用哪一版编码」，D-003 定的是「码表从哪来、能不能放进仓库」——两者不冲突。政府网站公开发布 ≠ 允许再分发，所以策略是把「对齐目标」与「分发方式」分开：仓库内只留来源说明、`NOTICE` 与最小映射子集，完整 xlsx 由使用者自行下载。**D-003 不改变任何 schema 字段**，契约仍为 v1.0.0，不需重跑三代评测。

## 关键约束

- `std_refs` 上 `additionalProperties: false` 是「写死」的实质：任何人再写 `icd11` 会直接校验失败，而不是悄悄多一个键。
- 三个编码字段用 `oneOf: null | 带 pattern 的字符串`：兼容 PoC 现状（全部 `pending` 置 `null`），同时防止编造编码（乱填 `123` 会被拦）。
- `align_status` 单独表达对齐状态，不要用编码值本身表达状态。
- `std_refs.icd10` 在开源仓库中**只允许填入 `data/icd10_minimal.json` 最小映射子集列出的编码**（评测涉及的 10 类疾病）。完整码表不入库，见 D-003 与 `docs/ICD10_SOURCE.md`。
- `eval_split` 要求 `python_hash_seed = 0`。字符串哈希随机化会改变检索 Top-K 排序，曾导致同一份代码两次跑出 v2 Accuracy 1.0 与 0.9333。
- 测试集与反馈集必须不相交，禁止在测试集上做反馈回流。

## 变更规则

改字段 = 提 PR + 三人通过 + `version` +1 + 记 `CHANGELOG.md` + **重跑三代评测并更新基线 hash**。契约变更后 v0/v1/v2 需在同一口径下重测，否则代际增量 Δ 失去可比性。

## 如何校验

```bash
python docs/contracts/validate_contracts.py
```

零第三方依赖（标准库实现的 JSON Schema 子集），退出码 0 表示全部通过。W7 接 CI 后，schema 变更自动触发校验。

## v1.1.0 待演进（接入 Nexent 时）

Asset Card 的 `source(uri/page/sha256)`、`confidence`、`version`；trace 的 `tool_calls[]`、`evidence_ids[]`、`graph_path`、`model_version`；`eval_split` 落盘为实际配置文件。升级时同步修改 schema、PoC 与本 README。
