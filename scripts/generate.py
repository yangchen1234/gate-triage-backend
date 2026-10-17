"""
generate.py — generate 100 containers of raw data -> containers.json ｜ 生成 100 个集装箱的原始数据
Usage ｜ 用法: python generate.py
Output ｜ 输出: containers.json (no priority/action/reason — score.py adds those ｜ 不含打分字段，由 score.py 算)

Sources ｜ 数字来源 (2026):
- 港口滞港费 (Port of LA Tariff No. 4, 40ft): 免费期 4 天; 超期 1-5 天 $52.77/天, 6-10 天 $105.47, 11+ $210.93
  https://portoflosangeles.org/business/tariff
- 船公司滞港费 (Maersk 2026 US import): 干柜免费 4 天, 超期 1-4 天 $300, 5-9 天 $345, 10+ $395
  冷藏柜免费期仅 2 天, 之后 $490-640/天
- 两笔费用叠加; 危险品 +25-50% (行业惯例)
- 40ft 柜重: Conexwest — 皮重 ~3,880 kg, 最大总重 ~30,480 kg
- 海关 hold 类型 (CBP): manifest hold ~1-3 工作日, document review 无固定时长, intensive exam ~5-7 天
  https://www.help.cbp.gov/s/article/Article-1267 / Article-1268
- 冷链温度: CDC 疫苗 2-8°C; FDA 胰岛素 2-8°C
- 真实事故: 2024 年 LA 港停电 9 次; 2024-07-19 CrowdStrike 港口切人工; 2025-01-27 Everport 停电; 2025-07-02 APM 系统宕机
"""
import json
import random
from datetime import datetime, timedelta

from port_profiles import PROFILES, compute_fees, free_days_for as _free_days_for

random.seed(42)  # fixed seed so every run is identical ｜ 固定种子，demo 稳定

N = 100
NOW = datetime(2026, 10, 17, 8, 0, 0)

# 5 家船公司，各自的历史矛盾率（最近 10 次申报里和地磅对不上的次数）
# Real carriers get low mismatch rates; the two unreliable ones are fictional so no real company is implied
# 真实船司只给低矛盾率；不靠谱的两家用虚构代码，避免影射真实公司
CARRIERS = {
    "MSCU": 1,   # MSC
    "MAEU": 2,   # Maersk
    "ONEU": 1,   # ONE
    "OOLU": 2,   # OOCL
    "PCLU": 4,   # fictional: Pacific Coastal Lines ｜ 虚构小型区域船司
    "TRXU": 6,   # fictional: TransRim Express ｜ 虚构，最不靠谱
}

CARGO_TYPES = ["reefer_pharma", "reefer_food", "hazmat", "general", "empty"]
CARGO_WEIGHTS = [0.08, 0.17, 0.10, 0.50, 0.15]

CONSIGNEE_BY_CARGO = {
    "reefer_pharma": ["hospital", "hospital", "retail"],
    "reefer_food":   ["grocery", "grocery", "retail"],
    "hazmat":        ["retail", "unknown"],
    "general":       ["retail", "retail", "grocery", "unknown"],
    "empty":         ["unknown"],
}

ZONES = ["A", "B", "C"]

# customs hold type -> estimated days to clear ｜ 海关 hold 类型 -> 预计解除天数
HOLD_TYPES = {
    "manifest":        (1, 3),   # CBP manifest review, ~1-3 business days ｜ 舱单复核
    "document_review": (2, 5),   # CBP/PGA asks for documents, no fixed duration ｜ 补文件
    "intensive":       (5, 7),   # devanned at exam site, ~5-7 days ｜ 拉去查验场开箱
}

# 40ft box: tare ~3,880 kg, max gross ~30,480 kg ｜ 40 尺柜皮重 / 最大总重
TARE_KG = 3880
MAX_GROSS_KG = 30480


# ---------- Demurrage via port profile ｜ 滞港费走港口配置 ----------

PORT = PROFILES["LAX"]   # dataset is generated for LA; score() recomputes fees for other ports
                         # 数据按 LA 生成；切换港口时 score() 按配置重算费用


def free_days_for(cargo):
    return _free_days_for(PORT, cargo)


def apply_fees(c):
    """Fill every fee field from the port profile (deterministic by container_id).
    按港口配置填所有费用字段（按柜号确定性计算）。"""
    c.update(compute_fees(PORT, c["cargo_type"], c["arrived_at"], NOW, c["container_id"]))


