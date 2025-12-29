#next_version_ingest.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

-------------------
新版本：明显分成三层

L1 抽取层：parse_case_text      -> 从原始病例文本抽取结构化信息（病灶、特征等）
L2 分级层：grade_case           -> 根据特征组合 + 纤维化程度给出 F 分级 + 理由
L3 入库层：ingest_struct        -> 把结构化结果 + 分级写入 Neo4j

使用示例：
  python3.11 kg_ingest_cn_v2.py -i data   # 导入 data/ 下所有 *.txt
"""

import re
import argparse
from typing import List, Dict, Any, Tuple, Iterable, Optional
from py2neo import Graph, Node, Relationship
import unicodedata
import os
import sys
import glob
import json
import datetime
from openai import OpenAI
from kg_grade import grade_case

import requests
from pathlib import Path


# -------------------------
# LLM 开关 & OpenAi 配置
# -------------------------
USE_LLM = True  # 想用 LLM 就设 True

OPENAI_API_URL = "http://202.120.40.86:11445/v1/chat/completions"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "qwen2.5:14b-instruct")



class LLMNotAvailable(Exception):
    pass
class LLMNotAvailable(Exception):
    pass


def call_llm(prompt: str) -> str:
    """
    调用本地 Ollama 模型
    """
    if not USE_LLM:
        raise LLMNotAvailable("USE_LLM=False")

    url = "http://202.120.40.86:11445/v1/chat/completions"
    model_name = "qwen2.5:14b-instruct"

    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama API error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"Unexpected Ollama response: {data}")

    return content.strip()



# -------------------------
# Neo4j连接（可用环境变量覆盖）
# -------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# -------------------------
# 中文规范化映射（正则->标准中文特征）
# -------------------------
SEP = r"(?:\s|-|–|—)"


#------------------------------------
#引入大模型完成识别部分
#------------------------------------
CN_CANON_MAP = [
    # --- 桥接 ---
    # 1. 最标准：bridging fibrosis（整段替换）
    (r"(bridging\s+fibrosis)", "桥接"),

    # 2. portal–portal bridging fibrosis
    (rf"(portal{SEP}?portal{SEP}?bridging{SEP}?fibrosis)", "桥接"),

    # 3. portal–central bridging fibrosis
    (rf"(portal{SEP}?(?:to|–|—)?{SEP}?(?:central|cv){SEP}?bridging{SEP}?fibrosis)", "桥接"),

    # 4. 英文桥接描述但没写 fibrosis（某些报告里只写 bridging）
    (r"\bbridging\b", "桥接"),

    # 5. ★补丁：之前规则可能导致“桥接 fibrosis”，这里再吃掉一次
    (r"(桥接\s*fibrosis)", "桥接"),

    # --- 假小叶 ---
    (r"pseudolobule[s]?", "假小叶"),
    (r"regenerative\s+nodule[s]?", "假小叶"),
    (r"onion\s*ring|concentric\s+collagen", "假小叶"),
    (r"假小叶", "假小叶"),

    # --- 汇管区纤维化 ---
    (r"portal\s*tract\s*fibrosis", "汇管区纤维化"),
    (r"portal\s*area\s*fibrosis", "汇管区纤维化"),
    (r"门管区纤维化", "汇管区纤维化"),
    (r"汇管区纤维化", "汇管区纤维化"),

    # --- 纤维间隙 ---
    (r"fibrous\s*gap", "纤维间隙"),
    (r"纤维间隙", "纤维间隙"),


]

CANON_FEATURES = [
    "汇管区纤维化", "纤维间隙", "桥接", "假小叶"
]

# ============================================================
# L1：抽取层 —— 文本 -> 结构化 dict
# ============================================================

def normalize_to_cn(text: str) -> str:
    """统一编码 + 把中英混合表达规范成标准中文特征词"""
    t = unicodedata.normalize("NFKC", text).replace("\ufeff", "")
    # 统一括号等符号（按需扩展）
    t = re.sub(r"[()]", "（", t)
    t = re.sub(r"[)】]", "）", t)
    out = t
    for pat, repl in CN_CANON_MAP:
        out = re.sub(pat, repl, out, flags=re.I)
    out = re.sub(r"[ \t]+", " ", out)
    return out

def extract_field(text: str, labels: Iterable[str]) -> Optional[str]:
    """按 label: value 的模式抽取一整行字段"""
    for label in labels:
        m = re.search(label + r"\s*[:：]\s*(.+)", text, re.I)
        if m:
            val = m.group(1).strip()
            # 如果后面跟着 1)、2) 之类的病灶编号，提前截断
            val = re.split(r"\n\s*(\d+\)|[-•·])", val)[0].strip()
            return val
    return None

def extract_slice_id(text: str) -> str:
    """尽量从文本里识别切片编号"""
    pats = [
        re.compile(r"编号[:：]\s*([A-Za-z0-9\-]+)"),
        re.compile(r"\(([A-Za-z0-9\-]{3,})\)"),
        re.compile(r"（([A-Za-z0-9\-]{3,})）"),
        re.compile(r"\b(L\d{2}-[A-Za-z0-9]+)\b"),
    ]
    for p in pats:
        m = p.search(text)
        if m:
            return m.group(1)
    return f"SLICE_{abs(hash(text)) % (10**8)}"

def extract_patient_meta(text: str) -> Dict[str, Any]:
    meta = {"raw": None, "sex": None, "age": None, "surgery": None, "comorbid": None}
    m = re.search(r"(患者信息|Patient)\s*[:：]\s*(.+)", text, re.I)
    if m:
        raw = m.group(2).strip()
        meta["raw"] = raw
        if re.search(r"女|female", raw, re.I): meta["sex"] = "female"
        if re.search(r"男|male", raw, re.I): meta["sex"] = "male"
        mag = re.search(r"(\d{1,3})\s*(岁|years?)", raw, re.I)
        if mag: meta["age"] = int(mag.group(1))
        if re.search(r"手术|surgery|appendectomy|cholecystectomy|hepatectomy", raw, re.I):
            meta["surgery"] = True
        meta["comorbid"] = raw
    return meta

def extract_staining(text: str) -> Dict[str, Any]:
    v = extract_field(text, ["切片染色质量", "Staining quality"])
    if not v: return {}
    out = {"raw": v}
    m = re.match(r"(优|良|差|Excellent|Good|Poor|Indeterminate)(.*)", v, re.I)
    if m:
        out["quality"] = m.group(1).strip()
        reason = m.group(2).strip(" ；;。.()（）")
        if reason: out["reason"] = reason
    return out

def extract_fibrosis_overall(text: str) -> Dict[str, Any]:
    v = extract_field(text, ["切片整体纤维化程度", "Overall fibrosis", "Fibrosis extent"])
    if not v: return {}
    out = {"raw": v}
    m = re.match(r"(低|中|中-高|高|Low|Moderate(?:–|-)?High|Moderate|High|Indeterminate)(.*)", v, re.I)
    if m:
        out["level"] = m.group(1).strip()
        out["note"] = m.group(2).strip(" ；;。.()（）")
    return out

def extract_lesion_block(text: str) -> str:
    m = re.search(r"(病灶列举|Lesions)\s*[:：]\s*(.*)", text, re.I | re.S)
    return m.group(2).strip() if m else ""

def split_lesions(lesion_block: str) -> List[str]:
    """把“病灶列举”下面的一大段拆成多条单独病灶描述"""
    lines = [ln.strip() for ln in lesion_block.splitlines() if ln.strip()]
    lesions, cur = [], []
    for ln in lines:
        if re.match(r"^(\d+\)|[-•·]|L\d+[:：]|病灶\d+[:：])", ln):
            if cur:
                lesions.append(" ".join(cur))
                cur = []
            cur.append(ln)
        else:
            cur.append(ln)
    if cur:
        lesions.append(" ".join(cur))
    return lesions

def lesion_id_and_desc(lesion_text: str) -> Tuple[str, str]:
    """从“病灶1: xxx”里拆出 ID 和 描述"""
    m = re.match(r"^((?:病灶)?\s*[L]?\s*\d+)\s*[:：]\s*(.+)", lesion_text, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return f"LES_{abs(hash(lesion_text)) % (10**8)}", lesion_text

def find_features_cn(normalized_desc: str) -> List[str]:
    """在已经规范化后的病灶描述里查找所有标准特征词"""
    feats = []
    for tok in CANON_FEATURES:
        if tok in normalized_desc:
            feats.append(tok)
    return sorted(set(feats))

def find_features_llm(desc_cn: str) -> List[str]:
    """
    LLM 版特征抽取：
    - 尝试让大模型在 CANON_FEATURES 列表中选出该病灶出现的特征；
    - 如调用失败或格式不对，则回退到 find_features_cn。
    """

    #先跑一轮规则版，作为fallback和先验
    rule_feats = find_features_cn(desc_cn)
    # 如果没配 LLM，直接用规则结果
    if not USE_LLM:
        return rule_feats


    candidate_str = "、".join(CANON_FEATURES)
    prompt = f"""
