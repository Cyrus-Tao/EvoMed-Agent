# -*- coding: utf-8 -*-
"""
L4 溯源进化层：决策链 trace.json 落盘

对应赛题任务 ④ 后段（可溯源决策链）。
每一步决策记录：输入证据、工具调用、中间结论、置信度、本体版本，
使整条决策链可回放、可审计、可复现。
"""
import json
import os

# 离线 mock 产物使用固定时间戳，保证产物可复现；
# W7 接入真实模型运行时改回 datetime.now().isoformat(timespec="seconds")。
MOCK_TS = "2026-10-16T00:00:00"


class TraceRecorder:
    def __init__(self, case_id, config_version, ontology_version):
        self.case_id = case_id
        self.config_version = config_version
        self.ontology_version = ontology_version
        self.steps = []
        self.started_at = MOCK_TS

    def add(self, stage, tool, inputs, outputs, confidence=None):
        self.steps.append({
            "step": len(self.steps) + 1,
            "stage": stage,
            "tool": tool,
            "inputs": inputs,
            "outputs": outputs,
            "confidence": confidence,
            "at": MOCK_TS,
        })

    def finalize(self, conclusion, gold, confidence, latency_ms):
        self.finished_at = MOCK_TS
        return {
            "trace_id": "TRACE-%s-%s" % (self.case_id, self.config_version),
            "case_id": self.case_id,
            "config_version": self.config_version,
            "ontology_version": self.ontology_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "latency_ms": latency_ms,
            "steps": self.steps,
            "conclusion": conclusion,
            "gold": gold,
            "correct": conclusion == gold,
            "final_confidence": confidence,
        }

    @staticmethod
    def is_traceable(trace):
        """证据可溯率判定：每个产生结论的步骤都必须挂上证据来源或明确标注无证据"""
        for s in trace["steps"]:
            if s["stage"] in ("S3_RAG增强", "S4_决策融合"):
                if "evidence_ids" not in str(s["inputs"]) and "evidence" not in str(s["inputs"]).lower():
                    return False
        return len(trace["steps"]) >= 3

    @staticmethod
    def save(trace, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
        return path
