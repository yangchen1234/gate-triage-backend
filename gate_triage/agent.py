"""
agent.py — Gate Triage planner agent ｜ 值班员助手 agent

What it does ｜ 做什么:
  Looks at today's queue, finds the blockers worth resolving, and drafts the outreach
  (email / call script) for each one. A human approves every action; nothing is sent.
  看队列 → 找最值得解决的卡点 → 把邮件/电话稿写好 → 人批准才发。

Division of labour ｜ 分工:
  Numbers  ($ unlocked, rank changes)  → deterministic tools in score.py   ｜ 数字来自确定性工具
  Words    (drafts, summary)           → the LLM                            ｜ 文字由 LLM 写
  Sending  (email, release)            → never automated                    ｜ 永远不自动发

LLM config (env) ｜ 环境变量:
  LLM_BASE_URL   e.g. https://api.openai.com/v1   or   http://<her-tailscale-ip>:11434/v1  (Ollama)
  LLM_API_KEY    any string for Ollama
  LLM_MODEL      e.g. gpt-4o-mini  or  qwen2.5:7b
  If unset → template mode (no LLM calls; drafts come from templates). ｜ 没配就用模板

Usage ｜ 用法:
  from agent import run_agent
  result = run_agent(containers, scenario, top_n=5)
"""
from __future__ import annotations

import json
import os
from typing import Any

from gate_triage.score import BLOCKERS, next_actions, simulate_fix, score_all  # noqa: F401

try:  # optional dependency ｜ 可选依赖
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


# ---------- LLM client ｜ LLM 客户端 ----------

def _llm_config() -> dict | None:
    base = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    if not base or not model or OpenAI is None:
        return None
    return {"base_url": base, "api_key": os.getenv("LLM_API_KEY", "ollama"), "model": model}


def _llm_source(cfg: dict | None) -> str:
    if cfg is None:
        return "template"
    return "local" if ("11434" in cfg["base_url"] or "localhost" in cfg["base_url"] or "100." in cfg["base_url"]) else "cloud"


def _client(cfg: dict):
    return OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])


# ---------- Draft templates (fallback) ｜ 模板草稿（兜底） ----------

def _template_draft(action: dict) -> dict:
    cid = action["container_id"]
    cargo = action["cargo_type"].replace("_", " ")
    usd = action["unlocks_usd_per_day"]
    who = action["who"]
    if action["blocker"] == "customs_hold":
        subject = f"Request to expedite release — {cid}"
        body = (f"Hello CBP team,\n\nContainer {cid} ({cargo}) is under a {action['fix'].split('the ')[-1]} at our terminal. "
                f"It is accruing ${action['demurrage_usd_per_day']}/day in demurrage and is time-sensitive cargo. "
                f"Could you advise what documentation would allow us to clear it today?\n\nThank you,\nGate Planner")
    elif action["blocker"] == "source_conflict":
        subject = f"Declaration mismatch — {cid}"
        body = (f"Hello,\n\nOur terminal scale reads a different weight than your declaration for {cid}. "
                f"Please re-confirm the declared status and gross weight so we can release without a physical inspection. "
                f"Current demurrage: ${action['demurrage_usd_per_day']}/day.\n\nThank you,\nGate Planner")
    elif action["blocker"] == "reefer_silent":
        subject = f"Reefer sensor check — {cid}"
        body = (f"Reefer tech: {cid} ({cargo}) has not reported temperature for over 90 minutes. "
                f"Please verify the unit is powered and the sensor is online. Cargo is temperature-sensitive.")
    else:  # zone_power
        subject = f"Move to powered zone — {cid}"
        body = (f"Yard ops: Zone B is unpowered. Please relocate reefer {cid} ({cargo}) to a powered slot in Zone A "
                f"and confirm plug-in. Priority: high.")
    return {"to": who, "subject": subject, "body": body, "source": "template"}


# ---------- Tools the agent can call ｜ agent 可调用的工具 ----------

def make_tools(containers: list[dict], scenario: dict):
    """Bind tools to the current queue. Returns (schemas, implementations)."""

    def get_plan(top_n: int = 5) -> dict:
        return next_actions(containers, scenario, top_n=top_n)

    def simulate(container_id: str, blocker: str) -> dict:
        raw = next((c for c in containers if c["container_id"] == container_id), None)
        if raw is None:
            return {"error": f"unknown container {container_id}"}
        if blocker not in BLOCKERS:
            return {"error": f"unknown blocker {blocker}; valid: {list(BLOCKERS)}"}
        return simulate_fix(raw, blocker, containers, scenario)

    impl = {"get_plan": get_plan, "simulate_fix": simulate}

    schemas = [
        {"type": "function", "function": {
            "name": "get_plan",
            "description": "Today's top blockers worth resolving, ranked by demurrage unlocked. Numbers are authoritative.",
            "parameters": {"type": "object", "properties": {"top_n": {"type": "integer", "default": 5}}}}},
        {"type": "function", "function": {
            "name": "simulate_fix",
            "description": "What happens if one blocker on one container is resolved: action, rank and $ before vs after.",
            "parameters": {"type": "object", "required": ["container_id", "blocker"],
                           "properties": {"container_id": {"type": "string"},
                                          "blocker": {"type": "string", "enum": list(BLOCKERS)}}}}},
    ]
    return schemas, impl


# ---------- Drafting ｜ 写草稿 ----------

