# 契约变更记录

## v1.0.0 — 2026-11-04

- 初始冻结四份契约：`asset_card` / `ontology` / `trace` / `eval_split`。
- **D-001**：标准对齐锁定 ICD-10；`std_refs` 字段固定为 `doid` / `mondo` / `icd10`，`additionalProperties: false` 禁止 `icd11`；PoC 代码与 `out/` 产物同步重生成。
- **D-002**：报名队名确定为「衍医队」，Dx³ 诊立方作废。
- **D-003**：ICD-10 对齐目标锁定《疾病分类与代码国家临床版 2.0（2022 汇总版）》；四份候选版本均未授予再分发许可，故完整码表不随仓库分发，仅保留最小映射子集；DOID（CC0）升为主对齐标准。新增 `docs/ICD10_SOURCE.md` 与 `NOTICE`，同步更新参考资料清单及其三份输出文档。**不改 schema 字段，契约仍为 v1.0.0，无需重跑三代评测。**
- 结构对齐 EvoMed-PoC 现有产物：本体顶层 `relations` 为三元组数组、`asset_cards.json` 为卡片数组、trace 的 `steps` 为七字段对象。
- 新增 `validate_contracts.py`（零第三方依赖）作为契约生效入口。
- 全项目 ICD-11 → ICD-10 口径统一，正式材料与源文件同步替换。

### 待办（v1.1.0）

- 接入 Nexent 后补齐 `source` / `graph_path` / `model_version` 等字段。
- 参考资料清单中 ICD-10 那行已按 D-003 改为「已核验来源（见注 2）」并写明不分发策略；**剩余待核的是具体发布源的下载链接、下载日期与 SHA256**，由 `docs/ICD10_SOURCE.md` 中的「待填写」字段跟踪，W8 开源前补齐。
- 其余 ⚠️ 项（Kaggle 合成集、MedQA / MedMCQA、CMB 与 MedMNIST 数据子集、MONDO、DDXPlus、ReasonMed）许可仍需逐项核验。
