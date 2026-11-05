# -*- coding: utf-8 -*-
"""
L0 数据合成器：生成最小验证数据集（固定随机种子，完全可复现）

数据全部为人工编写的医学常识模板合成，不涉及任何真实患者信息，
可安全开源。用于验证 EvoMed-Agent 五层架构的关键技术假设。

产出：
  data/cases.jsonl        症状-疾病病例（30 条，10 个病种）
  data/guidelines.jsonl   临床指南片段（10 条）
  data/raw_assets.jsonl   异构原始资产（模拟沉睡数据：txt/md/csv 三种模态）
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# 10 个病种及其典型症状池（医学常识层面编写）
DISEASES = {
    "急性上呼吸道感染": ["发热", "咳嗽", "咽痛", "鼻塞", "流涕", "打喷嚏", "乏力"],
    "社区获得性肺炎": ["发热", "咳嗽", "咳脓痰", "胸痛", "气促", "寒战", "肺部湿啰音"],
    "支气管哮喘": ["发作性喘息", "胸闷", "呼吸困难", "夜间咳嗽", "哮鸣音", "过敏史"],
    "原发性高血压": ["头晕", "头痛", "颈项僵硬", "心悸", "耳鸣", "血压升高"],
    "2型糖尿病": ["多饮", "多尿", "多食", "体重下降", "乏力", "视物模糊"],
    "偏头痛": ["单侧搏动性头痛", "恶心", "呕吐", "畏光", "畏声", "视觉先兆"],
    "急性胃炎": ["上腹痛", "腹胀", "恶心", "呕吐", "嗳气", "食欲不振"],
    "胃食管反流病": ["烧心", "反酸", "胸骨后疼痛", "夜间咳嗽", "卧位加重"],
    "缺铁性贫血": ["乏力", "头晕", "面色苍白", "心悸", "活动后气促", "指甲脆裂"],
    "甲状腺功能减退症": ["乏力", "畏寒", "体重增加", "便秘", "皮肤干燥", "记忆力减退"],
}

# 每个病种的诊断要点（写入指南片段）
KEY_POINTS = {
    "急性上呼吸道感染": "起病急，以鼻咽部卡他症状为主，全身症状轻，病程自限约 5-7 天。",
    "社区获得性肺炎": "发热伴咳嗽咳痰，肺部可闻及湿啰音，影像学见实变影，需与肺结核鉴别。",
    "支气管哮喘": "反复发作性喘息，夜间及清晨加重，双肺哮鸣音，支气管舒张试验阳性。",
    "原发性高血压": "非同日三次诊室血压 ≥140/90 mmHg，需排除继发性高血压。",
    "2型糖尿病": "典型三多一少症状，空腹血糖 ≥7.0 mmol/L 或 HbA1c ≥6.5%。",
    "偏头痛": "单侧搏动性中重度头痛，伴恶心呕吐、畏光畏声，日常活动加重。",
    "急性胃炎": "起病急，上腹疼痛伴恶心呕吐，常有饮食不当或药物刺激诱因。",
    "胃食管反流病": "典型烧心与反酸，卧位及饱食后加重，内镜或 PPI 试验可支持诊断。",
    "缺铁性贫血": "乏力苍白伴心悸，血常规示小细胞低色素性贫血，铁蛋白降低。",
    "甲状腺功能减退症": "代谢率减低表现，TSH 升高伴 FT4 降低，需与亚临床甲减鉴别。",
}

# 病种内部编号（本体 ID），标准术语对齐在 W3-W4 由 OntoAligner 完成，此处保留接口
DISEASE_IDS = {name: "MEDONT:%04d" % (i + 1) for i, name in enumerate(DISEASES)}

# 干扰症状池（模拟主诉中的噪声）
NOISE_SYMPTOMS = ["食欲减退", "睡眠欠佳", "轻度水肿", "关节酸痛", "夜间盗汗"]


def build_cases(rng):
    """每个病种 3 条病例，共 30 条。症状 3-5 个，含 0-1 个干扰症状。"""
    cases = []
    idx = 0
    for disease, syms in DISEASES.items():
        for k in range(3):
            idx += 1
            n_main = rng.choice([3, 4])
            picked = rng.sample(syms, min(n_main, len(syms)))
            noise = []
            if rng.random() < 0.4:
                noise = [rng.choice(NOISE_SYMPTOMS)]
            symptoms = picked + noise
            age = rng.randint(18, 78)
            sex = rng.choice(["男", "女"])
            days = rng.randint(1, 14)
            text = ("患者，%s，%d 岁，因「%s」就诊，症状持续 %d 天。"
                    % (sex, age, "、".join(picked), days))
            if noise:
                text += "伴%s。" % noise[0]
            cases.append({
                "id": "C%03d" % idx,
                "disease": disease,
                "disease_id": DISEASE_IDS[disease],
                "age": age,
                "sex": sex,
                "symptoms": symptoms,
                "main_symptoms": picked,
                "text": text,
            })
    rng.shuffle(cases)
    return cases


def build_guidelines():
    """每个病种 1 条指南片段，共 10 条。"""
    out = []
    for i, (disease, syms) in enumerate(DISEASES.items(), start=1):
        text = ("【%s】典型表现：%s。诊断要点：%s"
                % (disease, "、".join(syms[:5]), KEY_POINTS[disease]))
        out.append({
            "id": "G%03d" % i,
            "disease": disease,
            "disease_id": DISEASE_IDS[disease],
            "symptoms": syms,
            "text": text,
            "source": "自建教学示例（依据公开医学常识编写）",
        })
    return out


def build_raw_assets(cases, guidelines):
    """模拟医院里真实存在的异构沉睡资产：txt 病历 / md 指南 / csv 检验表。"""
    assets = []
    for c in cases[:12]:
        assets.append({
            "id": "RAW-%s" % c["id"],
            "modality": "text",
            "ext": ".txt",
            "source_system": "EMR 门诊病历库",
            "content": c["text"],
        })
    for g in guidelines:
        assets.append({
            "id": "RAW-%s" % g["id"],
            "modality": "document",
            "ext": ".md",
            "source_system": "临床指南文档库",
            "content": g["text"],
        })
    assets.append({
        "id": "RAW-LAB-001",
        "modality": "table",
        "ext": ".csv",
        "source_system": "检验信息系统 LIS",
        "content": "项目,结果,参考区间\n血红蛋白,98 g/L,130-175\n血清铁蛋白,6 ng/mL,30-400\n空腹血糖,8.4 mmol/L,3.9-6.1\nTSH,12.3 mIU/L,0.27-4.2",
    })
    return assets


def dump(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("  -> %s (%d 条)" % (os.path.relpath(path, HERE), len(rows)))


def main():
    rng = random.Random(20261016)
    print("[EvoMed-PoC] 生成最小验证数据集")
    cases = build_cases(rng)
    guidelines = build_guidelines()
    raw = build_raw_assets(cases, guidelines)
    dump(os.path.join(HERE, "cases.jsonl"), cases)
    dump(os.path.join(HERE, "guidelines.jsonl"), guidelines)
    dump(os.path.join(HERE, "raw_assets.jsonl"), raw)

    meta = {
        "name": "EvoMed-MiniBench v0.1",
        "seed": 20261016,
        "n_cases": len(cases),
        "n_guidelines": len(guidelines),
        "n_raw_assets": len(raw),
        "n_diseases": len(DISEASES),
        "license": "自建合成数据，可自由使用（不含任何真实患者信息）",
        "note": "用于最小原型验证，正式评测将接入公开中文医疗基准。",
    }
    with open(os.path.join(HERE, "dataset_meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("  -> dataset_meta.json")
    print("[完成] 病种数 = %d，病例 = %d，指南 = %d，原始资产 = %d"
          % (len(DISEASES), len(cases), len(guidelines), len(raw)))


if __name__ == "__main__":
    main()
