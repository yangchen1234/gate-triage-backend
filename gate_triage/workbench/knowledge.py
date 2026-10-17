"""Inspectable local source retrieval. No model or remote retrieval is implied."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/knowledge", tags=["source retrieval"])
ROOT = Path(__file__).resolve().parents[2]

# Curated passages keep operational caveats with the facts they qualify. The
# public URL is evidence for background only, never a live closure signal.
POLICIES = [
    ("departure", "Readiness is not release authorization",
     "A reported available container still needs all independent prerequisites. Customs hold, documents, payment, appointment, site movement authorization and current resource conditions remain separate. Urgency never overrides a hold. 海关 扣留 放行 可提 许可", "t49_holds"),
    ("temperature", "Respond to warming without clearing unrelated restrictions",
     "Reefer temperature and independent scale weight are simulation operational evidence, not Terminal49 fields. A fresh normal temperature resolves only the reefer issue; a customs hold remains. 冷藏 温度 升温 称重 地磅", "t49_container"),
    ("incident", "Use a scoped incident and staged recovery",
     "The September 2024 battery truck incident is historical background. The demo adds synthetic East gate closure, restricted capacity and reopening times. Road reopening is not proof every terminal service has recovered. 事故 侧翻 火灾 封路 恢复", "pola_reopening_2024"),
    ("feed", "Preserve known restrictions during an outage",
     "Connectivity loss makes freshness uncertain; it does not clear the last known hold. Deduplicate by event ID and reject late field updates behind the source watermark. Reconcile after recovery. 实时 延迟 重复 断网 数据 恢复", "t49_webhooks"),
    ("optimization", "Optimize feasible work and report the tradeoffs",
     "Constraint scheduling respects permission, precedence and resource capacity. Compare FIFO, priority and CP-SAT with identical information and service samples. Count completed handoffs separately from planned jobs and inspections. 吞吐量 优化 调度 公平", "local_contract"),
    ("rag", "Retrieval explains; events update; constraints decide feasibility",
     "Local source retrieval returns curated passages and links without an LLM. Future RAG can draft cited explanations. It cannot infer a current closure from historical documents, remove a hold, authorize release or control equipment. RAG 大模型 知识库 检索", "local_contract"),
]


def tokens(value: str) -> list[str]:
    text = value.casefold()
    latin = re.findall(r"[a-z0-9_]+", text)
    chinese = re.findall(r"[\u3400-\u9fff]", text)
    return latin + chinese + ["".join(chinese[i:i + 2]) for i in range(len(chinese) - 1)]


@lru_cache(maxsize=1)
def passages() -> list[dict]:
    manifest = json.loads((ROOT / "docs/reference-pack/source-manifest.json").read_text())
    sources = {s["id"]: s for s in manifest["sources"]}
    sources["t49_webhooks"] = {"title": "Terminal49 webhook guide", "url": "https://terminal49.com/docs/api-docs/in-depth-guides/webhooks", "supported_background": "Official delivery and signing contract, subject to account capabilities."}
    sources["local_contract"] = {"title": "Gate Triage realtime decision contract", "url": "/reference/realtime-decision-contract.zh-CN.md", "supported_background": "Our product design, not a port operating procedure."}
    result = []
    for identifier, title, content, source_id in POLICIES:
        source = sources[source_id]
        result.append({"id": identifier, "title": title, "passage": re.sub(r"[\u3400-\u9fff].*$", "", content).strip(),
                       "search_terms": content,
                       "source_id": source_id, "source_title": source["title"],
                       "url": source["url"], "scope": source["supported_background"],
                       "kind": "product_policy"})
    for source_id, source in sources.items():
        if source_id == "local_contract":
            continue
        result.append({"id": source_id, "title": source["title"],
                       "passage": source["supported_background"], "source_id": source_id,
                       "source_title": source["title"], "url": source["url"],
                       "scope": "Historical/API background; not a live operational observation.",
                       "kind": "official_background"})
    from .spatial import incident_catalog
    for scenario in incident_catalog():
        for index, source in enumerate(scenario["source_refs"]):
            result.append({"id": f"emergency:{scenario['id']}:{index}",
                           "title": source["title"],
                           "passage": scenario["historical_facts"] + " Exercise policy: " + " ".join(scenario["response_steps"]),
                           "search_terms": scenario["name"] + " " + scenario["historical_facts"] + " " + " ".join(scenario["response_steps"]),
                           "source_id": f"emergency:{scenario['id']}", "source_title": source["title"], "url": source["url"],
                           "scope": "Historical source supports background only. Response steps are our generic exercise policy, not that authority's approved operating procedure or a live closure signal.",
                           "kind": "historical_background_and_exercise_policy"})
    return result


def search_sources(query: str, limit: int = 5) -> dict:
    """Small BM25 index; full passages stay visible so a match is inspectable."""
    corpus = passages()
    query_terms = set(tokens(query))
    documents = [Counter(tokens(p["title"] + " " + p.get("search_terms", p["passage"]))) for p in corpus]
    lengths = [sum(d.values()) for d in documents]
    average = sum(lengths) / max(len(lengths), 1)
    ranked = []
    for passage, doc, length in zip(corpus, documents, lengths):
        score = 0.0
        for term in query_terms:
            frequency = doc[term]
            if not frequency:
                continue
            df = sum(term in d for d in documents)
            idf = math.log(1 + (len(documents) - df + .5) / (df + .5))
            score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
        if score:
            ranked.append({**passage, "score": round(score, 4)})
    ranked.sort(key=lambda p: (-p["score"], p["id"]))
    return {"query": query, "method": "local_bm25_source_retrieval", "llm_used": False,
            "items": ranked[:limit], "notice": "Sources explain the design; they do not authorize an action or establish current port conditions."}


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=400), limit: int = Query(default=5, ge=1, le=10)):
    return {"data": search_sources(q, limit), "meta": {"method": "retrieval_only", "live_provider": False}}


@router.get("/sources")
def sources():
    return {"data": {"items": passages(), "llm_used": False}}
