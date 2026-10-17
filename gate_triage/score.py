"""
score.py — Gate Triage scoring engine ｜ 打分引擎

Usage ｜ 用法:
    from score import score, score_all
    result = score(container, scenario)
    ranked = score_all(containers, scenario)   # sorted by priority desc ｜ 按 priority 降序

scenario = {"lanes_open": 8, "customs_online": True, "power_zone_b": True}

Two kinds of signal ｜ 两类信号:
  True conflict  — two sources disagree with each other        -> conflict_score
  真冲突          — 两个来源说的事对不上
  Single-source alert — one source sees a problem others can't  -> urgency
  单源警报        — 一个来源发现问题，其他来源管不到
"""
from copy import deepcopy
from datetime import datetime

try:
    from gate_triage.port_profiles import get_profile, compute_fees
except ImportError:  # running as a loose script ｜ 作为脚本直接运行时
    from port_profiles import get_profile, compute_fees

NOW = datetime(2026, 10, 17, 8, 0, 0)   # snapshot time of the dataset ｜ 数据快照时间

DEFAULT_SCENARIO = {"lanes_open": 8, "customs_online": True, "power_zone_b": True}

# How critical each cargo / consignee type is ｜ 货物 / 收货方的重要程度
CARGO_W = {"reefer_pharma": 1.0, "reefer_food": 0.8, "hazmat": 0.7, "general": 0.4, "empty": 0.1}
CONSIGNEE_W = {"hospital": 1.0, "grocery": 0.7, "retail": 0.5, "unknown": 0.4}

def max_fee(profile):
    """Upper bound of demurrage at this port, for normalising the cost term. ｜ 该港口滞港费上限，归一化用。"""
    port_top = profile["port_tiers"][-1][1]
    reefer_top = profile["carrier_tiers"]["reefer"][-1][1]
    reefer_top = reefer_top[1] if isinstance(reefer_top, tuple) else reefer_top
    return float(port_top + reefer_top * 1.5)


def clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# ---------- 1. Trust per source ｜ 每个来源的信任分 ----------

def compute_trust(c, scenario):
    """Each source gets a 0–1 trust score. This is what sets us apart from a plain mismatch dashboard.
    每个来源一个 0–1 的信任分，这是和普通"标矛盾"看板的区别。"""
    s = c["sources"]

    # Carrier: based on how often its declarations disagreed with the scale recently
    # 船司：看最近 10 次申报有几次和地磅对不上
    carrier_trust = clip(1.0 - s["carrier"].get("history_mismatches_last10", 0) / 10.0)

    # Scale: most objective source, fixed ｜ 地磅：最客观，固定
    scale_trust = 0.95

    # Customs: if their system is offline, hold status can't be verified
    # 海关：系统宕机时 hold 状态不可信
    customs_trust = 1.0 if scenario.get("customs_online", True) else 0.3

    # Reefer sensor: trust decays the longer it's been silent
    # 冷藏传感器：失联越久越不可信
    if s["reefer"] is None:
        reefer_trust = None
    else:
        ping = s["reefer"]["last_ping_min"]
        reefer_trust = 1.0 if ping <= 30 else clip(1.0 - ping / 180.0)

    return carrier_trust, scale_trust, customs_trust, reefer_trust


# ---------- 2. True conflicts ｜ 真冲突 ----------