# ---------- Base container ｜ 基础柜子 ----------

def container_id(prefix):
    return f"{prefix}{random.randint(1000000, 9999999)}"


def base_container():
    cargo = random.choices(CARGO_TYPES, CARGO_WEIGHTS)[0]
    prefix = random.choice(list(CARRIERS.keys()))
    consignee = random.choice(CONSIGNEE_BY_CARGO[cargo])
    is_reefer = cargo.startswith("reefer")

    # true gross weight incl. tare ｜ 真实总重（含皮重）
    if cargo == "empty":
        true_weight = random.randint(TARE_KG - 200, TARE_KG + 300)
    else:
        true_weight = random.randint(12000, MAX_GROSS_KG - 500)

    # arrived 0-11 days ago; dry free 4 days, reefer 2 ｜ 到港 0–11 天前
    dwell_days = random.randint(0, 11)
    arrived = NOW - timedelta(days=dwell_days, hours=random.randint(0, 23))
    free_days_left = free_days_for(cargo) - dwell_days

    carrier = {
        "declared_status": "empty" if cargo == "empty" else "laden",
        "declared_weight_kg": int(true_weight * random.uniform(0.95, 1.05)),
        "history_mismatches_last10": CARRIERS[prefix],
    }
    scale = {"weight_kg": true_weight}
    customs = {"hold": False, "hold_type": "none", "est_days_to_clear": 0}
    if is_reefer:
        setpoint = 2.0 if cargo == "reefer_pharma" else -18.0
        reefer = {
            "temp_c": round(setpoint + random.uniform(-0.5, 0.8), 1),
            "setpoint_c": setpoint,
            "last_ping_min": random.randint(2, 25),
        }
    else:
        reefer = None

    # ~10% have a routine customs hold; not a data conflict ｜ 约 10% 有海关 hold，不算冲突
    if random.random() < 0.10:
        ht = random.choice(["manifest", "manifest", "document_review"])
        customs = {"hold": True, "hold_type": ht, "est_days_to_clear": random.randint(*HOLD_TYPES[ht])}

    c = {
        "container_id": container_id(prefix),
        "carrier_code": prefix,
        "cargo_type": cargo,
        "consignee_type": consignee,
        "zone": random.choice(ZONES),
        "arrived_at": arrived.isoformat(),
        "free_days_left": free_days_left,
        "sources": {
            "carrier": carrier,
            "scale": scale,
            "customs": customs,
            "reefer": reefer,
        },
        "_conflict": "none",  # debug label ｜ 调试用
    }
    apply_fees(c)
    return c


def set_overdue(c, free_days_left):
    """Set overdue days and recompute fees from the port profile.
    统一改超期天数并按港口配置重算费用。"""
    dwell = free_days_for(c["cargo_type"]) - free_days_left
    c["arrived_at"] = (NOW - timedelta(days=dwell, hours=random.randint(0, 23))).isoformat()
    apply_fees(c)


# ---------- 5 injected conflicts ｜ 5 种冲突 ----------

def conflict_empty_but_heavy(c):
    """Carrier says empty, scale reads laden ｜ 船司说空柜，地磅读出重柜"""
    c["cargo_type"] = "general"
    c["consignee_type"] = "unknown"
    c["sources"]["carrier"]["declared_status"] = "empty"
    c["sources"]["carrier"]["declared_weight_kg"] = random.randint(3700, 4200)
    c["sources"]["scale"]["weight_kg"] = random.randint(16000, 26000)
    c["sources"]["reefer"] = None
    set_overdue(c, random.randint(-3, 2))
    c["_conflict"] = "empty_but_heavy"


def conflict_customs_cleared_reefer_warming(c):
    """Customs cleared, but reefer is 4°C+ above setpoint ｜ 海关放行，冷藏升温 4°C 以上"""
    c["cargo_type"] = "reefer_food"   # pharma+hospital warming is reserved for the hero ｜ 药品+医院升温只留给主角
    c["consignee_type"] = "grocery"
    setpoint = -18.0
    c["sources"]["customs"] = {"hold": False, "hold_type": "none", "est_days_to_clear": 0}
    c["sources"]["reefer"] = {
        "temp_c": round(setpoint + random.uniform(4.5, 8.0), 1),
        "setpoint_c": setpoint,
        "last_ping_min": random.randint(3, 20),
    }
    set_overdue(c, random.randint(-2, 2))
    c["_conflict"] = "customs_cleared_reefer_warming"


