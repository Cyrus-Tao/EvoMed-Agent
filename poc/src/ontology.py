# -*- coding: utf-8 -*-
"""
L1 本体演化层：低资源半自动领域本体构建 + 一致性校验 + 增量更新

对应赛题任务 ②。
流程：术语抽取 -> 关系候选生成 -> 标准对齐（接口保留）-> 人工审核 -> SHACL 式校验 -> 版本化

PoC 阶段标准对齐（DOID / MONDO / ICD-10）保留接口并置为 pending，
不编造任何标准编码；正式构建在 W3-W4 用 OntoAligner 完成。
"""
import json
import os
from collections import defaultdict


class Ontology:
    def __init__(self, version="0.1.0"):
        self.version = version
        self.classes = {}          # class_id -> {label, synonyms, std_refs}
        self.symptoms = set()      # 症状术语表
        self.has_symptom = defaultdict(set)   # class_id -> {symptom}
        self.symptom_df = defaultdict(int)    # symptom -> 出现在多少个疾病中
        self.history = []          # 演化历史
        self.align_log = []        # 标准对齐记录

    # ---------- 构建 ----------
    def extract_terms(self, cases, guidelines):
        """术语抽取：从病例主诉与指南文本中收集症状术语"""
        for g in guidelines:
            for s in g.get("symptoms", []):
                self.symptoms.add(s)
        for c in cases:
            for s in c.get("main_symptoms", []):
                self.symptoms.add(s)

    def build_from(self, cases, guidelines, n_seed_symptoms=3):
        """
        关系候选生成：疾病 -[has_symptom]-> 症状

        关键设定：低资源条件下初始本体只从指南中抽取前 n 个症状（默认 3 个），
        刻意保持「不完备」——这正是本任务的前提：本体靠后续反馈增量演化补全，
        而不是一次性构建完整。若初始即全量，进化闭环将无从体现。
        """
        self.extract_terms(cases, guidelines)
        for g in guidelines:
            cid = g["disease_id"]
            self.classes[cid] = {
                "label": g["disease"],
                "synonyms": [],
                "std_refs": {"doid": None, "mondo": None, "icd10": None},
                "align_status": "pending",
            }
            for s in g.get("symptoms", [])[:n_seed_symptoms]:
                self.has_symptom[cid].add(s)
        self._refresh_df()
        self.history.append({"version": self.version, "action": "initial_build",
                             "n_classes": len(self.classes), "n_relations": self.n_relations()})
        return self

    def _refresh_df(self):
        self.symptom_df = defaultdict(int)
        for cid, syms in self.has_symptom.items():
            for s in syms:
                self.symptom_df[s] += 1

    def n_relations(self):
        return sum(len(v) for v in self.has_symptom.values())

    def idf(self, symptom):
        """症状特异性：出现在越少疾病中的症状越具鉴别力"""
        df = self.symptom_df.get(symptom, 1)
        n = max(1, len(self.classes))
        return 1.0 + (n - df) / float(n)

    def label_of(self, cid):
        return self.classes.get(cid, {}).get("label", cid)

    def cid_of(self, label):
        for cid, c in self.classes.items():
            if c["label"] == label:
                return cid
        return None

    # ---------- 标准对齐（接口保留） ----------
    def align_to_standard(self, mapping):
        """
        mapping: {class_label: {"doid": "...", "icd10": "..."}}
        正式实现调用 OntoAligner；此处只接受显式传入的映射，不做任何猜测。
        """
        n_aligned = 0
        for label, refs in mapping.items():
            cid = self.cid_of(label)
            if cid is None:
                continue
            self.classes[cid]["std_refs"].update(refs)
            self.classes[cid]["align_status"] = "aligned"
            self.align_log.append({"class_id": cid, "label": label, "refs": refs})
            n_aligned += 1
        return n_aligned

    def alignment_accuracy(self):
        """本体对齐准确率：已对齐类 / 全部类（评测指标之一）"""
        if not self.classes:
            return 0.0
        aligned = sum(1 for c in self.classes.values() if c.get("align_status") == "aligned")
        return aligned / float(len(self.classes))

    # ---------- 增量更新（进化闭环） ----------
    def update_from_feedback(self, feedbacks):
        """
        反馈回流：把人工纠正得到的新的「疾病-症状」关联写回本体，版本 +1。
        feedbacks: [{"disease": "...", "symptoms": [...]}]
        """
        added = 0
        for fb in feedbacks:
            cid = self.cid_of(fb["disease"])
            if cid is None:
                continue
            for s in fb.get("symptoms", []):
                if s not in self.has_symptom[cid]:
                    self.has_symptom[cid].add(s)
                    self.symptoms.add(s)
                    added += 1
        if added:
            self._refresh_df()
            major, minor, patch = (int(x) for x in self.version.split("."))
            self.version = "%d.%d.%d" % (major, minor + 1, patch)
            self.history.append({"version": self.version, "action": "feedback_update",
                                 "added_relations": added, "n_relations": self.n_relations()})
        return added

    # ---------- SHACL 式一致性校验 ----------
    def validate(self, min_symptoms=3):
        """返回 (passed, issues)。模拟 pySHACL 的约束检查。"""
        issues = []
        labels = [c["label"] for c in self.classes.values()]
        dup = {l for l in labels if labels.count(l) > 1}
        if dup:
            issues.append("类标签重复: %s" % sorted(dup))
        for cid, c in self.classes.items():
            if not cid.startswith("MEDONT:"):
                issues.append("类 ID 格式不合规: %s" % cid)
            if len(self.has_symptom.get(cid, ())) < min_symptoms:
                issues.append("类 %s(%s) 的 has_symptom 少于 %d 条" % (cid, c["label"], min_symptoms))
        return (len(issues) == 0), issues

    # ---------- 序列化 ----------
    def to_dict(self):
        return {
            "version": self.version,
            "classes": self.classes,
            "relations": [
                {"subject": cid, "predicate": "has_symptom", "object": s}
                for cid, syms in self.has_symptom.items() for s in sorted(syms)
            ],
            "history": self.history,
        }

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return path


def load_guidelines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_cases(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