def compute_conflicts(c, carrier_trust, scale_trust):
    """Returns (conflict_score, [notes]). Only counts cases where two sources contradict each other.
    Carrier trust sets how much declared-vs-scale gap we tolerate: a carrier with a bad record gets
    scrutinised at a 20% gap, a reliable one at 30%.
    返回 (conflict_score, [冲突描述])。只算两个来源互相矛盾的情况。
    船司信任分决定容忍多大的申报差：信誉差的差 20% 就查，信誉好的差 30% 才查。"""
    s = c["sources"]
    declared = s["carrier"]["declared_status"]
    dw = s["carrier"]["declared_weight_kg"]
    sw = s["scale"]["weight_kg"]
    gap_threshold = 0.15 + 0.15 * carrier_trust      # trust 1.0 → 30%, trust 0.4 → 21% ｜ 信任越低审得越严
    del scale_trust                                   # scale is the reference measurement; kept in signature for symmetry ｜ 地磅是基准
    score = 0.0
    notes = []

    # Carrier says empty, scale says heavy (empty 40ft ≈ 3.9t)
    # 船司说空柜，地磅称出重柜（空 40 尺柜约 3.9 吨）
    if declared == "empty" and sw > 8000:
        score += 0.7
        notes.append(f"carrier declares empty but scale reads {sw/1000:.1f}t")

    # Declared weight off by more than the trust-scaled tolerance ｜ 申报重量和地磅差超过（按信任分缩放的）容忍度
    if declared == "laden" and sw > 0 and abs(dw - sw) / sw > gap_threshold:
        score += 0.5
        notes.append(f"declared {dw/1000:.1f}t vs scale {sw/1000:.1f}t, beyond the {gap_threshold:.0%} tolerance")

    return clip(score), notes


# ---------- 3. Urgency ｜ 紧急度 ----------

# Normal day: optimise for money (demurrage, overdue).
# Crisis: optimise for what matters (cargo type, consignee, temperature).
# This weight switch is what makes a box jump the queue when lanes go down.
# 平时按钱排（滞港费、超期）；灾时按货排（货物类型、收货方、温度）。
# 权重切换就是车道减半时关键物资能跳到最前面的原因。
WEIGHTS_NORMAL = dict(cargo=0.20, consignee=0.10, temp=0.15, silent=0.05, overdue=0.25, cost=0.25)
WEIGHTS_CRISIS = dict(cargo=0.30, consignee=0.20, temp=0.30, silent=0.10, overdue=0.05, cost=0.05)


def is_crisis(scenario):
    return (scenario.get("lanes_open", 8) < 8
            or not scenario.get("customs_online", True)
            or not scenario.get("power_zone_b", True))


def compute_urgency(c, reefer_trust, scenario):
    s = c["sources"]
    r = s["reefer"]
    w = WEIGHTS_CRISIS if is_crisis(scenario) else WEIGHTS_NORMAL

    if r is None:
        temp_drift = 0.0
        reefer_silent = 0.0
    else:
        # Only warming counts; +4°C → 0.4, +8°C → 0.8. Scaled by sensor trust.
        # 只算升温；高 4°C → 0.4，高 8°C → 0.8。乘以传感器信任分。
        temp_drift = clip((r["temp_c"] - r["setpoint_c"]) / 10.0) * reefer_trust
        # Silence itself is urgent: 30 min → 0, 90 min → 0.4, 180 min → 1
        # 失联本身就是急：30 分钟 0，90 分钟 0.4，180 分钟 1
        reefer_silent = clip((r["last_ping_min"] - 30) / 150.0)

    overdue = clip(-c["free_days_left"] / 6.0)              # 6 days overdue → 1 ｜ 超期 6 天 → 1
    cost = clip(c["demurrage_per_day"] / max_fee(c["_profile"]))

    urgency = (w["cargo"] * CARGO_W[c["cargo_type"]]
               + w["consignee"] * CONSIGNEE_W[c["consignee_type"]]
               + w["temp"] * temp_drift
               + w["silent"] * reefer_silent
               + w["overdue"] * overdue
               + w["cost"] * cost)
    return clip(urgency), temp_drift, reefer_silent


# ---------- 4. Action ｜ 动作 ----------

