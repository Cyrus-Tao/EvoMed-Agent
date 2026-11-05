# -*- coding: utf-8 -*-
"""
评测模块：7 项指标

  1. Accuracy              整体准确率
  2. Macro-P               宏平均精确率
  3. Macro-R               宏平均召回率
  4. Macro-F1              宏平均 F1
  5. evidence_hit_rate     证据召回命中率：Top-K 证据中命中正确疾病的比例
  6. traceable_rate        证据可溯率：决策链完整且结论步骤挂载证据来源的比例
  7. avg_latency_ms        单样本端到端时延

另计：alignment_accuracy（本体对齐准确率）、skill_reuse_rate（Skill 复用率）
"""
from collections import Counter


def _per_class(y_true, y_pred, labels):
    stats = {}
    for d in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == d and p == d)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != d and p == d)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == d and p != d)
        stats[d] = (tp, fp, fn)
    return stats


def evaluate(traces, labels=None, verbose=False):
    n = len(traces)
    if n == 0:
        return {}

    y_true = [t["gold"] for t in traces]
    y_pred = [t["conclusion"] for t in traces]
    labels = labels or sorted(set(y_true) | set(y_pred))

    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / float(n)

    # 有效作答准确率：低置信度拒答的样本转人工，不计入自动判定
    # 全部拒答时该指标无定义，返回 None（呈现为 n/a）
    answered = [(t, p) for t, p, tr in zip(y_true, y_pred, traces) if not tr.get("rejected")]
    acc_answered = (sum(1 for t, p in answered if t == p) / float(len(answered))
                    if answered else None)

    stats = _per_class(y_true, y_pred, labels)
    ps, rs, f1s = [], [], []
    for d, (tp, fp, fn) in stats.items():
        p = tp / float(tp + fp) if (tp + fp) else 0.0
        r = tp / float(tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        ps.append(p); rs.append(r); f1s.append(f)
    macro_p = sum(ps) / len(ps)
    macro_r = sum(rs) / len(rs)
    macro_f1 = sum(f1s) / len(f1s)

    # 证据召回命中率
    hit = 0
    for t in traces:
        ev = t.get("evidence", [])
        if ev and any(e.get("disease") == t["gold"] for e in ev):
            hit += 1
    ev_hit = hit / float(n)

    # 证据可溯率
    from .trace import TraceRecorder
    traceable = sum(1 for t in traces if TraceRecorder.is_traceable(t)) / float(n)

    latency = sum(t.get("latency_ms", 0) for t in traces) / float(n)
    rejected = sum(1 for t in traces if t.get("rejected")) / float(n)

    res = {
        "n_samples": n,
        "accuracy": round(acc, 4),
        "accuracy_answered": (round(acc_answered, 4) if acc_answered is not None else None),
        "macro_p": round(macro_p, 4),
        "macro_r": round(macro_r, 4),
        "macro_f1": round(macro_f1, 4),
        "evidence_hit_rate": round(ev_hit, 4),
        "traceable_rate": round(traceable, 4),
        "avg_latency_ms": round(latency, 2),
        "reject_rate": round(rejected, 4),
    }
    if verbose:
        res["per_class"] = {d: {"tp": v[0], "fp": v[1], "fn": v[2]} for d, v in stats.items()}
        res["confusion_top"] = Counter(
            "%s->%s" % (t, p) for t, p in zip(y_true, y_pred) if t != p).most_common(5)
    return res


def delta(a, b):
    """代际增量 Δ = b - a"""
    keys = ["accuracy", "macro_p", "macro_r", "macro_f1", "evidence_hit_rate", "traceable_rate"]
    return {k: round(b.get(k, 0) - a.get(k, 0), 4) for k in keys if k in a and k in b}
