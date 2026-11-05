# -*- coding: utf-8 -*-
"""
L0 多模态资产认知层：把「不可检索的文件」变成「可检索的资产」

对应赛题任务 ①。
核心产物是资产卡片（Asset Card）：为每一份异构资产生成统一的结构化描述，
使质量分与敏感度成为检索与权限控制的一等公民。

真实系统中这里会接入 Docling 做 PDF/影像解析；PoC 阶段处理
txt / md / csv 三种模态，保留完全相同的接口。
"""
import hashlib
import json
import os
import re

# 离线 mock 产物使用固定时间戳，保证产物可复现；
# W7 接入真实运行时改回 datetime.now().isoformat(timespec="seconds")。
MOCK_TS = "2026-10-16T00:00:00"

# 敏感度分级规则（真实系统应接入医院数据分级规范）
SENSITIVE_PATTERNS = ["身份证", "手机号", "姓名", "住院号", "医保"]

# 各模态的质量分计算权重
QUALITY_WEIGHTS = {
    "text": {"min_len": 10, "good_len": 40},
    "document": {"min_len": 20, "good_len": 60},
    "table": {"min_len": 20, "good_len": 50},
}


def _fingerprint(content):
    return hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]


def _quality_score(asset):
    """质量分 0-1：长度达标度 + 字段完整性 + 模态可信度"""
    content = asset.get("content", "")
    modality = asset.get("modality", "text")
    w = QUALITY_WEIGHTS.get(modality, QUALITY_WEIGHTS["text"])
    n = len(content)
    length_score = min(1.0, n / float(w["good_len"])) if n >= w["min_len"] else n / float(w["good_len"]) * 0.5
    field_score = 1.0 if all(k in asset for k in ("id", "source_system")) else 0.6
    noise_penalty = 0.1 if re.search(r"[?？]{2,}|待补充|TBD", content) else 0.0
    return round(max(0.0, min(1.0, length_score * 0.6 + field_score * 0.4 - noise_penalty)), 3)


def _sensitivity(content):
    hits = [p for p in SENSITIVE_PATTERNS if p in content]
    if len(hits) >= 2:
        return "高"
    if len(hits) == 1:
        return "中"
    return "低"


def _slice(content, size=60):
    """可检索切片：长文本按句/窗口切分，避免整篇向量化稀释语义"""
    if len(content) <= size:
        return [content]
    parts = re.split(r"(?<=[。；\n])", content)
    buf, out = "", []
    for p in parts:
        buf += p
        if len(buf) >= size:
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out or [content]


def build_asset_card(asset):
    """单份资产 -> 资产卡片"""
    content = asset.get("content", "")
    return {
        "asset_id": asset.get("id"),
        "modality": asset.get("modality", "text"),
        "ext": asset.get("ext", ".txt"),
        "source_system": asset.get("source_system", "unknown"),
        "fingerprint": _fingerprint(content),
        "quality_score": _quality_score(asset),
        "sensitivity": _sensitivity(content),
        "n_slices": len(_slice(content)),
        "slices": _slice(content),
        "indexed_at": MOCK_TS,
    }


def build_asset_cards(raw_assets, min_quality=0.0):
    """批量构建资产卡片，并按质量分过滤低质资产"""
    cards = [build_asset_card(a) for a in raw_assets]
    kept = [c for c in cards if c["quality_score"] >= min_quality]
    return kept, cards


def summarize(cards):
    """资产盘点摘要：用于 Skill S1 的输出"""
    by_modality = {}
    for c in cards:
        by_modality.setdefault(c["modality"], 0)
        by_modality[c["modality"]] += 1
    return {
        "total": len(cards),
        "by_modality": by_modality,
        "avg_quality": round(sum(c["quality_score"] for c in cards) / max(1, len(cards)), 3),
        "high_sensitivity": sum(1 for c in cards if c["sensitivity"] == "高"),
    }


def save_cards(cards, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    return path