def decide_action(c, scenario, conflict_score, urgency, temp_drift, customs_trust):
    """Rules checked in order; first match wins. ｜ 按顺序判断，命中即停。"""
    s = c["sources"]
    lanes = scenario.get("lanes_open", 8)
    power_b = scenario.get("power_zone_b", True)
    # Fixed bar for "eligible to release". Lane count does NOT move it: with fewer lanes, the day's
    # capacity cut in next_actions / stats decides who actually gets out. ｜ 门槛固定；车道减少时由容量截断决定谁出闸
    release_threshold = 0.25
    has_reefer = s["reefer"] is not None
    hold = s["customs"]["hold"]

    if conflict_score >= 0.5:
        return "inspect", "data conflict", "R1_source_conflict"          # sources contradict → a human looks ｜ 数据打架，人看
    if hold and customs_trust >= 0.5:
        return "slow", f"customs {s['customs']['hold_type']} hold, ~{s['customs']['est_days_to_clear']}d", "R2_customs_hold"
    if hold and customs_trust < 0.5:
        return "inspect", "customs offline, hold unverified", "R3_customs_offline"   # 海关宕机，hold 不可信
    if has_reefer and c["zone"] == "B" and not power_b:
        return "reroute", "zone B unpowered", "R4_zone_power_loss"        # every reefer in B will warm ｜ B 区冷藏柜迟早升温
    if not scenario.get("customs_online", True):
        return "slow", "customs offline, clearance unverified", "R3_clearance_unverified"
    if has_reefer and temp_drift > 0.3:
        return "release", "reefer warming", "R5_reefer_warming"           # get it out before it spoils ｜ 坏之前赶紧走
    if urgency >= release_threshold:
        return "release", "high urgency", "R6_urgency_threshold"
    return "slow", "below threshold", "R7_default_queue"


# ---------- 5. Reason ｜ 理由 ----------

def build_reason(c, action, why, conflict_notes, temp_drift, reefer_silent, carrier_trust, scenario=None):
    """One plain-English line a planner can read. Template for now; LLM polish later.
    一句接线员能看懂的英文。先用模板，之后可让 LLM 润色。"""
    s = c["sources"]
    r = s["reefer"]
    parts = []
    scenario = scenario or DEFAULT_SCENARIO
    if not scenario.get("customs_online", True):
        parts.append("customs offline; verify clearance before any gate release")
    if r is not None and c["zone"] == "B" and not scenario.get("power_zone_b", True):
        parts.append("zone B unpowered; arrange authorized powered storage")

    if conflict_notes:
        parts.append("; ".join(conflict_notes).capitalize() + f" (carrier trust {carrier_trust:.1f})")
    if r is not None and temp_drift > 0.3:
        parts.append(f"reefer at {r['temp_c']}°C vs {r['setpoint_c']}°C setpoint")
    if r is not None and reefer_silent > 0.3:
        parts.append(f"reefer sensor silent {r['last_ping_min']} min")
    if s["customs"]["hold"]:
        parts.append(f"customs {s['customs']['hold_type'].replace('_', ' ')} hold; do not release")
    if c["free_days_left"] < 0:
        parts.append(f"{-c['free_days_left']}d overdue at {c['_profile']['symbol']}{c['demurrage_per_day']}/day")

    verb = {
        "inspect": "Hold for inspection",
        "slow": "Queue",
        "release": "Release",
        "reroute": "Reroute to powered zone",
    }[action]

    if parts:
        return f"{verb}: " + ", ".join(parts) + "."
    return f"{verb}: {why}."


# ---------- Entry points ｜ 入口 ----------

def score(container, scenario=None):
    """Score one container. Returns a copy with trust, priority, action, reason added.
    给一个柜子打分。返回副本，加上 trust / priority / action / reason。"""
    scenario = scenario or DEFAULT_SCENARIO
    c = deepcopy(container)

    # Port profile (Twist 2): currency, free time, tariff tiers, agency names all come from here.
    # Fees are recomputed so the same box can be viewed at any port.
    # 港口配置（Twist 2）：货币、免费期、费率阶梯、机构名称都从这来。费用重算，同一个柜子可以放到任何港口看。
    profile = get_profile(scenario.get("port"))
    c.update(compute_fees(profile, c["cargo_type"], c["arrived_at"], NOW, c["container_id"]))
    c["_profile"] = profile

    carrier_t, scale_t, customs_t, reefer_t = compute_trust(c, scenario)
    conflict_score, conflict_notes = compute_conflicts(c, carrier_t, scale_t)
    urgency, temp_drift, reefer_silent = compute_urgency(c, reefer_t if reefer_t is not None else 0.0, scenario)
    action, why, rule = decide_action(c, scenario, conflict_score, urgency, temp_drift, customs_t)
    # Conflicts rank high too — someone needs to look at them soon
    # 冲突也要排前面，因为需要人赶紧看
    priority = 0.65 * urgency + 0.35 * conflict_score
    reason = build_reason(c, action, why, conflict_notes, temp_drift, reefer_silent, carrier_t, scenario)

    c["sources"]["carrier"]["trust"] = round(carrier_t, 2)
    c["sources"]["scale"]["trust"] = round(scale_t, 2)
    c["sources"]["customs"]["trust"] = round(customs_t, 2)
    if c["sources"]["reefer"] is not None:
        c["sources"]["reefer"]["trust"] = round(reefer_t, 2)

    c["priority"] = round(priority, 3)
    c["urgency"] = round(urgency, 3)
    c["conflict_score"] = round(conflict_score, 3)
    c["action"] = action
    c["reason"] = reason
    # Audit record: what fired, under which scenario, with what trust. For compliance / funding reviews.
    # 可审计记录：命中哪条规则、什么场景、当时各来源信任分多少。给监管和资助方看的。
    c["decision_trace"] = {
        "rule_fired": rule,
        "mode": "crisis" if is_crisis(scenario) else "normal",
        "scenario": dict(scenario),
        "trust_at_decision": {
            "carrier": round(carrier_t, 2),
            "scale": round(scale_t, 2),
            "customs": round(customs_t, 2),
            "reefer": round(reefer_t, 2) if reefer_t is not None else None,
        },
        "release_threshold": 0.25,
        "weights": dict(WEIGHTS_CRISIS if is_crisis(scenario) else WEIGHTS_NORMAL),
        "port": profile["code"],
    }
    c.pop("_profile", None)
    return c


