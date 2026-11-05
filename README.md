# EvoMed-Agent

> 第十一届华为 ICT 大赛（中国赛·创新赛）赛题 3 · 基于华为 ModelEngine Nexent 打造可进化决策智能体
> 参赛单位：苏州大学 ｜ 队名：**衍医队**

把医院里「沉睡」的多模态资产变成可溯源、可进化、能支撑临床决策的智能体。平台锁定 **ModelEngine Nexent v2.7.0（MIT）**，全部能力通过 SDK / MCP / Skill 三通道外挂注入，**不改平台内核**。

## 当前状态

| 项 | 状态 |
| --- | --- |
| 数据契约 | **v1.0.0 已冻结**（2026-11-04，本地 tag `contracts-v1.0.0`） |
| 最小原型 | `poc/` 离线可复现，零第三方依赖，9/9 契约校验通过 |
| 平台接入 | W7 接入 Nexent；本仓库目前不含平台侧代码 |
| 开源发布 | W8 前完成二次许可核验，进度见 `NOTICE` |

> 这是**开发中的参赛仓库**，不是可部署的医疗系统。PoC 使用合成数据与 mock 推理器，所有结论仅用于验证技术假设，**不可用于任何临床用途**。

## 快速开始

需要 Python 3.9+，无需安装依赖、无需 GPU、无需 API Key。

```bash
python poc/run_poc.py                        # 跑三代对照实验
python docs/contracts/validate_contracts.py # 校验 4 份数据契约
```

期望输出 `9 项校验，9 项通过，0 项失败`。`validate_contracts.py` 用标准库实现 JSON Schema 子集，读取 `poc/out/` 下 9 个 JSON 产物，**该目录必须随仓库保留**。

PoC 入口强制 `PYTHONHASHSEED=0` 并重启自身，查询扩展按术语字典序做确定性 tie-break，因此 `poc/out/` 全产物连跑两次完全一致（`avg_latency_ms` 固定为 0 —— mock 推理器的毫秒数无意义）。详见 `poc/README.md`。

## 目录结构

```
EvoMed-Agent/
├── LICENSE                        Apache-2.0 全文
├── NOTICE                         第三方资产与合规声明
├── README.md
├── docs/
│   ├── 04-参考资料清单.md           数据 / 代码 / 开源项目来源与许可证核验状态
│   ├── ICD10_SOURCE.md             ICD-10 来源与「不分发完整码表」说明
│   └── contracts/
│       ├── asset_card.schema.json
│       ├── ontology.schema.json
│       ├── trace.schema.json
│       ├── eval_split.schema.json
│       ├── README.md               决策记录 D-001/002/003 与变更规则
│       ├── CHANGELOG.md
│       └── validate_contracts.py   零依赖校验器
└── poc/
    ├── run_poc.py
    ├── src/  data/  README.md
    └── out/                        9 个 JSON 产物（契约校验数据源）
```

## 架构与评测口径

五层逐层对应赛题任务 ①~⑤：

| 层 | 内容 |
| --- | --- |
| L0 | 多模态资产认知 → Asset Card（`source` / `confidence` / `version`） |
| L1 | 本体演化：术语抽取 → 关系候选 → SHACL 式校验 → 版本化 |
| L2 | 图谱增强检索 |
| L3 | 检索—推理双驱决策（复用团队论文 AgentDiagnosis 四阶段框架） |
| L4 | trace 溯源 + 反馈回流 → 本体增量 → 版本演进 |

**评测看代际增量 Δ，不看绝对 Accuracy**（10 分类随机基线 10%，绝对值没有竞争力）。PoC 用 15 条测试集 / 15 条反馈集，二者不重叠：

| 指标 | v0 基线 | v1 +本体+RAG | v2 +反馈进化 |
| --- | --- | --- | --- |
| Accuracy | 0.2667 | 0.9333 | 1.0000 |
| Macro-F1 | 0.1900 | 0.8800 | 1.0000 |
| 证据召回命中率 | 0.0000 | 1.0000 | 0.9333 |
| 证据可溯率 | 0.0000 | 1.0000 | 1.0000 |

KV-1~4 四项关键技术验证全部通过，Δ(v2−v1) Accuracy = **+0.0667**。契约变更需在同一口径下重跑三代评测并更新基线 hash。

## 数据契约

`docs/contracts/` 下 4 份 schema 是三人并行开发的接口约定，**契约先于代码**：

- `std_refs` 固定 `doid` / `mondo` / `icd10`，`additionalProperties: false`；写 `icd11` 会直接校验失败（D-001）。
- `eval_split` 要求 `python_hash_seed = 0`，测试集与反馈集必须不相交。
- 改字段 = 提 PR + 三人通过 + 版本号 +1 + 记 `CHANGELOG.md` + 重跑三代评测；接入 Nexent 后升 v1.1.0，补 `graph_path` / `model_version` 等字段。

完整决策记录见 [`docs/contracts/README.md`](docs/contracts/README.md)。

## 数据与合规

- **不随仓库分发完整 ICD-10 码表**。四份候选版本均未授予再分发许可；对齐目标为《疾病分类与代码国家临床版 2.0（2022 汇总版）》，仓库内只留来源说明与评测所需最小映射子集，主对齐标准为 DOID（CC0）。见 `docs/ICD10_SOURCE.md` 与 `NOTICE`（D-003）。
- PoC 数据由 `poc/data/gen_data.py` 固定种子 20261016 合成，**不含真实患者信息**，可开源。
- 明确禁用：MIMIC 系列、SNOMED CT、UMLS、来源不明的中文医学知识图谱。许可待核项在核验完成前不入库，见 `docs/04-参考资料清单.md` 与 `NOTICE`。
- 使用者自行从官方渠道下载的完整码表放 `data/external/`（已在 `.gitignore` 中）。

## 许可证与仓库

自研代码 **Apache-2.0**（见 `LICENSE`）；与 MIT 项目深度耦合的模块沿用 MIT。第三方资产逐条列于 `NOTICE`。

- 主仓（大赛指定）：GitCode `https://gitcode.com/gcw_Kp5PCUeQ/EvoMed-Agent.git`
- 镜像：GitHub `https://github.com/Cyrus-Tao/EvoMed-Agent.git`
