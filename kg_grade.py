# kg_grade.py
# ----------------------------------------
# Rule-based Ishak grading + LLM explanation (Evidence-grounded)
# ----------------------------------------

import os
import json
import requests
from typing import Dict, List, Tuple

# ========== LLM 配置 ==========
LLM_ENDPOINT = os.getenv(
    "LLM_ENDPOINT",
    "https://cn.getgoapi.com/v1/chat/completions"
)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY = os.getenv(
    "LLM_API_KEY",
    "sk-hhBG3Jq4EJhSFwSYr4KDPereFzpbojM6qhwJtKuH5twEPLHh"
)


# ============================================================
# 一、证据聚合层（Feature -> Lesion）
# ============================================================

def build_feature_evidence(struct: dict) -> Dict[str, List[str]]:
    """
    从 struct 中构造 Feature 证据映射：
    {
      "假小叶": ["病灶1", "病灶3"],
      "桥接": ["病灶2"]
    }
    """
    evidence: Dict[str, List[str]] = {}
    for les in struct.get("lesions", []):
        lid = les.get("lesion_id")
        for f in les.get("features", []):
            evidence.setdefault(f, []).append(lid)
    return evidence


# ============================================================
# 二、规则主导的 Ishak 分级（唯一裁决）
# ============================================================

def rule_based_ishak_grade(feature_evidence: Dict[str, List[str]]) -> Tuple[str, str]:
    """
    严格基于 Feature 证据进行 Ishak 分级
    返回: (stage, rule_reason)
    """

    n_pseudo = len(feature_evidence.get("假小叶", []))
    n_bridge = len(feature_evidence.get("桥接", []))
    n_portal = len(feature_evidence.get("汇管区纤维化", []))

    # F6
    if n_pseudo >= 2 and n_bridge >= 1:
        return (
            "F6",
            "≥2 处假小叶并伴桥接性纤维化，符合肝硬化（F6）"
        )

    # F5
    if n_pseudo >= 1:
        return (
            "F5",
            "出现假小叶结构，符合早期肝硬化（F5）"
        )

    # F4
    if n_bridge >= 2:
        return (
            "F4",
            "多处桥接性纤维化，未见假小叶，符合 F4"
        )

    # F3
    if n_bridge == 1:
        return (
            "F3",
            "出现桥接性纤维化，符合中重度纤维化（F3）"
        )

    # F2
    if n_portal >= 1:
        return (
            "F2",
            "门管区纤维化为主，符合轻中度纤维化（F2）"
        )

    # F0–F1
    return (
        "F0–F1",
        "未见明确桥接或假小叶，仅轻度或无纤维化改变"
    )


# ============================================================
# 三、LLM 解释层（只能解释，不能判断）
# ============================================================

def explain_with_llm(
    stage: str,
    feature_evidence: Dict[str, List[str]],
    struct: dict
) -> str:
    """
    使用 LLM 解释「为什么规则给出该分级」
    ⚠️ 只能基于已存在的 Feature + Lesion
    """

    evidence_lines = []
    for f, lids in feature_evidence.items():
        evidence_lines.append(
            f"- {f}：出现在病灶 {', '.join(lids)}"
        )

    lesion_desc = [
        f"- {les['lesion_id']}：{les['description']}"
        for les in struct.get("lesions", [])
    ]

    prompt = f"""
你是一名资深肝病理科医生。

【重要前提】
- 肝纤维化分级结果已经由规则系统确定，请勿更改或质疑该结果；
- 你不需要进行任何再判断，只需对“为什么是该分级”进行医学解释；
- 不允许引入未提供的新病理证据或推测。

【已确定分级】
Ishak 分级：{stage}


（说明：上述证据均来自该病例的实际病灶观察结果）

【你的任务】
请基于以上证据，用 1–2 句话，从“病理形态学变化”的角度，解释该病例为何符合该 Ishak 分级。

【写作要求】
1. 不要重复或照抄 Ishak 分级定义原文；
2. 不要使用“符合F6定义”“根据评分标准”等模板化表述；
3. 重点描述病理形态之间的组合关系（如结构重塑、结节形成、纤维连接等）；
4. 不引入新的特征、不增加未出现的病灶；
5. 表达应自然、专业，类似真实病理报告中的综合性描述；
6. 总字数不超过 60 字。

【输出格式】
- 仅输出医学解释文本本身
- 不要编号，不要标题，不要多余说明
""".strip()

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是严谨的肝病理科医生，只能基于给定证据进行解释。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }

    try:
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        resp = requests.post(LLM_ENDPOINT, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"【解释生成失败】{e}"


# ============================================================
# 四、对外主入口（供 next_version_ingest.py 调用）
# ============================================================

def grade_case(struct: dict) -> Dict[str, any]:
    """
    对单个病例进行评分（规则）+ 解释（LLM）
    """

    # 1️⃣ 构造证据
    feature_evidence = build_feature_evidence(struct)

    # 2️⃣ 规则裁决（唯一有效分级）
    stage, rule_reason = rule_based_ishak_grade(feature_evidence)

    # 3️⃣ LLM 解释（不影响分级）
    explanation = explain_with_llm(
        stage,
        feature_evidence,
        struct
    )

    return {
        "stage": stage,
        "rule_reason": rule_reason,
        "feature_evidence": feature_evidence,
        "llm_explanation": explanation
    }