def score_all(containers, scenario=None):
    """Score every container and sort by priority, highest first.
    全部打分，按 priority 从高到低排。"""
    scored = [score(c, scenario) for c in containers]
    scored.sort(key=lambda x: x["priority"], reverse=True)
    return scored


# ---------- Next best actions ｜ 下一步最值得做的事 ----------
#
# Counterfactual: for every box with a blocker, pretend the blocker is fixed, re-score,
# and measure what that unlocks. The agent calls this; the LLM never computes the numbers.
# 反事实推演：对每个有卡点的柜子，假设卡点解决了，重打分，看解锁了多少。
# agent 调这个工具拿数字，LLM 不算钱。

BLOCKERS = {
    # key: (detect, apply_fix, fix_label, who)
    "customs_hold": (
        # intensive exams are physical and can't be chased — not a candidate ｜ 开箱查验催不动，不列
        lambda c, sc: c["sources"]["customs"]["hold"] and c["sources"]["customs"]["hold_type"] != "intensive",
        lambda c: c["sources"]["customs"].update({"hold": False, "hold_type": "none", "est_days_to_clear": 0}),
        "Chase {customs} to clear the {hold_type}",
        "customs",
    ),
    "source_conflict": (
        lambda c, sc: c["conflict_score"] >= 0.5,
        lambda c: c["sources"]["carrier"].update({
            "declared_status": "laden" if c["sources"]["scale"]["weight_kg"] > 8000 else "empty",
            "declared_weight_kg": c["sources"]["scale"]["weight_kg"],
        }),
        "Ask carrier to re-declare; scale reads {scale_t}t",
        "carrier",
    ),
    "reefer_silent": (
        lambda c, sc: c["sources"]["reefer"] is not None and c["sources"]["reefer"]["last_ping_min"] > 90,
        lambda c: c["sources"]["reefer"].update({"last_ping_min": 5}),
        "Dispatch reefer tech; sensor silent {ping} min",
        "reefer_tech",
    ),
    "zone_power": (
        lambda c, sc: c["sources"]["reefer"] is not None and c["zone"] == "B" and not sc.get("power_zone_b", True),
        lambda c: c.update({"zone": "A"}),
        "Move to powered {zone_powered}",
        "yard",
    ),
}


CONTAINERS_PER_LANE_PER_DAY = 12   # matches backend Settings ｜ 和后端配置一致


def _rank_of(container_id, ranked):
    for i, c in enumerate(ranked):
        if c["container_id"] == container_id:
            return i + 1
    return None


def _out_today(container_id, ranked, scenario):
    """Does this box actually leave the gate today? Must be 'release' AND within the day's lane capacity.
    今天能不能真的出闸：必须是放行，而且排在当天车道容量之内。"""
    capacity = scenario.get("lanes_open", 8) * CONTAINERS_PER_LANE_PER_DAY
    releases = [c["container_id"] for c in ranked if c["action"] == "release"]
    return container_id in releases[:capacity]


