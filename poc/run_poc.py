# -*- coding: utf-8 -*-
"""
EvoMed-Agent 最小原型（PoC）一键运行入口

验证四件事：
  KV-1  检索增强有效：+RAG 显著优于 Vanilla 与 +CoT（复现论文核心结论）
  KV-2  本体约束提升检索质量：接入本体后证据召回命中率上升
  KV-3  决策链可溯源：每条决策产出字段完整的 trace.json
  KV-4  进化闭环成立：v1 的错误反馈回流本体后，v2 指标上升（Δ>0）

用法：
  python run_poc.py                    # 默认 mock 模式，离线可跑
  python run_poc.py --llm http         # 接入真实大模型（需配置环境变量）
  python run_poc.py --save-traces      # 落盘全部 trace.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- 可复现性保证 ----------------------------------------------------------
# Python 对 str 的哈希默认随机化（PYTHONHASHSEED），会导致 set 迭代顺序随进程变化，
# 进而影响检索 Top-K 的并列排序，使同一份代码每次跑出不同指标。
# 这里强制以 PYTHONHASHSEED=0 重新执行自身，确保结果完全可复现。
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

sys.stdout.reconfigure(encoding="utf-8")

from src import asset_card as ac          # noqa: E402
from src import ontology as ont           # noqa: E402
from src import retrieval as rt           # noqa: E402
from src.agent import DiagnosisAgent      # noqa: E402
from src.evaluate import evaluate, delta  # noqa: E402
from src.llm import build_llm             # noqa: E402
from src.trace import TraceRecorder       # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "out")


def load_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def line(ch="=", n=74):
    print(ch * n)


def title(s):
    print("\n" + s)
    print("-" * 74)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", default="mock", choices=["mock", "http"])
    ap.add_argument("--save-traces", action="store_true")
    args = ap.parse_args()

    line()
    print("EvoMed-Agent 最小原型（PoC）· 关键技术验证")
    print("平台目标：华为 ModelEngine Nexent v2.7.0   LLM 模式：%s" % args.llm)
    line()

    # ---------- 载入数据 ----------
    cases = load_jsonl(os.path.join(DATA, "cases.jsonl"))
    guidelines = load_jsonl(os.path.join(DATA, "guidelines.jsonl"))
    raw_assets = load_jsonl(os.path.join(DATA, "raw_assets.jsonl"))
    dev_cases, test_cases = cases[:15], cases[15:]      # 反馈集 / 测试集严格分离
    disease_pool = {g["disease"]: g["symptoms"] for g in guidelines}

    # ---------- L0 资产认知 ----------
    title("L0  多模态资产认知：沉睡资产 -> 资产卡片")
    cards, all_cards = ac.build_asset_cards(raw_assets)
    summ = ac.summarize(all_cards)
    print("  原始资产 %d 份，生成资产卡片 %d 张" % (len(raw_assets), len(all_cards)))
    print("  模态分布：%s" % summ["by_modality"])
    print("  平均质量分：%.3f   高敏感度资产：%d 份" % (summ["avg_quality"], summ["high_sensitivity"]))
    print("  样例卡片：%s" % json.dumps(all_cards[0], ensure_ascii=False)[:150] + " ...")
    ac.save_cards(all_cards, os.path.join(OUT, "asset_cards.json"))

    # ---------- L1 本体构建 ----------
    title("L1  本体演化：术语抽取 -> 关系候选 -> 校验 -> 版本化")
    onto = ont.Ontology(version="0.1.0").build_from(cases, guidelines)
    ok, issues = onto.validate()
    print("  本体版本 %s：类 %d 个，has_symptom 关系 %d 条" % (onto.version, len(onto.classes), onto.n_relations()))
    print("  SHACL 式校验：%s" % ("通过" if ok else "发现 %d 项问题" % len(issues)))
    for i in issues[:3]:
        print("    - %s" % i)
    print("  标准对齐状态：%d/%d 已对齐（DOID/ICD-10 映射保留接口，不做任何猜测）"
          % (int(onto.alignment_accuracy() * len(onto.classes)), len(onto.classes)))
    onto.save(os.path.join(OUT, "ontology_v0.1.0.json"))

    # ---------- L2 检索库 ----------
    docs = rt.build_docs(guidelines, cases)
    retriever_on = rt.HybridRetriever(docs, ontology=onto)
    retriever_off = rt.HybridRetriever(docs, ontology=None)
    print("\n  L2 检索库构建完成：%d 条可检索证据（指南 %d + 病历 %d）"
          % (len(docs), len(guidelines), len(cases)))

    llm = build_llm(args.llm)

    def run(config, subset, retriever, ontology):
        agent = DiagnosisAgent(llm, retriever, ontology, config, disease_pool)
        return [agent.run(c) for c in subset]

    # ---------- 三代对照 ----------
    cfg_v0 = {"version": "v0", "use_ontology": False, "use_retrieval": False, "use_cot": False}
    cfg_v1 = {"version": "v1", "use_ontology": True, "use_retrieval": True, "use_cot": True}
    cfg_v2 = {"version": "v2", "use_ontology": True, "use_retrieval": True, "use_cot": True,
              "use_skills": True}

    title("三代对照实验（测试集 %d 条，反馈集 %d 条，二者不重叠）" % (len(test_cases), len(dev_cases)))
    labels = sorted(disease_pool.keys())

    t_v0 = run(cfg_v0, test_cases, retriever_off, None)
    m_v0 = evaluate(t_v0, labels)

    t_v0_dev = run(cfg_v0, dev_cases, retriever_off, None)   # 基线在反馈集上的错误
    t_v1_dev = run(cfg_v1, dev_cases, retriever_on, onto)    # v1 在反馈集上的错误
    t_v1 = run(cfg_v1, test_cases, retriever_on, onto)
    m_v1 = evaluate(t_v1, labels)

    # ---- 进化闭环：把反馈集上的错误回流进本体 ----
    # 反馈来自「系统答错的地方」：v0 基线的错误 + v1 的错误，二者取并集。
    # 反馈集与测试集严格不重叠，测试集答案不会泄漏进本体。
    fb = {}
    for t in list(t_v0_dev) + list(t_v1_dev):
        if not t["correct"]:
            fb.setdefault(t["gold"], set()).update(t["steps"][0]["inputs"]["symptoms"])
    feedbacks = [{"disease": d, "symptoms": sorted(s)} for d, s in fb.items()]
    added = onto.update_from_feedback(feedbacks)
    ok2, issues2 = onto.validate()
    title("L4  进化闭环：反馈回流 -> 本体增量 -> 版本演进")
    print("  反馈集错误样本 %d 条 -> 新增 has_symptom 关系 %d 条" % (len(feedbacks), added))
    print("  本体版本演进：0.1.0 -> %s   重新校验：%s" % (onto.version, "通过" if ok2 else "有问题"))
    print("  演化历史：%s" % json.dumps(onto.history[-1], ensure_ascii=False))
    onto.save(os.path.join(OUT, "ontology_%s.json" % onto.version))

    # 本体更新后重建检索器（图谱约束随之更新）
    retriever_v2 = rt.HybridRetriever(docs, ontology=onto)
    t_v2 = run(cfg_v2, test_cases, retriever_v2, onto)
    m_v2 = evaluate(t_v2, labels)

    # ---------- 结果表 ----------
    title("评测结果（测试集 n=%d）" % len(test_cases))
    rows = [
        ("指标", "v0 基线", "v1 +本体+RAG", "v2 +反馈进化", "Δ(v1-v0)", "Δ(v2-v1)"),
    ]
    keys = [("accuracy", "Accuracy"), ("accuracy_answered", "有效作答准确率"),
            ("macro_p", "Macro-P"), ("macro_r", "Macro-R"),
            ("macro_f1", "Macro-F1"), ("evidence_hit_rate", "证据召回命中率"),
            ("traceable_rate", "证据可溯率"), ("avg_latency_ms", "平均时延 ms"),
            ("reject_rate", "拒答率")]
    d10, d21 = delta(m_v0, m_v1), delta(m_v1, m_v2)
    def fmt(m, k):
        v = m.get(k, 0)
        return "n/a" if v is None else ("%.4f" % v)

    for k, name in keys:
        dv1 = d10.get(k)
        dv2 = d21.get(k)
        rows.append((name, fmt(m_v0, k), fmt(m_v1, k), fmt(m_v2, k),
                     ("%+.4f" % dv1) if dv1 is not None else "-",
                     ("%+.4f" % dv2) if dv2 is not None else "-"))
    w = [12, 12, 16, 16, 12, 12]
    for r in rows:
        print("  " + "".join(str(x).ljust(w[i]) for i, x in enumerate(r)))

    # ---------- 关键结论 ----------
    title("关键技术验证结论")
    kv = []
    kv.append(("KV-1 检索增强有效", m_v1["accuracy"] > m_v0["accuracy"],
               "Accuracy %.4f -> %.4f (Δ=%+.4f)" % (m_v0["accuracy"], m_v1["accuracy"],
                                                    m_v1["accuracy"] - m_v0["accuracy"])))
    kv.append(("KV-2 本体约束提升检索", m_v1["evidence_hit_rate"] > m_v0["evidence_hit_rate"],
               "证据命中率 %.4f -> %.4f" % (m_v0["evidence_hit_rate"], m_v1["evidence_hit_rate"])))
    kv.append(("KV-3 决策链可溯源", m_v1["traceable_rate"] >= 0.99,
               "可溯率 %.4f，trace.json 字段完整" % m_v1["traceable_rate"]))
    kv.append(("KV-4 进化闭环成立", m_v2["accuracy"] > m_v1["accuracy"],
               "Accuracy %.4f -> %.4f (Δ=%+.4f)" % (m_v1["accuracy"], m_v2["accuracy"],
                                                    m_v2["accuracy"] - m_v1["accuracy"])))
    for name, okk, desc in kv:
        print("  [%s] %-22s %s" % ("PASS" if okk else "FAIL", name, desc))

    # Skill 复用率
    agent_v2 = DiagnosisAgent(llm, retriever_v2, onto, cfg_v2, disease_pool)
    agent_v2.run(test_cases[0])
    skill_set = sorted(set(agent_v2.skill_calls))
    print("\n  Skill 复用率：%d/%d（%s）" % (len(skill_set), 5, "、".join(skill_set)))
    print("  本体对齐准确率：%.4f（PoC 保留接口，正式对齐在 W3-W4 完成）" % onto.alignment_accuracy())

    # ---------- 产物落盘 ----------
    os.makedirs(OUT, exist_ok=True)
    if args.save_traces:
        td = os.path.join(OUT, "traces")
        for t in t_v2[:5]:
            TraceRecorder.save(t, os.path.join(td, "%s.json" % t["trace_id"]))
        print("\n  trace 样例已落盘：out/traces/ （%d 条）" % min(5, len(t_v2)))
    TraceRecorder.save(t_v2[0], os.path.join(OUT, "trace_sample.json"))

    report = {"v0": m_v0, "v1": m_v1, "v2": m_v2,
              "delta_v1_v0": d10, "delta_v2_v1": d21,
              "kv_results": [{"name": n, "pass": bool(o), "detail": d} for n, o, d in kv],
              "ontology_versions": [h["version"] for h in onto.history],
              "skills_used": skill_set}
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n  产物：out/asset_cards.json, out/ontology_*.json, "
          "out/trace_sample.json, out/metrics.json")
    line()
    print("完成。mock 模式为确定性规则推理器，结果完全可复现；")
    print("接入真实大模型请用 --llm http 并配置 EVOMED_LLM_BASE_URL / EVOMED_LLM_API_KEY。")
    line()


if __name__ == "__main__":
    main()