DRAFT_SYSTEM = (
    "You draft short, professional outreach for a port terminal gate planner. "
    "Use ONLY the facts given. Do not invent container numbers, dollar amounts, dates or regulations. "
    "Return JSON: {\"subject\": str, \"body\": str}. Body under 120 words. No sign-off beyond 'Gate Planner'."
)


def draft_outreach(action: dict, cfg: dict | None) -> dict:
    """LLM writes the email/call script for one action; template if no LLM or on error."""
    if cfg is None:
        return _template_draft(action)
    facts = {
        "to": action["who"],
        "container_id": action["container_id"],
        "cargo": action["cargo_type"],
        "consignee": action["consignee_type"],
        "blocker": action["blocker"],
        "requested_fix": action["fix"],
        "demurrage_usd_per_day": action["demurrage_usd_per_day"],
        "unlocks_usd_per_day": action["unlocks_usd_per_day"],
        "current_action": action["before"]["action"],
        "if_fixed": action["after"]["action"],
    }
    try:
        resp = _client(cfg).chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": DRAFT_SYSTEM},
                      {"role": "user", "content": json.dumps(facts)}],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        out = json.loads(resp.choices[0].message.content)
        return {"to": action["who"], "subject": out["subject"], "body": out["body"], "source": _llm_source(cfg)}
    except Exception as e:  # any failure → template ｜ 任何失败都回退模板
        d = _template_draft(action)
        d["fallback_reason"] = str(e)[:120]
        return d


# ---------- The agent loop ｜ agent 循环 ----------

AGENT_SYSTEM = (
    "You are the assistant to a port terminal gate planner. Capacity is limited today. "
    "Your job: produce today's action list — which blockers to resolve first and why. "
    "Rules: (1) Call get_plan first. (2) You may call simulate_fix to compare alternatives. "
    "(3) All numbers must come from tool results; never estimate. (4) You never release cargo or send messages; "
    "a human approves each item. (5) Finish with JSON: "
    "{\"summary\": one sentence for the planner, \"actions\": [{\"container_id\": str, \"blocker\": str, \"why\": one sentence}]}."
)


def _run_loop(client, cfg: dict, schemas, impl, top_n: int, max_steps: int = 8) -> dict:
    messages = [{"role": "system", "content": AGENT_SYSTEM},
                {"role": "user", "content": f"Build today's action list with up to {top_n} items."}]
    for _ in range(max_steps):
        resp = client.chat.completions.create(model=cfg["model"], messages=messages,
                                              tools=schemas, tool_choice="auto", temperature=0.2)
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                result = impl[name](**args) if name in impl else {"error": f"unknown tool {name}"}
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
            continue
        text = (msg.content or "").strip()
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1]) if start >= 0 else {"summary": text, "actions": []}
    raise RuntimeError("agent did not finish within max_steps")


def run_agent(containers: list[dict], scenario: dict, top_n: int = 5) -> dict:
    """Entry point. Always returns a usable plan; degrades gracefully without an LLM.
    入口。没有 LLM 也能返回可用的清单。"""
    cfg = _llm_config()
    plan = next_actions(containers, scenario, top_n=top_n)   # ground truth ｜ 数字基准
    by_id = {a["container_id"]: a for a in plan["actions"]}

    summary = None
    whys: dict[str, str] = {}
    agent_mode = "deterministic"
    if cfg is not None:
        try:
            schemas, impl = make_tools(containers, scenario)
            out = _run_loop(_client(cfg), cfg, schemas, impl, top_n)
            summary = out.get("summary")
            # Keep only container_ids the tools actually proposed; the LLM cannot add boxes.
            # 只保留工具给出的柜子，LLM 不能自己加。
            for item in out.get("actions", []):
                if item.get("container_id") in by_id:
                    whys[item["container_id"]] = item.get("why", "")
            agent_mode = _llm_source(cfg)
        except Exception as e:
            summary = None
            agent_mode = f"deterministic (agent error: {str(e)[:80]})"

    actions_out = []
    for a in plan["actions"]:
        item = dict(a)
        item["why"] = whys.get(a["container_id"]) or f"{a['fix']} — unlocks ${a['unlocks_usd_per_day']}/day."
        item["draft"] = draft_outreach(a, cfg)
        item["requires_human_approval"] = True
        actions_out.append(item)

    if summary is None:
        n = len(actions_out)
        summary = (f"{n} actions today unlock ${plan['total_unlocked_usd_per_day']}/day "
                   f"against a gate capacity of {plan['gate_capacity_today']} boxes.")

    return {
        "scenario": plan["scenario"],
        "gate_capacity_today": plan["gate_capacity_today"],
        "summary": summary,
        "actions": actions_out,
        "total_unlocked_usd_per_day": plan["total_unlocked_usd_per_day"],
        "agent_mode": agent_mode,
        "nothing_is_sent_automatically": True,
    }


# ---------- Self-test ｜ 自测 ----------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "containers.json")))
    sc = {"lanes_open": 4, "customs_online": True, "power_zone_b": True}
    r = run_agent(data, sc)
    print(f"mode={r['agent_mode']}  capacity={r['gate_capacity_today']}  total=${r['total_unlocked_usd_per_day']}/day")
    print("summary:", r["summary"])
    for i, a in enumerate(r["actions"], 1):
        print(f"\n{i}. {a['container_id']} [{a['who']}] {a['fix']}  (+${a['unlocks_usd_per_day']}/day)")
        print(f"   why: {a['why']}")
        print(f"   draft[{a['draft']['source']}] {a['draft']['subject']}")
        print("   " + a["draft"]["body"].replace("\n", "\n   ")[:300])