def simulate_fix(container, blocker, containers, scenario=None, before_q=None):
    """Pretend `blocker` is resolved on this container; re-score the whole queue; report the delta.
    Pass `before_q` (the already-scored queue) when calling in a loop to avoid re-scoring it each time.
    假设这个柜子的卡点已解决，整队重打分，返回前后差异。循环调用时传入 before_q 避免重复打分。"""
    scenario = scenario or DEFAULT_SCENARIO
    detect, apply_fix, label, who = BLOCKERS[blocker]

    if before_q is None:
        before_q = score_all(containers, scenario)
    before = next(c for c in before_q if c["container_id"] == container["container_id"])

    fixed = deepcopy(container)
    apply_fix(fixed)
    others = [c for c in containers if c["container_id"] != container["container_id"]]
    after_q = score_all(others + [fixed], scenario)
    after = next(c for c in after_q if c["container_id"] == container["container_id"])

    # $ unlocked: fixing the blocker gets the box out the gate today when it otherwise wouldn't.
    # Capacity-aware, so under lane shortage only fixes that win a real slot count.
    # 解锁多少钱：修好之后今天能出闸、不修就出不去。按容量算，车道减半时只有真能抢到名额的才算。
    cid = container["container_id"]
    was_out = _out_today(cid, before_q, scenario)
    now_out = _out_today(cid, after_q, scenario)
    profile = get_profile(scenario.get("port"))
    unlocked_local = before["demurrage_per_day"] if (now_out and not was_out) else 0
    unlocked_usd = before["demurrage_usd_per_day"] if (now_out and not was_out) else 0

    r = container["sources"]["reefer"]
    if profile["language"] == "zh":   # localized action text ｜ 行动文案本地化
        label = {
            "customs_hold": "联系{customs}解除{hold_type}",
            "source_conflict": "请船公司重新申报；地磅实称 {scale_t} 吨",
            "reefer_silent": "派冷藏技工检查；传感器已 {ping} 分钟未上报",
            "zone_power": "转移至有电的{zone_powered}",
        }[blocker]
    fix_text = label.format(
        customs=profile["customs_agency"],
        hold_type=profile["hold_labels"].get(container["sources"]["customs"]["hold_type"], "hold"),
        scale_t=f"{container['sources']['scale']['weight_kg'] / 1000:.1f}",
        ping=r["last_ping_min"] if r else 0,
        zone_powered=profile["zone_powered"],
    )
    return {
        "container_id": container["container_id"],
        "cargo_type": container["cargo_type"],
        "consignee_type": container["consignee_type"],
        "blocker": blocker,
        "fix": fix_text,
        "who": profile["who"][who],
        "who_role": who,
        "port": profile["code"],
        "currency": profile["currency"],
        "language": profile["language"],
        "before": {"action": before["action"], "rank": _rank_of(cid, before_q), "priority": before["priority"], "out_today": was_out},
        "after":  {"action": after["action"],  "rank": _rank_of(cid, after_q),  "priority": after["priority"], "out_today": now_out},
        "unlocks_per_day": unlocked_local,
        "unlocks_usd_per_day": unlocked_usd,
        "demurrage_per_day": before["demurrage_per_day"],
        "demurrage_usd_per_day": before["demurrage_usd_per_day"],
    }


