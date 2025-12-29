from py2neo import Graph, Node, Relationship
from collections import defaultdict
import datetime
import json
import requests

LLM_ENDPOINT = "http://202.120.40.86:11445/v1/chat/completions"
MODEL = "qwen2.5:14b-instruct"

URI = "bolt://localhost:7687"
USER = "neo4j"
PWD  = "password"

graph = Graph(URI, auth=(USER, PWD))


# ----------------------------
# 1. 规则定义（你可扩展）
# ----------------------------
def llm_explain_evidence(feature, count, lesions):
    prompt = f"""
你是一名肝病理科医生。
请用一句专业但简洁的话，解释“为什么该特征在肝纤维化评估中重要”。

特征名称：{feature}
出现次数：{count}
涉及病灶：{", ".join(lesions)}

要求：
- 只解释医学意义
- 不要提规则编号
- 不超过 30 字
"""
    return call_llm_simple(prompt)


def llm_explain_rule(rule_condition, stage):
    prompt = f"""
你是一名肝病理科专家。
请解释以下分级规则在 Ishak 系统中的医学依据。

规则条件：{rule_condition}
对应分级：{stage}
要求：
- 一句话
- 强调形态学与分级关系
- 不超过 30 字
"""
    return call_llm_simple(prompt)


def call_llm_simple(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    r = requests.post(LLM_ENDPOINT, json=payload, timeout=20)
    return r.json()["choices"][0]["message"]["content"].strip()

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



ISHak_RULES = [
    {
        "rule_id": "R_F6_PSEUDO_DISTORT",
        "condition": "假小叶 >= 2 AND 小叶结构破坏 >= 1",
        "trigger": lambda c: c["假小叶"] >= 2 and c["小叶结构破坏"] >= 1,
        "stage": "F6",
        "priority": 100
    },
    {
        "rule_id": "R_F5_PSEUDO",
        "condition": "假小叶 >= 1",
        "trigger": lambda c: c["假小叶"] >= 1,
        "stage": "F5",
        "priority": 90
    },
    {
        "rule_id": "R_F3_BRIDGE",
        "condition": "桥接 >= 2",
        "trigger": lambda c: c["桥接"] >= 2,
        "stage": "F3",
        "priority": 70
    },
]


# ----------------------------
# 2. 工具函数
# ----------------------------

def upsert_node(label, key, props):
    props = {k: v for k, v in props.items() if v is not None}
    props["key"] = key
    graph.run(
        f"MERGE (n:{label} {{key:$key}}) SET n += $props",
        key=key, props=props
    )
    return graph.nodes.match(label, key=key).first()


def link(a, rel, b):
    graph.merge(Relationship(a, rel, b))


# ----------------------------
# 3. Evidence / Rule / Grade 写入
# ----------------------------

def build_explain_graph_for_slice(slice_id: str):
    """
    从现有：
      Slice - Lesion - Feature
    构建：
      Evidence -> Rule -> Grade
    """

    # --- 1. 拉取 Feature 证据 ---
    q = """
    MATCH (s:Slice {id:$sid})-[:HAS_LESION]->(l)-[:HAS_FEATURE]->(f)
    RETURN f.name AS feature, collect(l.lesion_id) AS lesions
    """
    rows = graph.run(q, sid=slice_id).data()

    # --- 2. 统计 Evidence ---
    feature_count = defaultdict(int)
    feature_lesions = {}

    for r in rows:
        feature = r["feature"]
        lesions = list(set(r["lesions"]))
        feature_count[feature] += len(lesions)
        feature_lesions[feature] = lesions

    s_node = graph.nodes.match("Slice", id=slice_id).first()
    if not s_node:
        return

    evidence_nodes = []

    for feat, cnt in feature_count.items():
        ev_key = f"ev::{slice_id}::{feat}"
        ev_node = upsert_node(
            "Evidence",
            ev_key,
            {
                "feature": feat,
                "count": cnt,
                "lesion_ids": feature_lesions.get(feat),
                "source": "lesion_feature_count",
                "llm_explain": llm_explain_evidence(
                    feat, cnt, feature_lesions.get(feat)
                )
            }
        )

        link(s_node, "HAS_EVIDENCE", ev_node)
        evidence_nodes.append(ev_node)

    # --- 3. 规则触发 ---
    matched_rules = []
    for rule in ISHak_RULES:
        if rule["trigger"](feature_count):
            r_node = upsert_node(
                "Rule",
                rule["rule_id"],
                {
                    "condition": rule["condition"],
                    "ishak_stage": rule["stage"],
                    "priority": rule["priority"],
                    "source": "Ishak",
                    "llm_explain": llm_explain_rule(
                        rule["condition"], rule["stage"]
                    )
                }
            )

            matched_rules.append(r_node)

            for ev in evidence_nodes:
                link(ev, "TRIGGERS", r_node)

    if not matched_rules:
        return

    # --- 4. 选择最高优先级 Rule → Grade ---
    final_rule = sorted(
        matched_rules,
        key=lambda r: r["priority"],
        reverse=True
    )[0]

    stage = final_rule["ishak_stage"]

    g_node = upsert_node(
        "Grade",
        f"grade::{slice_id}",
        {
            "stage": stage,
            "method": "rule+llm",
            "generated_at": datetime.datetime.now().isoformat()
        }
    )

    link(final_rule, "SUPPORTS", g_node)
    link(s_node, "HAS_GRADE", g_node)


# ----------------------------
# 4. 批处理入口
# ----------------------------

def run_all():
    slices = graph.run("MATCH (s:Slice) RETURN s.id AS sid").data()
    for r in slices:
        print(f"[EXPLAIN] building for {r['sid']}")
        build_explain_graph_for_slice(r["sid"])


if __name__ == "__main__":
    run_all()