你是一名肝病理科专科医生。下面是一段单个病灶的描述，请你从中判断出现了哪些“纤维化相关特征”。

标准特征候选列表（只能从这里面选，不能自己发明新名词）：
{candidate_str}

请你：
1. 根据病灶描述，找出所有确实出现或可以明确推断存在的特征；
2. 输出 JSON 数组，例如：["桥接","假小叶"]；
3. 如果没有看到任何上述特征，就输出 []；
4. 不要输出解释，不要多余文字，只要合法 JSON。

病灶描述：
{desc_cn}

你的输出：
""".strip()

    try:
        raw = call_llm(prompt)
        # 去掉可能的 markdown 包装
        raw = raw.strip().strip("`")
        feats = json.loads(raw)
        # 保守：只保留在 CANON_FEATURES 里的词
        feats = [f for f in feats if f in CANON_FEATURES]
        # 和规则版结果合并去重
        final = sorted(set(rule_feats + feats))
        return final
    except Exception:
        # LLM 挂了 / 格式错误，都直接用规则版
        print("[WARN] LLM feature extract failed, fallback to rules:", e)
        return rule_feats


def normalize_case_with_llm(raw_case: str) -> str:
    """
    用大模型把医生的自由口述，整理成统一模板：

    患者信息:...
    切片染色质量:...
    切片整体纤维化程度:...
    病灶列举:
    病灶 1:...
    病灶 2:...
    """
    template_prompt = f"""
    你是一名肝病理科医生兼数据标注员，请将下面这段自由口述的病例描述，规范整理成如下结构化文本：

    患者信息: 女,50 岁; 乙肝携带者; ...
    切片染色质量: 优/良/差（如果原文没说清楚, 就写“未说明”）。
    切片整体纤维化程度: 低/中/中-高/高（如果原文没说清楚, 就写“未说明”）。
    病灶列举:
    病灶 1: ...（每个病灶单独描述，包含位置、主要变化、相关特征）
    病灶 2: ...
    病灶 3: ...
    （请提取尽可能多的病灶区域，即使部分区域不典型，也要列出）

    要求：
    1. 每个“病灶”指代一个观察区域，如假小叶、桥接、肝细胞坏死、小胆管增生等病变都应单独列出；
    2. 每个病灶尽量包含“标准特征词”：假小叶、桥接、汇管区纤维化、纤维间隙、肝小叶结构破坏；
    3. 若有不确定但疑似病变区域，也请列为单独病灶并加注“疑似”；
    4. 每个病灶不要合并，要逐一编号列出，至少提取 3-5 个病灶；
    5. 不要输出解释，不要多余文字，只输出规范后的病例文本。
    6. 最后请附加一段“特征统计汇总”，格式如下：
    特征统计汇总：
    - 假小叶: 共3处，出现在病灶1、病灶3、病灶5
    - 桥接: 共2处，出现在病灶2、病灶4
    - 汇管区纤维化: 共2处，出现在病灶3、病灶6
    （只需列出实际在本病例中提到过的特征）

    原始病例：
    {raw_case}
    """.strip()


    print("\n[DEBUG] Calling LLM to normalize case...")
    normalized = call_llm(template_prompt)
    print("[DEBUG] LLM normalized result:\n", normalized, "\n")
    return normalized



def parse_case_text(raw_case: str) -> Dict[str, Any]:
    """
    L1 抽取层入口：
    输入：一整段病例文本
    输出：结构化 dict（不依赖 Neo4j）
    """

    try:
        normalized_raw = normalize_case_with_llm(raw_case)
    except LLMNotAvailable as e:
        print("[WARN] LLM not available, fallback to raw_case:", e)
        normalized_raw = raw_case
    except Exception as e:
        print("[WARN] LLM normalize failed, fallback to raw_case:", e)
        normalized_raw = raw_case

    cn = normalize_to_cn(normalized_raw)

    slice_id = extract_slice_id(cn)
    patient = extract_patient_meta(cn)
    staining = extract_staining(cn)
    fibrosis = extract_fibrosis_overall(cn)

    lesion_block = extract_lesion_block(cn)
    lesion_chunks = split_lesions(lesion_block)

    lesions = []
    for chunk in lesion_chunks:
        lid, desc = lesion_id_and_desc(chunk)
        desc_cn = normalize_to_cn(desc)
        feats = find_features_llm(desc_cn)
        lesions.append({
            "lesion_id": lid,
            "description": desc_cn,
            "features": feats,
        })

    return {
        "slice_id": slice_id,
        "raw": raw_case,
        "cn_norm": cn,
        "patient": patient,
        "staining": staining,
        "fibrosis_overall": fibrosis,
        "lesions": lesions,
    }



# ============================================================
# L2：分级层 —— 结构化 dict -> F 分级 + 理由
# ============================================================

def decide_grade_llm(ev):
    """使用LLM进行肝纤维化评分"""
    feats = ev["features"] or []
    fib_level = ev["fib_level"]
    stain_quality = ev["stain_quality"]
    lesions_desc = "；".join(ev["lesions"]) if ev["lesions"] else "无明确病灶描述"
    
    # 构建LLM提示词
    prompt = f"""
