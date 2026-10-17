"""
port_profiles.py — per-port parameters ｜ 港口配置

Twist 2 (global): the engine is port-agnostic; everything that differs between ports lives here —
currency, free time, demurrage tiers, customs agency, who to call, and the language drafts are written in.
Twist 2：引擎不分港口；港口之间不同的东西都在这里 —— 货币、免费期、滞港费阶梯、海关机构、联系对象、草稿语言。

Sources ｜ 来源 (2025–2026):
  LAX  Port of LA Tariff No. 4 (port storage) + Maersk US import D&D 2026 (carrier)
  SHA  Emirates Line China Import D&D, eff. 15 May 2025 — Shanghai in "other ports" group, RMB, 7 free days
       https://www.emiratesline.com/wp-content/uploads/2025/05/China-Import-DD-Effective-15th-May-2025.pdf
  RTM  Maersk Netherlands import D&D, eff. 01 Aug 2026 — EUR, 4 free days, includes terminal storage
       https://www.maersk.com/local-information/the-netherlands/import
"""
from __future__ import annotations

import hashlib
from datetime import datetime

# FX to USD for cross-port comparison ｜ 换算成美元用于横向比较（近似值，可配置）
FX_TO_USD = {"USD": 1.0, "CNY": 1 / 7.1, "EUR": 1.09}

PROFILES = {
    "LAX": {
        "code": "LAX", "name": "Port of Los Angeles", "country": "US",
        "currency": "USD", "symbol": "$", "language": "en",
        "free_days": {"dry": 4, "reefer": 2},
        # (max_days_overdue, rate) tiers; last tier is open-ended ｜ 阶梯
        "port_tiers": [(5, 52.77), (10, 105.47), (None, 210.93)],           # Port of LA Tariff No. 4, 40ft
        "carrier_tiers": {"dry": [(4, 300), (9, 345), (None, 395)],          # Maersk US import 2026
                          "reefer": [(None, (490, 640))]},                   # range → deterministic pick
        "hazmat_surcharge": (1.25, 1.5),
        "customs_agency": "CBP",
        "customs_agency_full": "U.S. Customs and Border Protection",
        "who": {"customs": "CBP", "carrier": "Carrier", "reefer_tech": "Reefer tech", "yard": "Yard ops"},
        "hold_labels": {"manifest": "manifest hold", "document_review": "document review", "intensive": "intensive exam"},
        "zone_powered": "Zone A",
        "tariff_basis": "Example tariffs, 40' import, 2026: terminal storage from Port of Los Angeles Tariff No. 4 (Section 10); carrier demurrage/detention from Maersk US import tariff. One example carrier, not a port-wide price; no contract rates, reefer plug-in or weekend/holiday rules.",
        "data_note": "Synthetic LA-shaped dataset. Zones A/B are simulated yard zones, not a terminal map.",
    },
    "SHA": {
        "code": "SHA", "name": "Port of Shanghai (Yangshan)", "country": "CN",
        "currency": "CNY", "symbol": "¥", "language": "zh",
        "free_days": {"dry": 7, "reefer": 7},                               # Emirates Line China import: 7 days all types
        "port_tiers": [(None, 0.0)],                                         # carrier tariff bundles storage in this source
        "carrier_tiers": {"dry": [(7, 200), (14, 400), (None, 800)],         # RMB/day, 40' dry, "other ports" incl. Shanghai
                          "reefer": [(7, 450), (14, 720), (None, 1200)]},    # RMB/day, 40' reefer
        "hazmat_surcharge": (1.25, 1.5),
        "customs_agency": "海关",
        "customs_agency_full": "中华人民共和国海关总署 (GACC)",
        "who": {"customs": "海关", "carrier": "船公司", "reefer_tech": "冷藏技工", "yard": "堆场调度"},
        "hold_labels": {"manifest": "舱单核查", "document_review": "单证审核", "intensive": "开箱查验"},
        "zone_powered": "A 区",
        "tariff_basis": "Example tariff, 40' import, 2026: Emirates Line China import demurrage ('other ports' incl. Shanghai), storage bundled into the carrier rate — port storage shows 0 because this source bundles it, not because the port charges nothing. One example carrier, not a port-wide price.",
        "data_note": "Parameter demo: the same synthetic LA-shaped dataset re-priced under this tariff; not Shanghai data. Zones A/B are simulated yard zones, not a Yangshan terminal map.",
    },
    "RTM": {
        "code": "RTM", "name": "Port of Rotterdam", "country": "NL",
        "currency": "EUR", "symbol": "€", "language": "en",
        "free_days": {"dry": 4, "reefer": 4},                               # Maersk NL import, calendar days
        "port_tiers": [(None, 0.0)],                                         # "compensation includes terminal storage costs"
        "carrier_tiers": {"dry": [(4, 110), (9, 210), (None, 250)],          # EUR/day, days 5-8 / 9-13 / 14+
                          "reefer": [(4, 230), (9, 320), (None, 385)]},
        "hazmat_surcharge": (1.25, 1.5),
        "customs_agency": "Dutch Customs",
        "customs_agency_full": "Douane (Netherlands Customs)",
        "who": {"customs": "Dutch Customs", "carrier": "Carrier", "reefer_tech": "Reefer tech", "yard": "Yard ops"},
        "hold_labels": {"manifest": "manifest hold", "document_review": "document review", "intensive": "physical inspection"},
        "zone_powered": "Zone A",
        "tariff_basis": "Example tariff, 40' import, 2026: Maersk Netherlands import demurrage/detention, calendar days, 'compensation includes terminal storage costs', i.e. storage is bundled into the carrier rate, so port storage shows 0. One example carrier, not a port-wide price.",
        "data_note": "Parameter demo: the same synthetic LA-shaped dataset re-priced under this tariff; not Rotterdam data. Zones A/B are simulated yard zones, not a terminal map.",
    },
}

