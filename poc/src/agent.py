# -*- coding: utf-8 -*-
"""
L3 检索—推理双驱决策层：AgentDiagnosis 四阶段内核

对应赛题任务 ③（核心）。四阶段严格复现论文框架：
  S1 初始诊断   -> 无证据基线推理
  S2 四步 CoT   -> 症状抽取 / 疾病关联 / 鉴别诊断 / 初步结论
  S3 RAG 增强   -> 检索证据注入 + 重推理（论文结论：这一阶段增益最大）
  S4 决策融合   -> 多策略投票 + 四维置信度 + 低置信度拒答

配置开关决定「用不用本体 / 用不用检索 / 走不走 CoT」，
从而构成 v0 / v1 / v2 三代对照实验。
"""
from .trace import TraceRecorder

REJECT_THRESHOLD = 0.35   # 低于该置信度则拒答，转人工


class DiagnosisAgent:
    def __init__(self, llm, retriever=None, ontology=None, config=None, disease_pool=None):
        self.llm = llm
        self.retriever = retriever
        self.ontology = ontology
        self.disease_pool = disease_pool or {}
        self.config = config or {}
        self.skill_calls = []      # 记录 Skill 复用情况

    def _use(self, key):
        return bool(self.config.get(key, False))

    def _symptoms_of(self, case):
        return case.get("main_symptoms") or case.get("symptoms") or []

    # ---------------- 四阶段 ----------------
    def run(self, case):
        symptoms = self._symptoms_of(case)
        onto = self.ontology if self._use("use_ontology") else None
        rec = TraceRecorder(case["id"], self.config.get("version", "v?"),
                            onto.version if onto else "none")

        cid = case["id"]
        # ---- S1 初始诊断 ----
        s1 = self.llm.diagnose(symptoms, evidence=[], ontology=onto,
                               disease_pool=self.disease_pool, case_id=cid)
        rec.add("S1_初始诊断", "llm.diagnose",
                {"symptoms": symptoms, "evidence": []},
                {"conclusion": s1["conclusion"], "candidates": s1["candidates"][:2]},
                s1["confidence"])

        # ---- S2 四步思维链 ----
        s2_out = s1
        if self._use("use_cot"):
            chain = self._chain_of_thought(symptoms, onto)
            s2 = self.llm.diagnose(chain["associated_symptoms"] or symptoms,
                                   evidence=[], ontology=onto,
                                   disease_pool=self.disease_pool, case_id=cid)
            s2_out = s2
            rec.add("S2_四步CoT", "skill.S2_chain_of_thought",
                    {"symptoms": symptoms},
                    {"chain": chain, "conclusion": s2["conclusion"]},
                    s2["confidence"])
            self.skill_calls.append("S2_chain_of_thought")

        # ---- S3 RAG 增强 ----
        evidence = []
        s3_out = s2_out
        if self._use("use_retrieval") and self.retriever is not None:
            evidence = self.retriever.retrieve(
                symptoms, top_k=self.config.get("top_k", 3),
                use_expansion=self._use("use_ontology"))
            s3 = self.llm.diagnose(symptoms, evidence=evidence, ontology=onto,
                                   disease_pool=self.disease_pool, case_id=cid)
            s3_out = s3
            rec.add("S3_RAG增强", "mcp.graph_retriever + llm.diagnose",
                    {"symptoms": symptoms,
                     "evidence_ids": [e["doc_id"] for e in evidence],
                     "evidence": [{"doc_id": e["doc_id"], "disease": e["disease"],
                                   "score": e["score"]} for e in evidence]},
                    {"conclusion": s3["conclusion"], "candidates": s3["candidates"][:3]},
                    s3["confidence"])
            self.skill_calls.append("S3_multi_hop_evidence")

        # ---- S4 决策融合 ----
        fused = self._fuse(s1, s2_out, s3_out, evidence, symptoms, onto)
        rec.add("S4_决策融合", "skill.S4_decision_fusion",
                {"s1": s1["conclusion"], "s2": s2_out["conclusion"],
                 "s3": s3_out["conclusion"],
                 "evidence_ids": [e["doc_id"] for e in evidence]},
                {"conclusion": fused["conclusion"], "confidence": fused["confidence"]},
                fused["confidence"])
        self.skill_calls.append("S4_decision_fusion")

        latency_ms = 0  # mock 推理器不采集真实时延（见 README §3），保证产物可复现
        trace = rec.finalize(fused["conclusion"], case["disease"],
                             fused["confidence"], latency_ms)
        trace["evidence"] = evidence
        trace["rejected"] = fused.get("rejected", False)
        return trace

    def _chain_of_thought(self, symptoms, onto):
        """四步 CoT：抽取 -> 关联 -> 鉴别 -> 结论"""
        extracted = list(dict.fromkeys(symptoms))
        associated, candidates = [], []
        if onto is not None:
            for s in extracted:
                for cid, syms in onto.has_symptom.items():
                    if s in syms:
                        if cid not in candidates:
                            candidates.append(cid)
                        associated.extend([x for x in syms if x not in extracted])
        # 鉴别：按 idf 排序，特异性高的症状优先
        if onto is not None:
            extracted_sorted = sorted(extracted, key=lambda s: -onto.idf(s))
        else:
            extracted_sorted = extracted
        return {
            "step1_extract": extracted_sorted,
            "step2_associate": list(dict.fromkeys(associated))[:8],
            "step3_differential": [onto.label_of(c) for c in candidates[:4]] if onto else [],
            "associated_symptoms": extracted_sorted + list(dict.fromkeys(associated))[:4],
        }

    def _fuse(self, s1, s2, s3, evidence, symptoms, onto):
        """多策略投票融合：S1/S2/S3 各一票，有证据时 S3 权重更高"""
        votes = {}
        for name, out, w in (("S1", s1, 1.0), ("S2", s2, 1.0), ("S3", s3, 2.0 if evidence else 1.0)):
            d = out.get("conclusion")
            if d:
                votes[d] = votes.get(d, 0.0) + w
        ranked = sorted(votes.items(), key=lambda kv: -kv[1])
        conclusion = ranked[0][0] if ranked else (s1.get("conclusion") or "")
        conf = s3["confidence"] if evidence else s1["confidence"]
        return {
            "conclusion": conclusion,
            "votes": dict(ranked),
            "confidence": conf,
            "rejected": conf.get("overall", 0.0) < REJECT_THRESHOLD,
        }