def next_actions(containers, scenario=None, top_n=5):
    """The planner's morning list: which blockers are worth resolving first, by $ unlocked.
    值班员的行动清单：先解决哪个卡点最值，按解锁金额排序。"""
    scenario = scenario or DEFAULT_SCENARIO
    scored = score_all(containers, scenario)
    by_id = {c["container_id"]: c for c in scored}

    candidates = []
    for raw in containers:
        c = by_id[raw["container_id"]]
        for blocker, (detect, *_rest) in BLOCKERS.items():
            if detect(c, scenario):
                candidates.append(simulate_fix(raw, blocker, containers, scenario, before_q=scored))

    # Primary sort: money unlocked. Tie-break: how far the box climbs, then its own demurrage.
    # 先按解锁金额，再按排名提升，再按自身滞港费。
    candidates.sort(key=lambda a: (
        a["unlocks_per_day"],
        (a["before"]["rank"] or 999) - (a["after"]["rank"] or 999),
        a["demurrage_per_day"],
    ), reverse=True)

    # One action per container, and only actions that actually get a box out today.
    # Under lane shortage this list gets shorter — that is the point: don't chase what won't move.
    # 每个柜子只列一条，且只列今天真能放出去的。车道减半时清单会变短，这正是意义：别催那些催了也走不了的。
    seen, plan = set(), []
    for a in candidates:
        if a["container_id"] in seen or a["unlocks_per_day"] <= 0:
            continue
        seen.add(a["container_id"])
        plan.append(a)
        if len(plan) == top_n:
            break

    capacity = scenario.get("lanes_open", 8) * CONTAINERS_PER_LANE_PER_DAY
    profile = get_profile(scenario.get("port"))
    return {
        "scenario": dict(scenario),
        "port": profile["code"],
        "port_name": profile["name"],
        "currency": profile["currency"],
        "gate_capacity_today": capacity,
        "actions": plan,
        "all_candidates": candidates,   # every simulated fix, for the agent trace ｜ 全部推演结果，给轨迹用
        "total_unlocked_per_day": sum(a["unlocks_per_day"] for a in plan),
        "total_unlocked_usd_per_day": sum(a["unlocks_usd_per_day"] for a in plan),
        "candidates_considered": len(candidates),
        "estimate_notice": "Synthetic tariff assumptions. Each candidate is an independent counterfactual; totals are not a joint schedule or realized savings.",
    }


# ---------- Self-test ｜ 自测 ----------

if __name__ == "__main__":
    import json
    from collections import Counter

    data = json.load(open("containers.json"))
    HERO = "TRXU7731902"   # demo hero: hospital vaccine reefer, Zone B, warming ｜ demo 主角

    scenarios = {
        "Normal":           {"lanes_open": 8, "customs_online": True,  "power_zone_b": True},
        "Lanes -50%":       {"lanes_open": 4, "customs_online": True,  "power_zone_b": True},
        "Customs down":     {"lanes_open": 8, "customs_online": False, "power_zone_b": True},
        "Zone B power out": {"lanes_open": 8, "customs_online": True,  "power_zone_b": False},
    }

    for name, sc in scenarios.items():
        ranked = score_all(data, sc)
        actions = Counter(c["action"] for c in ranked)
        hero_rank = next(i + 1 for i, c in enumerate(ranked) if c["container_id"] == HERO)
        hero = next(c for c in ranked if c["container_id"] == HERO)
        print(f"\n=== {name} ===")
        print("  actions:", dict(actions))
        print(f"  HERO rank #{hero_rank}  action={hero['action']}  priority={hero['priority']}  urgency={hero['urgency']}")
        print(f"  HERO reason: {hero['reason']}")

    # Rule checks against the injected conflicts ｜ 用埋进去的冲突对答案
    normal = score_all(data, scenarios["Normal"])
    by_conf = {}
    for c in normal:
        by_conf.setdefault(c["_conflict"], []).append(c["action"])
    print("\n=== Normal: action by injected conflict ===")
    for k, v in sorted(by_conf.items()):
        print(f"  {k:35s} {dict(Counter(v))}")

    assert all(c["conflict_score"] == 0 for c in normal if c["_conflict"] == "none"), "clean boxes should have 0 conflict"
    assert all(c["action"] == "inspect" for c in normal if c["_conflict"] in ("empty_but_heavy", "weight_mismatch")), "true conflicts -> inspect"
    cd = score_all(data, scenarios["Customs down"])
    assert all(c["action"] == "inspect" for c in cd if c["sources"]["customs"]["hold"]), "customs down: holds -> inspect"
    zb = score_all(data, scenarios["Zone B power out"])
    zb_reefers = [c for c in zb if c["zone"] == "B" and c["sources"]["reefer"] and c["action"] not in ("inspect", "slow")]
    print(f"\nZone B reefer actions (non-inspect/slow): {dict(Counter(c['action'] for c in zb_reefers))}")
    print("\nAll assertions passed.")
