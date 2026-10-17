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
  LLM_BASE_URL   https://api.anthropic.com/v1/   (Claude, via its OpenAI-compatible layer)
                 https://api.openai.com/v1        (OpenAI)
                 http://<her-tailscale-ip>:11434/v1  (Ollama, on-prem)
  LLM_API_KEY    the provider key; any string for Ollama
  LLM_MODEL      e.g. claude-haiku-5-5  /  gpt-4o-mini  /  qwen2.5:7b
  If unset → template mode (no LLM calls; drafts come from templates). ｜ 没配就用模板

Usage ｜ 用法:
  from agent import run_agent
  result = run_agent(containers, scenario, top_n=5)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from time import perf_counter
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
    if "11434" in cfg["base_url"] or "localhost" in cfg["base_url"] or "100." in cfg["base_url"]:
        return "local"
    return "cloud"


def _client(cfg: dict):
    return OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])


def _is_anthropic(cfg: dict) -> bool:
    return "anthropic.com" in cfg["base_url"]


def _sampling(cfg: dict, temperature: float) -> dict:
    """Claude's OpenAI-compat layer rejects temperature < 1 on current models and ignores response_format,
    so omit both there. ｜ Claude 兼容层不接受 temperature<1、忽略 response_format，用 Claude 时不传。"""
    if _is_anthropic(cfg):
        return {}
    return {"temperature": temperature}