DEFAULT_PORT = "LAX"


def get_profile(code: str | None) -> dict:
    return PROFILES.get((code or DEFAULT_PORT).upper(), PROFILES[DEFAULT_PORT])


def _pick(key: str, lo: float, hi: float, salt: str = "") -> float:
    """Deterministic pick in [lo, hi] from a container id, so stored == recomputed.
    用柜号做确定性选择，保证存的数和重算的数一致。"""
    h = int(hashlib.md5(f"{key}:{salt}".encode()).hexdigest(), 16) % 1000 / 1000.0
    return lo + (hi - lo) * h


def _tier(tiers, days_overdue):
    """Return (rate, tier_index) for the tier that applies at days_overdue (0 → first tier)."""
    for i, (limit, rate) in enumerate(tiers, start=1):
        if limit is None or days_overdue <= limit:
            return rate, i
    return tiers[-1][1], len(tiers)


def free_days_for(profile: dict, cargo: str) -> int:
    return profile["free_days"]["reefer" if cargo.startswith("reefer") else "dry"]


def compute_fees(profile: dict, cargo: str, arrived_at: str, now: datetime, key: str) -> dict:
    """Everything money-related for one box at one port. ｜ 一个柜子在一个港口的全部费用字段。"""
    arrived = datetime.fromisoformat(arrived_at.replace("Z", ""))
    dwell_days = int((now - arrived).total_seconds() // 86400)
    free_days_left = free_days_for(profile, cargo) - dwell_days
    days_overdue = max(0, -free_days_left)

    port_rate, tier = _tier(profile["port_tiers"], days_overdue)

    kind = "reefer" if cargo.startswith("reefer") else "dry"
    carrier_rate, _ = _tier(profile["carrier_tiers"][kind], days_overdue)
    if isinstance(carrier_rate, tuple):
        carrier_rate = round(_pick(key, *carrier_rate, salt="carrier"))
    if cargo == "hazmat":
        carrier_rate = round(carrier_rate * _pick(key, *profile["hazmat_surcharge"], salt="hazmat"), 0)

    total = round(port_rate + carrier_rate)
    fx = FX_TO_USD[profile["currency"]]
    return {
        "port": profile["code"],
        "currency": profile["currency"],
        "free_days_left": free_days_left,
        "port_demurrage_per_day": round(port_rate, 2),
        "carrier_demurrage_per_day": round(carrier_rate),
        "demurrage_per_day": total,                          # local currency ｜ 本币
        "demurrage_usd_per_day": round(total * fx),          # for cross-port stats ｜ 换算美元，统计用
        "demurrage_tier": tier,
    }