def conflict_reefer_silent(c):
    """Reefer sensor silent 90+ min ｜ 冷藏 90 分钟以上没上报"""
    c["cargo_type"] = "reefer_food"
    c["consignee_type"] = "grocery"
    c["sources"]["reefer"] = {
        "temp_c": -18.0,
        "setpoint_c": -18.0,
        "last_ping_min": random.randint(95, 240),
    }
    set_overdue(c, random.randint(-1, 3))
    c["_conflict"] = "reefer_silent"


def conflict_weight_mismatch(c):
    """Declared weight off from scale by 30%+ ｜ 船司申报重量和地磅差 30% 以上"""
    c["cargo_type"] = "general"
    c["sources"]["carrier"]["declared_status"] = "laden"
    true_w = random.randint(14000, 28000)
    c["sources"]["scale"]["weight_kg"] = true_w
    c["sources"]["carrier"]["declared_weight_kg"] = int(true_w * random.uniform(0.5, 0.65))
    c["sources"]["reefer"] = None
    set_overdue(c, random.randint(-2, 3))
    c["_conflict"] = "weight_mismatch"


def conflict_hazmat_intensive_overdue(c):
    """Hazmat + intensive exam + overdue (tier 2 demurrage) ｜ 危险品 + 细查 + 已超期"""
    c["cargo_type"] = "hazmat"
    c["consignee_type"] = "retail"
    c["sources"]["customs"] = {"hold": True, "hold_type": "intensive", "est_days_to_clear": random.randint(5, 7)}
    c["sources"]["reefer"] = None
    set_overdue(c, random.randint(-8, -5))
    c["_conflict"] = "hazmat_intensive_overdue"


CONFLICTS = [
    conflict_empty_but_heavy,
    conflict_customs_cleared_reefer_warming,
    conflict_reefer_silent,
    conflict_weight_mismatch,
    conflict_hazmat_intensive_overdue,
]


def hero_container(c):
    """Demo hero: hospital vaccine reefer, Zone B, customs cleared, warming, unreliable carrier.
    Reefer free time is 2 days; arrived 3 days ago -> 1 day overdue.
    Should rank ~20-40 under Normal and jump to #1 under Lanes -50%.
    demo 主角：医院疫苗冷藏柜，Zone B，海关放行，冷藏在升温，船司不靠谱。
    Normal 下应排 20–40 位，Lanes -50% 下应跳到第一。"""
    c["container_id"] = "TRXU7731902"
    c["carrier_code"] = "TRXU"
    c["cargo_type"] = "reefer_pharma"
    c["consignee_type"] = "hospital"
    c["zone"] = "B"
    c["sources"] = {
        "carrier": {"declared_status": "laden", "declared_weight_kg": 15800, "history_mismatches_last10": 6},
        "scale": {"weight_kg": 16100},
        "customs": {"hold": False, "hold_type": "none", "est_days_to_clear": 0},
        "reefer": {"temp_c": 7.9, "setpoint_c": 2.0, "last_ping_min": 8},
    }
    set_overdue(c, 0)
    c["_conflict"] = "pharma_reefer_warming"


def main():
    containers = [base_container() for _ in range(N)]
    hero_container(containers[0])

    slots = random.sample(range(1, N), 15)
    for idx, slot in enumerate(slots):
        CONFLICTS[idx % 5](containers[slot])

    random.shuffle(containers)

    with open("containers.json", "w") as f:
        json.dump(containers, f, indent=2)

    from collections import Counter
    print(f"Generated {len(containers)} containers -> containers.json")
    print("cargo_type:", dict(Counter(c["cargo_type"] for c in containers)))
    print("injected conflicts:", dict(Counter(c["_conflict"] for c in containers)))
    print("demurrage tier:", dict(sorted(Counter(c["demurrage_tier"] for c in containers).items())))
    print("customs holds:", dict(Counter(c["sources"]["customs"]["hold_type"] for c in containers if c["sources"]["customs"]["hold"])))
    print("overdue:", sum(1 for c in containers if c["free_days_left"] < 0))
    dem = [c["demurrage_per_day"] for c in containers]
    print(f"demurrage/day (port+carrier) range: ${min(dem)} – ${max(dem)}")
    print(f"total demurrage/day: ${sum(d for c, d in zip(containers, dem) if c['free_days_left'] < 0):,}")


if __name__ == "__main__":
    main()