def _extract_json(text: str) -> dict:
    """Pull the first {...} object out of a reply that may include prose or code fences.
    从可能带说明文字或代码块的回复里抠出第一个 JSON 对象。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


class Trace:
    """Step-by-step record of what the agent did, for the UI to replay.
    agent 每一步的记录，前端逐行回放用。"""

    def __init__(self):
        self.steps: list[dict] = []
        self._t0 = perf_counter()
        self._last = self._t0

    def add(self, kind: str, text: str, ms: float | None = None, **detail):
        now = perf_counter()
        self.steps.append({
            "step": len(self.steps) + 1,
            "kind": kind,                       # observe | simulate | rank | llm | tool | draft | done
            "text": text,
            "ms": round((now - self._last) * 1000, 1) if ms is None else round(ms, 1),
            "t_ms": round((now - self._t0) * 1000, 1),
            **({"detail": detail} if detail else {}),
        })
        self._last = now


# ---------- Draft templates (fallback) ｜ 模板草稿（兜底） ----------

def _template_draft_zh(action: dict) -> dict:
    """Chinese templates for SHA ｜ 上海港中文模板"""
    cid = action["container_id"]
    cargo = {"reefer_pharma": "冷藏药品", "reefer_food": "冷藏食品", "hazmat": "危险品", "general": "普通货物", "empty": "空箱"}[action["cargo_type"]]
    fee = f"{action['demurrage_per_day']} 元/天"
    who = action["who"]
    b = action["blocker"]
    if b == "customs_hold":
        subject = f"申请加急放行 — {cid}"
        body = (f"海关老师您好：\n\n集装箱 {cid}（{cargo}）目前处于{action['fix'].split('the ')[-1]}状态，每日产生滞箱费 {fee}，货物时效性强。"
                f"请问需要补充哪些单证可以今日放行？\n\n谢谢，\n闸口调度")
    elif b == "source_conflict":
        subject = f"申报重量不符 — {cid}"
        body = (f"船公司您好：\n\n码头地磅称重与贵司申报的 {cid} 重量不一致。请重新确认申报状态和毛重，以便免开箱放行。"
                f"当前滞箱费 {fee}。\n\n谢谢，\n闸口调度")
    elif b == "reefer_silent":
        subject = f"冷藏箱传感器检查 — {cid}"
        body = f"冷藏技工：{cid}（{cargo}）已超过 90 分钟未上报温度，请确认供电和传感器状态。货物对温度敏感。"
    else:
        subject = f"转移至有电堆场 — {cid}"
        body = f"堆场调度：B 区断电，请将冷藏箱 {cid}（{cargo}）转移至 A 区有电箱位并确认插电。优先级：高。"
    return {"to": who, "subject": subject, "body": body, "source": "template", "language": "zh"}


def _template_draft(action: dict) -> dict:
    if action.get("language") == "zh":
        return _template_draft_zh(action)
    cid = action["container_id"]
    cargo = action["cargo_type"].replace("_", " ")
    who = action["who"]
    sym = {"USD": "$", "EUR": "€", "CNY": "¥"}.get(action.get("currency", "USD"), "$")
    fee = f"{sym}{action['demurrage_per_day']}/day"
    if action["blocker"] == "customs_hold":
        subject = f"Request to expedite release — {cid}"
        body = (f"Hello {who} team,\n\nContainer {cid} ({cargo}) is under a {action['fix'].split('the ')[-1]} at our terminal. "
                f"It is accruing {fee} in demurrage and is time-sensitive cargo. "
                f"Could you advise what documentation would allow us to clear it today?\n\nThank you,\nGate Planner")
    elif action["blocker"] == "source_conflict":
        subject = f"Declaration mismatch — {cid}"
        body = (f"Hello,\n\nOur terminal scale reads a different weight than your declaration for {cid}. "
                f"Please re-confirm the declared status and gross weight so we can release without a physical inspection. "
                f"Current demurrage: {fee}.\n\nThank you,\nGate Planner")
    elif action["blocker"] == "reefer_silent":
        subject = f"Reefer sensor check — {cid}"
        body = (f"Reefer tech: {cid} ({cargo}) has not reported temperature for over 90 minutes. "
                f"Please verify the unit is powered and the sensor is online. Cargo is temperature-sensitive.")
    else:  # zone_power
        subject = f"Move to powered zone — {cid}"
        body = (f"Yard ops: Zone B is unpowered. Please relocate reefer {cid} ({cargo}) to a powered slot in Zone A "
                f"and confirm plug-in. Priority: high.")
    return {"to": who, "subject": subject, "body": body, "source": "template", "language": "en"}


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
    "Use ONLY the facts given. Do not invent container numbers, amounts, dates or regulations. "
    "Write in the language specified by `language` (en = English, zh = Simplified Chinese). "
    "Return JSON: {\"subject\": str, \"body\": str}. Body under 120 words. Sign off as 'Gate Planner' (or '闸口调度' in Chinese)."
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
        "port": action.get("port"),
        "language": action.get("language", "en"),
        "currency": action.get("currency", "USD"),
        "demurrage_per_day": action["demurrage_per_day"],
        "unlocks_per_day": action["unlocks_per_day"],
        "current_action": action["before"]["action"],
        "if_fixed": action["after"]["action"],
    }
    try:
        kwargs = _sampling(cfg, 0.3)
        if not _is_anthropic(cfg):
            kwargs["response_format"] = {"type": "json_object"}
        resp = _client(cfg).chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": DRAFT_SYSTEM},
                      {"role": "user", "content": json.dumps(facts)}],
            **kwargs,
        )
        out = _extract_json(resp.choices[0].message.content)
        return {"to": action["who"], "subject": out["subject"], "body": out["body"], "source": _llm_source(cfg), "language": action.get("language", "en")}
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


def _summ(name: str, args: dict, result: dict) -> str:
    """One line per tool call for the trace ｜ 每次工具调用一行"""
    if name == "get_plan":
        n = len(result.get("actions", [])); c = result.get("candidates_considered", 0)
        return f"get_plan → {c} blocked boxes simulated, {n} clear today's gate"
    if name == "simulate_fix":
        b, a = result.get("before", {}), result.get("after", {})
        return (f"simulate_fix {args.get('container_id')} / {args.get('blocker')} → "
                f"{b.get('action')} #{b.get('rank')} → {a.get('action')} #{a.get('rank')}, +{result.get('unlocks_per_day', 0)}/day")
    return f"{name} → {str(result)[:80]}"


def _run_loop(client, cfg: dict, schemas, impl, top_n: int, trace: Trace, max_steps: int = 8) -> dict:
    messages = [{"role": "system", "content": AGENT_SYSTEM},
                {"role": "user", "content": f"Build today's action list with up to {top_n} items."}]
    for _ in range(max_steps):
        resp = client.chat.completions.create(model=cfg["model"], messages=messages,
                                              tools=schemas, tool_choice="auto", **_sampling(cfg, 0.2))
        msg = resp.choices[0].message
        if msg.tool_calls:
            trace.add("llm", f"Model ({cfg['model']}) requested {len(msg.tool_calls)} tool call(s)")
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                result = impl[name](**args) if name in impl else {"error": f"unknown tool {name}"}
                trace.add("tool", _summ(name, args, result), tool=name, args=args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})
            continue
        text = (msg.content or "").strip()
        trace.add("llm", "Model returned final plan")
        try:
            return _extract_json(text)
        except ValueError:
            return {"summary": text[:300], "actions": []}
    raise RuntimeError("agent did not finish within max_steps")


def run_agent(containers: list[dict], scenario: dict, top_n: int = 5) -> dict:
    """Entry point. Always returns a usable plan; degrades gracefully without an LLM.
    入口。没有 LLM 也能返回可用的清单。"""
    cfg = _llm_config()
    trace = Trace()
    sym = {"USD": "$", "EUR": "€", "CNY": "¥"}

    t0 = perf_counter()
    plan = next_actions(containers, scenario, top_n=top_n)   # ground truth ｜ 数字基准
    plan_ms = (perf_counter() - t0) * 1000
    by_id = {a["container_id"]: a for a in plan["actions"]}
    cur = sym.get(plan.get("currency", "USD"), "$")
    cands = plan.get("all_candidates", [])
    per_sim_ms = plan_ms * 0.9 / max(1, len(cands))   # simulation dominates next_actions ｜ 推演占大头

    # Observe → simulate → rank, as the deterministic backbone always does
    # 观察 → 推演 → 排序，这是确定性主干每次都走的步骤
    blocked = len({c["container_id"] for c in cands})
    trace.add("observe", f"Observed queue at {plan.get('port_name')}: {len(containers)} boxes, "
                         f"{blocked} blocked, gate capacity {plan['gate_capacity_today']} today",
              ms=plan_ms * 0.1, port=plan.get("port"), scenario=scenario)
    shown = 0
    for c in cands:
        if shown >= 8:
            break
        b, a = c["before"], c["after"]
        trace.add("simulate", f"If {c['who']} resolves {c['container_id']} ({c['blocker'].replace('_', ' ')}): "
                              f"{b['action']} #{b['rank']} → {a['action']} #{a['rank']}, +{cur}{c['unlocks_per_day']}/day",
                  ms=per_sim_ms, container_id=c["container_id"], blocker=c["blocker"], unlocks=c["unlocks_per_day"])
        shown += 1
    if len(cands) > shown:
        trace.add("simulate", f"… {len(cands) - shown} more fixes simulated", ms=per_sim_ms * (len(cands) - shown))
    trace.add("rank", f"Ranked {len(cands)} candidate fixes by {plan.get('currency')} unlocked; "
                      f"{len(plan['actions'])} actually clear today's gate, {len(cands) - len(plan['actions'])} would not move")

    summary = None
    whys: dict[str, str] = {}
    agent_mode = "deterministic"
    if cfg is not None:
        try:
            schemas, impl = make_tools(containers, scenario)
            out = _run_loop(_client(cfg), cfg, schemas, impl, top_n, trace)
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
            trace.add("llm", f"Model unavailable ({str(e)[:60]}); continuing with deterministic plan")

    actions_out = []
    for a in plan["actions"]:
        item = dict(a)
        item["why"] = whys.get(a["container_id"]) or f"{a['fix']} — unlocks {cur}{a['unlocks_per_day']}/day."
        item["draft"] = draft_outreach(a, cfg)
        item["requires_human_approval"] = True
        item["approval"] = {"status": "pending"}
        actions_out.append(item)
        trace.add("draft", f"Drafted outreach to {a['who']} for {a['container_id']} ({item['draft']['source']})",
                  container_id=a["container_id"], to=a["who"], source=item["draft"]["source"])

    trace.add("done", f"{len(actions_out)} action(s) ready, {cur}{plan['total_unlocked_per_day']}/day unlocked — awaiting planner approval; nothing sent")

    if summary is None:
        n = len(actions_out)
        sym = cur
        summary = (f"{n} action{'s' if n != 1 else ''} worth making today at {plan.get('port_name', 'the port')}: "
                   f"unlock {sym}{plan['total_unlocked_per_day']}/day against a gate capacity of {plan['gate_capacity_today']} boxes.")

    return {
        "scenario": plan["scenario"],
        "port": plan.get("port"),
        "port_name": plan.get("port_name"),
        "currency": plan.get("currency"),
        "gate_capacity_today": plan["gate_capacity_today"],
        "total_unlocked_per_day": plan["total_unlocked_per_day"],
        "summary": summary,
        "actions": actions_out,
        "total_unlocked_usd_per_day": plan["total_unlocked_usd_per_day"],
        "agent_mode": agent_mode,
        "nothing_is_sent_automatically": True,
        "trace": trace.steps,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
