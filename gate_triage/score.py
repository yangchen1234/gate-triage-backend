"""
score.py — Gate Triage scoring engine ｜ 打分引擎

Usage ｜ 用法:
    from gate_triage.score import score, score_all
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

DEFAULT_SCENARIO = {"lanes_open": 8, "customs_online": True, "power_zone_b": True}

# How critical each cargo / consignee type is ｜ 货物 / 收货方的重要程度
CARGO_W = {"reefer_pharma": 1.0, "reefer_food": 0.8, "hazmat": 0.7, "general": 0.4, "empty": 0.1}
CONSIGNEE_W = {"hospital": 1.0, "grocery": 0.7, "retail": 0.5, "unknown": 0.4}

MAX_DEMURRAGE = 750.0   # upper bound in the dataset, for normalisation ｜ 数据里的上限，用来归一化


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
    返回 (conflict_score, [冲突描述])。只算两个来源互相矛盾的情况。"""
    s = c["sources"]
    declared = s["carrier"]["declared_status"]
    dw = s["carrier"]["declared_weight_kg"]
    sw = s["scale"]["weight_kg"]
    score = 0.0
    notes = []

    # Carrier says empty, scale says heavy (empty 40ft ≈ 3.9t)
    # 船司说空柜，地磅称出重柜（空 40 尺柜约 3.9 吨）
    if declared == "empty" and sw > 8000:
        score += 0.7
        notes.append(f"carrier declares empty but scale reads {sw/1000:.1f}t")

    # Declared weight off by more than 30% ｜ 申报重量和地磅差 30% 以上
    if declared == "laden" and sw > 0 and abs(dw - sw) / sw > 0.30:
        score += 0.5
        notes.append(f"declared {dw/1000:.1f}t vs scale {sw/1000:.1f}t")

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
    cost = clip(c["demurrage_usd_per_day"] / MAX_DEMURRAGE)

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
    # With half the lanes, the bar for release goes up ｜ 车道减半，放行门槛提高
    release_threshold = 0.25 if lanes >= 8 else 0.50
    has_reefer = s["reefer"] is not None
    hold = s["customs"]["hold"]

    if conflict_score >= 0.5:
        return "inspect", "data conflict"                       # sources contradict → a human looks ｜ 数据打架，人看
    if hold and customs_trust >= 0.5:
        return "slow", f"customs {s['customs']['hold_type']} hold, ~{s['customs']['est_days_to_clear']}d"
    if hold and customs_trust < 0.5:
        return "inspect", "customs offline, hold unverified"    # can't trust the hold flag ｜ 海关宕机，hold 不可信
    if has_reefer and c["zone"] == "B" and not power_b:
        return "reroute", "zone B unpowered"                    # every reefer in B will warm ｜ B 区冷藏柜迟早升温
    if not scenario.get("customs_online", True):
        return "slow", "customs offline, clearance unverified"
    if has_reefer and temp_drift > 0.3:
        return "release", "reefer warming"                      # get it out before it spoils ｜ 坏之前赶紧走
    if urgency >= release_threshold:
        return "release", "high urgency"
    return "slow", "below threshold"


# ---------- 5. Reason ｜ 理由 ----------

def build_reason(c, action, why, conflict_notes, temp_drift, reefer_silent, carrier_trust, scenario=None):
    """One plain-English line a planner can read. Template for now; LLM polish later.
    一句接线员能看懂的英文。先用模板，之后可让 LLM 润色。"""
    s = c["sources"]
    r = s["reefer"]
    scenario = scenario or DEFAULT_SCENARIO
    parts = []

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
        parts.append(f"{-c['free_days_left']}d overdue at ${c['demurrage_usd_per_day']}/day")

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

    carrier_t, scale_t, customs_t, reefer_t = compute_trust(c, scenario)
    conflict_score, conflict_notes = compute_conflicts(c, carrier_t, scale_t)
    urgency, temp_drift, reefer_silent = compute_urgency(c, reefer_t if reefer_t is not None else 0.0, scenario)
    action, why = decide_action(c, scenario, conflict_score, urgency, temp_drift, customs_t)
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
    return c


def score_all(containers, scenario=None):
    """Score every container and sort by priority, highest first.
    全部打分，按 priority 从高到低排。"""
    scored = [score(c, scenario) for c in containers]
    scored.sort(key=lambda x: x["priority"], reverse=True)
    return scored


# ---------- Self-test ｜ 自测 ----------

if __name__ == "__main__":
    import json
    from collections import Counter
    from pathlib import Path

    data_path = Path(__file__).resolve().parents[1] / "data" / "containers.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
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
