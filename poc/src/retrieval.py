# -*- coding: utf-8 -*-
"""
L2 图谱增强检索层：双路召回 + 本体约束扩展 + 证据合并

对应赛题任务 ④ 前段（跨文档多跳检索）。
两路召回：
  - 稀疏路：BM25（对症状词这类术语型查询最稳）
  - 稠密路：字符 bigram TF-IDF 余弦（模拟向量召回，无需外部模型）
本体约束：用 has_symptom 关系做查询扩展（同病种共现症状），实现「图谱式」多跳。

真实系统中稠密路替换为 all-MiniLM-L6-v2 / FAISS IVF_FLAT，
图谱路替换为 LightRAG / HippoRAG；接口保持不变。
"""
import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[\u4e00-\u9fa5a-zA-Z0-9]+")


def tokenize(text):
    """中文按字 + 术语词切分：先整词，再补字符 bigram 提升召回"""
    words = TOKEN_RE.findall(text)
    grams = []
    for w in words:
        if re.search(r"[\u4e00-\u9fa5]", w):
            if len(w) == 1:
                grams.append(w)
            else:
                grams.extend([w[i:i + 2] for i in range(len(w) - 1)])
        else:
            grams.append(w.lower())
    return words + grams


class Doc:
    """检索单元：一条证据"""
    __slots__ = ("doc_id", "text", "disease", "disease_id", "source", "tokens", "tf")

    def __init__(self, doc_id, text, disease, disease_id, source):
        self.doc_id = doc_id
        self.text = text
        self.disease = disease
        self.disease_id = disease_id
        self.source = source
        self.tokens = tokenize(text)
        self.tf = Counter(self.tokens)

    def __repr__(self):
        return "<Doc %s %s>" % (self.doc_id, self.disease)


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.avgdl = sum(len(d.tokens) for d in docs) / max(1, self.n)
        self.df = Counter()
        for d in docs:
            for t in set(d.tokens):
                self.df[t] += 1
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in self.df.items()}

    def scores(self, query_tokens):
        out = []
        qc = Counter(query_tokens)
        for d in self.docs:
            s = 0.0
            dl = len(d.tokens)
            for t, qn in qc.items():
                f = d.tf.get(t, 0)
                if f == 0:
                    continue
                idf = self.idf.get(t, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / max(1e-9, self.avgdl))
                s += idf * (f * (self.k1 + 1)) / denom
            out.append(s)
        return out


class TfidfVector:
    """轻量稠密路：字符 bigram TF-IDF 余弦"""
    def __init__(self, docs):
        self.docs = docs
        self.n = len(docs)
        self.df = Counter()
        for d in docs:
            for t in set(d.tokens):
                self.df[t] += 1
        self.idf = {t: math.log(1 + self.n / (c + 1)) for t, c in self.df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, d):
        v = {}
        norm = 0.0
        for t, f in d.tf.items():
            w = (1 + math.log(f)) * self.idf.get(t, 0.0)
            v[t] = w
            norm += w * w
        norm = math.sqrt(norm) or 1.0
        return {t: w / norm for t, w in v.items()}

    def _qvec(self, tokens):
        tf = Counter(tokens)
        v, norm = {}, 0.0
        for t, f in tf.items():
            w = (1 + math.log(f)) * self.idf.get(t, 0.0)
            v[t] = w
            norm += w * w
        norm = math.sqrt(norm) or 1.0
        return {t: w / norm for t, w in v.items()}

    def scores(self, query_tokens):
        q = self._qvec(query_tokens)
        out = []
        for v in self.vecs:
            s = sum(w * v.get(t, 0.0) for t, w in q.items())
            out.append(s)
        return out


class HybridRetriever:
    """双路召回 + 本体约束扩展 + 证据合并（去重 / 排序 / 冲突消解）"""
    def __init__(self, docs, ontology=None, w_sparse=0.6, w_dense=0.4):
        self.docs = docs
        self.ontology = ontology
        self.w_sparse, self.w_dense = w_sparse, w_dense
        self.bm25 = BM25(docs)
        self.vec = TfidfVector(docs)

    def expand_query(self, symptoms):
        """本体约束的图谱式扩展：把查询症状映射到共享该症状的病种的其他典型症状"""
        if not self.ontology:
            return list(symptoms)
        extra = set()
        for s in symptoms:
            for cid, syms in self.ontology.has_symptom.items():
                if s in syms:
                    # 按术语字典序取前 3，避免 set 迭代顺序随 PYTHONHASHSEED / Python 版本变化
                    extra.update(sorted(syms)[:3])
        merged = list(dict.fromkeys(list(symptoms) + sorted(extra)))
        return merged[:12]

    def retrieve(self, symptoms, top_k=3, use_expansion=True):
        q_terms = self.expand_query(symptoms) if (use_expansion and self.ontology) else list(symptoms)
        q_tokens = []
        for t in q_terms:
            q_tokens.extend(tokenize(t))
        ss = self.bm25.scores(q_tokens)
        ds = self.vec.scores(q_tokens)
        m1, m2 = max(ss) or 1.0, max(ds) or 1.0
        fused = [self.w_sparse * (s / m1) + self.w_dense * (d / m2) for s, d in zip(ss, ds)]
        order = sorted(range(len(self.docs)), key=lambda i: -fused[i])[:top_k]
        evidence = []
        for i in order:
            d = self.docs[i]
            evidence.append({
                "doc_id": d.doc_id,
                "disease": d.disease,
                "disease_id": d.disease_id,
                "text": d.text,
                "source": d.source,
                "score": round(fused[i], 4),
                "sparse": round(ss[i], 4),
                "dense": round(ds[i], 4),
            })
        return evidence

    @staticmethod
    def merge(evidence_list):
        """证据合并：按 disease 聚合，冲突时取高分证据"""
        bucket = {}
        for e in evidence_list:
            k = e["disease"]
            if k not in bucket or e["score"] > bucket[k]["score"]:
                bucket[k] = e
        return sorted(bucket.values(), key=lambda x: -x["score"])


def build_docs(guidelines, cases):
    """
    构建检索库：指南片段 + 病例（病例作为「过往相似病例」证据）
    对应 L0 输出的可检索切片进入知识库。
    """
    docs = []
    for g in guidelines:
        docs.append(Doc(g["id"], g["text"], g["disease"], g["disease_id"], "指南库"))
    for c in cases:
        docs.append(Doc(c["id"], c["text"], c["disease"], c["disease_id"], "病历库"))
    return docs