你是一名资深肝脏病理科医生。请根据以下病理信息，使用Ishak分级系统（F0-F6）对该肝脏切片进行评分。

【Ishak分级标准】：
- F0：无纤维化
- F1：门管区纤维化，无桥接
- F2：门管区纤维化+少许桥接（门-门或门-中心）
- F3：弥漫桥接纤维化（门-门或门-中心），但无肝硬化
- F4：桥接纤维隔加重，伴肝实质结构扭曲
- F5：早期肝硬化，伴明显假小叶形成
- F6：肝硬化

【病理学信息】：
- 检测到的纤维化特征：{', '.join(feats) if feats else '无'}
- 整体纤维化程度：{fib_level}
- 切片染色质量：{stain_quality}
- 病灶描述：{lesions_desc}

【任务】：
1. 根据上述信息，给出F分级（F0-F6之一）
2. 评分置信度（0.0-1.0之间）
3. 简要解释

输出JSON格式（只输出JSON，不要其他文字）：
{{
    "stage": "F0|F1|F2|F3|F4|F5|F6",
    "confidence": 0.0-1.0,
    "reason": "简要原因"
}}
""".strip()
    
    try:
        response = call_llm(prompt)
        result = json.loads(response.strip().strip("`json").strip("`"))
        stage = result.get("stage", "F2")
        conf = float(result.get("confidence", 0.5))
        reason = result.get("reason", "LLM评分")
        return stage, conf, reason
    except Exception as e:
        print(f"[WARN] LLM grading failed: {e}, fallback to rule-based")
        return decide_grade_rule(ev)




def map_features_to_ishak(feature_count: Dict[str, int]) -> Tuple[str, str]:
    """
    将特征计数映射为Ishak评分及解释
    """

    # 规则设定（可自定义）
    n_pseudolobule = feature_count['假小叶']
    n_bridging = feature_count['桥接']
    n_pc_fibrosis = feature_count['汇管区纤维化']
    n_struct_destruction = feature_count['肝小叶结构破坏']

    if n_pseudolobule >= 2 and n_bridging >= 1:
        return "F6", "发现多个假小叶和桥接性纤维化，符合结节性肝硬化特征，判断为 F6"
    elif n_bridging >= 2:
        return "F5", "明显桥接性纤维化，部分区域疑似结节形成，判断为 F5"
    elif n_bridging >= 1 and n_pc_fibrosis >= 1:
        return "F4", "观察到桥接（P-P/P-C）与汇管区纤维化，判断为 F4"
    elif n_pc_fibrosis >= 2:
        return "F3", "多处门管区纤维扩张，偶见桥接，判断为 F3"
    elif n_pc_fibrosis >= 1:
        return "F2", "少数门管区有纤维扩张，判断为 F2"
    else:
        return "F0–1", "未见明显纤维化特征或仅为轻度门管区纤维扩张"


def map_score_to_level(score: str) -> str:
    """
    将评分映射为描述性纤维化程度
    """
    if score == "F0–1":
        return "低"
    elif score == "F2":
        return "中"
    elif score == "F3":
        return "中-高"
    else:
        return "高"



# ============================================================
# L3：入库层 —— 把 struct + grading 写入 Neo4j
# ============================================================

def ensure_schema(graph: Graph):
    graph.run("CREATE CONSTRAINT slice_id IF NOT EXISTS FOR (n:Slice) REQUIRE n.id IS UNIQUE;")
    graph.run("CREATE CONSTRAINT feature_name IF NOT EXISTS FOR (n:Feature) REQUIRE n.name IS UNIQUE;")
    graph.run("CREATE CONSTRAINT staining_key IF NOT EXISTS FOR (n:Staining) REQUIRE n.key IS UNIQUE;")
    graph.run("CREATE CONSTRAINT fibrosis_key IF NOT EXISTS FOR (n:Fibrosis) REQUIRE n.key IS UNIQUE;")

def upsert_node(graph: Graph, label: str, key: str, props: Dict[str, Any]):
    props = {k: v for k, v in props.items() if v not in (None, "")}
    props["key"] = key
    graph.run(f"MERGE (n:{label} {{key: $key}}) SET n += $props", key=key, props=props)
    return graph.nodes.match(label, key=key).first()

def upsert_slice(graph: Graph, slice_id: str, props: Dict[str, Any]):
    props = {k: v for k, v in props.items() if v not in (None, "")}
    props["id"] = slice_id
    graph.run("MERGE (s:Slice {id: $id}) SET s += $props", id=slice_id, props=props)
    return graph.nodes.match("Slice", id=slice_id).first()

def create_rel(graph: Graph, a: Node, rel: str, b: Node, props: Optional[Dict[str, Any]] = None):
    graph.create(Relationship(a, rel, b, **(props or {})))


def upsert_evidence(graph, case_id, feature, count, llm_explain):
    q = """
    MATCH (s:Slice {id:$case_id})
    MERGE (e:Evidence {
        case_id: $case_id,
        feature: $feature
    })
    SET e.count = $count,
        e.llm_explain = $llm_explain
    MERGE (s)-[:HAS_EVIDENCE]->(e)
    """
    graph.run(
        q,
        case_id=case_id,
        feature=feature,
        count=count,
        llm_explain=llm_explain
    )



def ingest_struct(graph: Graph, struct: Dict[str, Any], grading: Dict[str, Any]):

    sid = struct["slice_id"]

    # --- Slice ---
    s_node = upsert_slice(graph, sid, {
        "raw": struct["raw"],
        "cn_norm": struct["cn_norm"]
    })

    # --- Metadata ---
    patient = struct.get("patient") or {}
    if patient.get("raw"):
        m_node = upsert_node(
            graph,
            "Metadata",
            f"meta::{sid}",
            patient
        )
        create_rel(graph, s_node, "HAS_METADATA", m_node)

    # --- Lesion + Feature ---
    for lesion in struct.get("lesions", []):
        l_node = upsert_node(
            graph,
            "Lesion",
            f"{sid}::{lesion['lesion_id']}",
            {
                "lesion_id": lesion["lesion_id"],
                "description": lesion["description"]
            }
        )
        create_rel(graph, s_node, "HAS_LESION", l_node)

        for f in lesion.get("features", []):
            f_node = upsert_node(graph, "Feature", f, {"name": f})
            create_rel(graph, l_node, "HAS_FEATURE", f_node)

    # --- Grade（唯一推理出口）---
    g_node = upsert_node(
        graph,
        "Grade",
        f"grade::{sid}",
        {
            # —— 医学语义核心 ——
            "stage": grading["stage"],          # F0–F6（真正的分级值）
            "grade_system": "Ishak",

            # —— 展示 & 命名（关键修复点） ——
            "grade": f"Ishak {grading['stage']}",

            # —— 判定来源 ——
            "method": "rule_based",
            "rule_reason": grading["rule_reason"],
            "llm_explanation": grading["llm_explanation"],

            # —— 元数据 ——
            "generated_at": datetime.datetime.now().isoformat()
        }
    )

    create_rel(graph, s_node, "HAS_GRADE", g_node)


def ingest_decision_graph(graph, sid, feature_evidence, stage):
    # 1. Grade
    g_key = f"Case_Id::{sid}"
    graph.run("""
    MERGE (g:Grade {key:$gkey})
    SET g.stage=$stage, g.method='rule_based', g.generated_at=datetime()
    """, gkey=g_key, stage=stage)

    graph.run("""
    MATCH (s:Slice {id:$sid}), (g:Grade {key:$gkey})
    MERGE (s)-[:HAS_GRADE]->(g)
    """, sid=sid, gkey=g_key)

    # 2. Evidence + Rule
    for feat, lids in feature_evidence.items():
        e_key = f"EVI::{sid}::{feat}"
        graph.run("""
        MERGE (e:Evidence {key:$ekey})
        SET e.feature=$feat,
            e.lesion_ids=$lids,
            e.count=size($lids)
        """, ekey=e_key, feat=feat, lids=lids)

        graph.run("""
        MATCH (s:Slice {id:$sid}), (e:Evidence {key:$ekey})
        MERGE (s)-[:HAS_EVIDENCE]->(e)
        """, sid=sid, ekey=e_key)

        # Rule（按 feature → stage 规则）
        rule_key = f"RULE::Ishak::{feat}"
        graph.run("""
        MERGE (r:Rule {key:$rkey})
        SET r.system='Ishak',
            r.condition=$cond,
            r.target_stage=$stage
        """, rkey=rule_key, cond=f"{feat} >= 1", stage=stage)

        graph.run("""
        MATCH (e:Evidence {key:$ekey}), (r:Rule {key:$rkey})
        MERGE (e)-[:TRIGGERS]->(r)
        """, ekey=e_key, rkey=rule_key)

        graph.run("""
        MATCH (r:Rule {key:$rkey}), (g:Grade {key:$gkey})
        MERGE (r)-[:SUPPORTS]->(g)
        """, rkey=rule_key, gkey=g_key)


# ============================================================
# 批处理入口
# ============================================================

def split_cases_from_file(text: str) -> List[str]:
    """
    自动分割多个病例片段。
    支持以下几类格式：
    1. '### Case 1' 标题格式
    2. 空行分割格式
    3. 单文件单病例
    """
    txt = unicodedata.normalize("NFKC", text).replace("\ufeff", "")

    # ① 如果文件是用 ### Case 分段
    blocks = re.split(r"\n\s*#{3,}.*\n", txt)
    if len(blocks) > 1:
        return [b.strip() for b in blocks if b.strip()]

    # ② 尝试用“空行+两大关键字段”分块
    chunks = re.split(r"\n\s*\n+", txt)
    cases, buf = [], []
    for ch in chunks:
        buf.append(ch)
        merged = "\n".join(buf)
        # 检查一个完整病例应当至少包含染色质量与病灶列举
        if re.search(r"(切片染色质量|Staining quality)", merged) and \
           re.search(r"(病灶列举|Lesions)", merged):
            cases.append(merged.strip())
            buf = []
    if buf and re.search(r"(切片染色质量|Staining quality)", "\n".join(buf)):
        cases.append("\n".join(buf).strip())

    return cases if cases else [txt]


def expand_inputs(user_input: str) -> List[Path]:
    p = Path(user_input)
    files: List[Path] = []
    if p.is_dir():
        files = sorted(Path(user_input).glob("*.txt"))
    else:
        matches = glob.glob(user_input)
        if matches:
            files = sorted(Path(m) for m in matches if Path(m).is_file())
        else:
            if p.is_file():
                files = [p]
    return files

def main():
    ap = argparse.ArgumentParser(description="Batch parse -> grade -> ingest to Neo4j")
    ap.add_argument("--input", "-i", required=True,
                    help="文件/目录/通配符（例如 data、data/case*.txt、data/case1.txt）")
    ap.add_argument("--uri", default=NEO4J_URI)
    ap.add_argument("--user", default=NEO4J_USER)
    ap.add_argument("--password", default=NEO4J_PASSWORD)
    args = ap.parse_args()

    files = expand_inputs(args.input)
    if not files:
        print(f"[ERROR] 未找到可导入的文件：{args.input}")
        sys.exit(1)

    print(f"[INFO] 待导入文件数：{len(files)}")
    graph = Graph(args.uri, auth=(args.user, args.password))
    ensure_schema(graph)

    total_cases = 0
    ok_files = 0

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[WARN] 读取失败：{path} -> {e}")
            continue

        # 一个文件里可以有多个病例
        cases = split_cases_from_file(text := unicodedata.normalize("NFKC", text).replace("\ufeff", ""))
        print(f"[INFO] 文件 {path.name} => {len(cases)} 个病例")

        file_ok = 0
        for idx, raw_case in enumerate(cases, 1):
            try:
                struct = parse_case_text(raw_case)
                struct["slice_id"] = path.stem
                grading = grade_case(struct)

                print(f"\n[GRADE] {path.name} :: {struct['slice_id']}")
                # print(f"  🧠 LLM 评分:   {grading.get('llm_grade')} (conf={grading.get('llm_confidence')})")
                # print(f"     理由: {grading.get('llm_reason')}")
                # print(f"  📏 规则评分: {grading.get('rule_grade')}")
                print(f"     LLM 理由: {grading.get('rule_reason')}")
                # print(f"  ✅ 是否一致: {'YES' if grading.get('match') else 'NO'}\n")

                case_id = f"{path.stem}::{struct['slice_id']}"

                feature_counter = grading.get("feature_counter", {})
                feature_explain = grading.get("feature_llm_explain", {})

                for feature, cnt in feature_counter.items():
                    upsert_evidence(
                        graph,
                        case_id=case_id,
                        feature=feature,
                        count=cnt,
                        llm_explain=feature_explain.get(feature, "")
                    )

                ingest_struct(graph, struct, grading)
                file_ok += 1
                total_cases += 1

            except Exception as e:
                print(f"[WARN] 该文件第 {idx} 个病例导入失败：{path.name} -> {e}")

        if file_ok == len(cases):
            ok_files += 1
        print(f"[DONE] {path.name}: {file_ok}/{len(cases)} 个病例成功")

    print(f"\n[SUMMARY] 成功导入文件：{ok_files}/{len(files)}，成功病例：{total_cases}\n")


if __name__ == "__main__":
    main()