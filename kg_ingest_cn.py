#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kg_ingest_cn.py (batch version)
--------------------------------
批量导入：支持 --input 传入 单个文件 / 目录 / 通配符(glob)
示例：
  python3.11 kg_ingest_cn.py -i data                # 导入 data/ 下所有 *.txt
  python3.11 kg_ingest_cn.py -i 'data/case*.txt'    # 导入匹配的所有文件
  python3.11 kg_ingest_cn.py -i data/case1.txt      # 单文件

依赖：
  pip install py2neo==2021.2.3
环境变量（可选）：
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
"""

import re
import argparse
from typing import List, Dict, Any, Tuple, Iterable, Optional
from py2neo import Graph, Node, Relationship
import unicodedata
import os
import sys
import glob
from pathlib import Path

# -------------------------
# Neo4j连接（可用环境变量覆盖）
# -------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# -------------------------
# 中文规范化映射（正则->标准中文特征）
# 顺序很重要：越具体的规则在前
# -------------------------
# 支持空格、半角连字符“-”、以及中文短破折号“–”与长破折号“—”
SEP = r"(?:\s|-|–|—)"

CN_CANON_MAP = [
    # --- 桥接（修复字符类范围问题） ---
    (rf"(portal{SEP}?portal{SEP}?(?:bridging|fibrosis))", "桥接"),
    (rf"(portal{SEP}?(?:to|–|—)?{SEP}?(?:central|cv){SEP}?(?:bridging|fibrosis))", "桥接"),
    (r"(bridging\s+fibrosis)", "桥接"),
    (r"(门[\-–—]?\s*门).*?(桥接|纤维)", "桥接"),
    (r"(门[\-–—]?\s*(中央|中心)).*?(桥接|纤维)", "桥接"),

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

    # --- 门管区扩大 ---
    (r"portal\s*expan\w*", "门管区扩大"),
    (r"门管区扩大", "门管区扩大"),

    # --- 纤维间隙 ---
    (r"fibrous\s*gap", "纤维间隙"),
    (r"纤维间隙", "纤维间隙"),

    # --- 肝窦周围纤维化 ---
    (r"perisinusoidal\s*fibrosis", "肝窦周围纤维化"),
    (r"肝窦周围纤维化", "肝窦周围纤维化"),

    # --- 胆管增生 ---
    (r"ductular\s*reaction", "胆管增生"),
    (r"胆管(反应|增生)", "胆管增生"),

    # --- 炎细胞浸润 ---
    (r"inflammatory\s+infiltrate[s]?", "炎细胞浸润"),
    (r"炎细胞浸润", "炎细胞浸润"),

    # --- 小叶结构破坏 ---
    (r"lobular\s+distortion", "小叶结构破坏"),
    (r"小叶结构破坏|结构紊乱", "小叶结构破坏"),

    # --- 中央静脉受掩盖 ---
    (r"central\s+vein\s+(obscured|not\s+well\s+identified|hard\s+to\s+identify)", "中央静脉受掩盖"),
    (r"中央静脉(不清|难以定位|受掩盖)", "中央静脉受掩盖"),
]

CANON_FEATURES = [
    "汇管区纤维化", "纤维间隙", "桥接", "假小叶", "胆管增生",
    "肝窦周围纤维化", "小叶结构破坏", "中央静脉受掩盖", "门管区扩大"
]

# -------------------------
# 文本预处理/规范化
# -------------------------
def normalize_to_cn(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).replace("\ufeff", "")
    # 统一一些符号（可按需扩展）
    t = re.sub(r"[()]", "（", t)
    t = re.sub(r"[)】]", "）", t)
    out = t
    for pat, repl in CN_CANON_MAP:
        out = re.sub(pat, repl, out, flags=re.I)
    out = re.sub(r"[ \t]+", " ", out)
    return out

# -------------------------
# 基础抽取
# -------------------------
def extract_field(text: str, labels: Iterable[str]) -> Optional[str]:
    for label in labels:
        m = re.search(label + r"\s*[:：]\s*(.+)", text, re.I)
        if m:
            val = m.group(1).strip()
            val = re.split(r"\n\s*(\d+\)|[-•·])", val)[0].strip()
            return val
    return None

def extract_slice_id(text: str) -> str:
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
    m = re.search(r"(病灶列举|Lesions)\s*[:：]\s*(.*)", text, re.I|re.S)
    return m.group(2).strip() if m else ""

def split_lesions(lesion_block: str) -> List[str]:
    lines = [ln.strip() for ln in lesion_block.splitlines() if ln.strip()]
    lesions, cur = [], []
    for ln in lines:
        if re.match(r"^(\d+\)|[-•·]|L\d+[:：]|病灶\d+[:：])", ln):
            if cur: lesions.append(" ".join(cur)); cur = []
            cur.append(ln)
        else:
            cur.append(ln)
    if cur: lesions.append(" ".join(cur))
    return lesions

def lesion_id_and_desc(lesion_text: str) -> Tuple[str, str]:
    m = re.match(r"^((?:病灶)?\s*[L]?\s*\d+)\s*[:：]\s*(.+)", lesion_text, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return f"LES_{abs(hash(lesion_text)) % (10**8)}", lesion_text

def find_features_cn(normalized_desc: str) -> List[str]:
    feats = []
    for tok in CANON_FEATURES:
        if tok in normalized_desc:
            feats.append(tok)
    return sorted(set(feats))

# -------------------------
# Neo4j helpers
# -------------------------
def ensure_schema(graph: Graph):
    graph.run("CREATE CONSTRAINT slice_id IF NOT EXISTS FOR (n:Slice) REQUIRE n.id IS UNIQUE;")
    graph.run("CREATE CONSTRAINT feature_name IF NOT EXISTS FOR (n:Feature) REQUIRE n.name IS UNIQUE;")
    graph.run("CREATE CONSTRAINT staining_key IF NOT EXISTS FOR (n:Staining) REQUIRE n.key IS UNIQUE;")
    graph.run("CREATE CONSTRAINT fibrosis_key IF NOT EXISTS FOR (n:Fibrosis) REQUIRE n.key IS UNIQUE;")

def upsert_node(graph: Graph, label: str, key: str, props: Dict[str, Any]):
    props = {k:v for k,v in props.items() if v not in (None, "")}
    props["key"] = key
    graph.run(f"MERGE (n:{label} {{key: $key}}) SET n += $props", key=key, props=props)
    return graph.nodes.match(label, key=key).first()

def upsert_slice(graph: Graph, slice_id: str, props: Dict[str, Any]):
    props = {k:v for k,v in props.items() if v not in (None, "")}
    props["id"] = slice_id
    graph.run("MERGE (s:Slice {id: $id}) SET s += $props", id=slice_id, props=props)
    return graph.nodes.match("Slice", id=slice_id).first()

def create_rel(graph: Graph, a: Node, rel: str, b: Node, props: Optional[Dict[str, Any]]=None):
    graph.create(Relationship(a, rel, b, **(props or {})))

# -------------------------
# 单病例入库
# -------------------------
def ingest_case(graph: Graph, raw_case: str, slice_hint: Optional[str] = None):
    cn = normalize_to_cn(raw_case)
    # 让 slice_id 更稳妥：如从文件名传入 hint，避免不同文件同一个“随机hash”撞车
    sid = extract_slice_id(cn)
    if slice_hint:
        sid = f"{slice_hint}::{sid}"

    patient = extract_patient_meta(cn)
    staining = extract_staining(cn)
    fibrosis = extract_fibrosis_overall(cn)
    lesion_block = extract_lesion_block(cn)
    lesion_chunks = split_lesions(lesion_block)

    s_node = upsert_slice(graph, sid, {"raw": raw_case, "cn_norm": cn})

    if patient.get("raw"):
        m_node = Node("Metadata",
                      key=f"meta::{sid}",
                      sex=patient.get("sex"),
                      age=patient.get("age"),
                      surgery=patient.get("surgery"),
                      comorbid=patient.get("comorbid"))
        graph.merge(m_node, "Metadata", "key")
        create_rel(graph, s_node, "HAS_METADATA", m_node)

    if staining:
        key = f"{staining.get('quality','未知')}::{staining.get('reason','')}"
        st_node = upsert_node(graph, "Staining", key, {
            "quality": staining.get("quality"),
            "reason": staining.get("reason"),
            "raw": staining.get("raw")
        })
        create_rel(graph, s_node, "HAS_STAINING", st_node)

    if fibrosis:
        key = f"{fibrosis.get('level','未知')}::{fibrosis.get('note','')}"
        fb_node = upsert_node(graph, "Fibrosis", key, {
            "level": fibrosis.get("level"),
            "note": fibrosis.get("note"),
            "raw": fibrosis.get("raw")
        })
        create_rel(graph, s_node, "HAS_FIBROSIS", fb_node)

    for chunk in lesion_chunks:
        lid, desc = lesion_id_and_desc(chunk)
        desc_cn = normalize_to_cn(desc)
        lkey = f"{sid}::{lid}"
        l_node = upsert_node(graph, "Lesion", lkey, {
            "slice_id": sid,
            "lesion_id": lid,
            "description": desc_cn
        })
        create_rel(graph, s_node, "HAS_LESION", l_node)
        feats = find_features_cn(desc_cn)
        for f in feats:
            f_node = upsert_node(graph, "Feature", f, {"name": f})
            create_rel(graph, l_node, "HAS_FEATURE", f_node)

# -------------------------
# 多病例分割：支持 ### 标题或空行块
# -------------------------
def split_cases_from_file(text: str) -> List[str]:
    t = unicodedata.normalize("NFKC", text).replace("\ufeff", "")
    # 先按 ### 分
    blocks = re.split(r"\n\s*#{3,}\s*[A-Za-z0-9\-\u4e00-\u9fa5\(\)（）]+\s*\n", t)
    if len(blocks) > 1:
        return [b.strip() for b in blocks if b.strip()]
    # 退化为按空行合并
    blocks = re.split(r"\n\s*\n+", t)
    cases, buf = [], []
    for b in blocks:
        buf.append(b)
        joined = "\n".join(buf)
        if re.search(r"(切片染色质量|Staining quality)", joined) and re.search(r"(病灶列举|Lesions)", joined):
            cases.append(joined.strip()); buf = []
    if buf and re.search(r"(切片染色质量|Staining quality)", "\n".join(buf)):
        cases.append("\n".join(buf).strip())
    return cases if cases else [t]

# -------------------------
# 批处理入口
# -------------------------
def expand_inputs(user_input: str) -> List[Path]:
    p = Path(user_input)
    files: List[Path] = []
    if p.is_dir():
        files = sorted(Path(user_input).glob("*.txt"))
    else:
        # 支持通配符
        matches = glob.glob(user_input)
        if matches:
            files = sorted(Path(m) for m in matches if Path(m).is_file())
        else:
            if p.is_file():
                files = [p]
    return files

def main():
    ap = argparse.ArgumentParser(description="Batch normalize -> extract -> ingest to Neo4j")
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

        cases = split_cases_from_file(text)
        print(f"[INFO] 文件 {path.name} => {len(cases)} 个病例")
        file_ok = 0
        for idx, c in enumerate(cases, 1):
            try:
                # 用文件名作为 slice_hint，避免跨文件冲突
                ingest_case(graph, c, slice_hint=path.stem)
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
