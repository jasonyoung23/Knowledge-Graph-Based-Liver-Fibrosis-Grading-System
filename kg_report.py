#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kg_report.py
-------------
从 Neo4j 拉取病例 -> 计算病灶间“距离”（基于特征的 Jaccard 距离）
 -> 汇总每个切片的分级结果与分级理由 -> 导出 CSV 报告。

用法：
  python3.11 kg_report.py --out report.csv --pairs pairs.csv

环境变量（可选）：
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
"""
import os, argparse, csv, itertools
from py2neo import Graph

URI = os.getenv("NEO4J_URI","bolt://localhost:7687")
USER= os.getenv("NEO4J_USER","neo4j")
PWD = os.getenv("NEO4J_PASSWORD","password")

def fetch_data():
    g = Graph(URI, auth=(USER, PWD))
    q = """
    MATCH (s:Slice)
    OPTIONAL MATCH (s)-[:HAS_GRADE]->(gr:Grade)
    OPTIONAL MATCH (s)-[:HAS_STAINING]->(st:Staining)
    OPTIONAL MATCH (s)-[:HAS_FIBROSIS]->(fb:Fibrosis)
    OPTIONAL MATCH (s)-[:HAS_LESION]->(l:Lesion)
    OPTIONAL MATCH (l)-[:HAS_FEATURE]->(f:Feature)
    WITH s, gr, st, fb, l, collect(DISTINCT f.name) AS feats
    RETURN s.id           AS sid,
           coalesce(gr.stage,'NA') AS stage,
           gr.confidence  AS confidence,
           gr.reason      AS reason,
           coalesce(st.quality,'') AS stain_quality,
           coalesce(fb.level,'')   AS fib_level,
           l.lesion_id    AS lesion_id,
           l.description  AS lesion_desc,
           feats          AS features
    ORDER BY sid, lesion_id
    """
    rows = Graph(URI, auth=(USER, PWD)).run(q).data()
    # 结构化：按切片分组
    by_slice = {}
    for r in rows:
        sid = r["sid"]
        if sid not in by_slice:
            by_slice[sid] = {
                "stage": r["stage"],
                "confidence": r["confidence"],
                "reason": r["reason"],
                "stain_quality": r["stain_quality"],
                "fib_level": r["fib_level"],
                "lesions": []
            }
        if r["lesion_id"] is not None:  # 可能存在没有病灶的切片
            by_slice[sid]["lesions"].append({
                "lesion_id": r["lesion_id"],
                "lesion_desc": r["lesion_desc"] or "",
                "features": set(r["features"] or [])
            })
    return by_slice

def jaccard_distance(a:set, b:set):
    if not a and not b:
        return 1.0  # 无特征的病灶，两者距离定义为1
    inter = len(a & b)
    union = len(a | b)
    return 1 - (inter / union if union else 0.0)

def build_reports(by_slice: dict):
    # 概览：每个切片1行
    summary_rows = []
    # 病灶对：每个切片内所有两两组合
    pair_rows = []

    for sid, info in by_slice.items():
        lesions = info["lesions"]
        # 切片级别的“平均病灶距离”（可当作病灶分散度指标）
        dists = []
        for li, lj in itertools.combinations(lesions, 2):
            d = jaccard_distance(li["features"], lj["features"])
            dists.append(d)
            pair_rows.append({
                "slice_id": sid,
                "lesion_i": li["lesion_id"],
                "lesion_j": lj["lesion_id"],
                "distance": round(d, 4),
                "shared_features": "、".join(sorted(li["features"] & lj["features"])) or "",
                "union_size": len(li["features"] | lj["features"]),
                "lesion_i_desc": li["lesion_desc"],
                "lesion_j_desc": lj["lesion_desc"]
            })
        avg_dist = round(sum(dists)/len(dists), 4) if dists else None

        # 汇总切片概览（分级+理由+整体“分散度”）
        summary_rows.append({
            "slice_id": sid,
            "stage": info["stage"],
            "confidence": info["confidence"],
            "stain_quality": info["stain_quality"],
            "fib_level": info["fib_level"],
            "avg_lesion_distance": avg_dist,
            "lesion_count": len(lesions),
            "grade_reason": info["reason"] or ""
        })
    return summary_rows, pair_rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="report.csv", help="切片级报告 CSV 文件")
    ap.add_argument("--pairs", default="pairs.csv", help="病灶对距离 CSV 文件")
    args = ap.parse_args()

    by_slice = fetch_data()
    if not by_slice:
        print("[INFO] 图中未找到 Slice 节点。")
        return

    summary_rows, pair_rows = build_reports(by_slice)

    # 写切片级概览
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "slice_id","stage","confidence","stain_quality","fib_level",
            "avg_lesion_distance","lesion_count","grade_reason"
        ])
        w.writeheader(); w.writerows(summary_rows)
    print(f"[SAVED] {args.out}  共 {len(summary_rows)} 行")

    # 写病灶对距离
    with open(args.pairs, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "slice_id","lesion_i","lesion_j","distance","shared_features",
            "union_size","lesion_i_desc","lesion_j_desc"
        ])
        w.writeheader(); w.writerows(pair_rows)
    print(f"[SAVED] {args.pairs}  共 {len(pair_rows)} 行")

if __name__ == "__main__":
    main()
