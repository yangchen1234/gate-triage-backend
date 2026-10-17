# Tariff assumptions ｜ 费率假设

Every money figure in Gate Triage is an **estimate built from one example public tariff per port**.
It is not a quote, not a contract rate, and not a port-wide price. This page says exactly what each
number is, where it comes from, and what it leaves out.

本项目所有金额都是**按每个港口一份公开示例费率估算**的，不是报价、不是合同价、也不是全港通用价。
本页说明每个数字是什么、从哪来、没算什么。

The API carries the same statement: `tariff_basis` and `data_note` are returned on `/plan`
(`next_actions`) and inside every container's `decision_trace`. Front-ends should show them as a footnote
wherever a currency amount appears.

---

## What the numbers are ｜ 数字是什么

| | LAX | SHA | RTM |
|---|---|---|---|
| **Role in the demo** | Primary dataset | Parameter demo | Parameter demo |
| **Dataset** | Synthetic, LA-shaped (100 boxes) | *Same* synthetic dataset, re-priced | *Same* synthetic dataset, re-priced |
| **Terminal storage (port) rate** | Port of Los Angeles Tariff No. 4, Sec. 10, 40' | **0 — bundled into carrier rate** (see below) | **0 — bundled into carrier rate** (see below) |
| **Carrier rate (example carrier)** | Maersk, US import, 2026 | Emirates Line, China import, 2026 ("other ports" incl. Shanghai) | Maersk, Netherlands import, 2026 |
| **Container type** | 40' dry / 40' reefer | 40' dry / 40' reefer | 40' dry / 40' reefer |
| **Direction** | Import | Import | Import |
| **Date of tariff** | 2026 published rates | 2026 published rates | 2026 published rates |
| **Free time** | Dry 4 d / Reefer 2 d | 7 d all types | 4 d all types, calendar days |
| **Includes terminal storage?** | No — port tariff added separately | Yes — carrier rate bundles storage | Yes — "compensation includes terminal storage costs" |
| **Currency** | USD | CNY | EUR |
| **Tiers (per day, dry)** | Port: 52.77 / 105.47 / 210.93 · Carrier: 300 / 345 / 395 | Carrier: 200 / 400 / 800 | Carrier: 110 / 210 / 250 |
| **Tiers (per day, reefer)** | Port: same · Carrier: 490–640 (deterministic pick) | Carrier: 450 / 720 / 1200 | Carrier: 230 / 320 / 385 |
| **Hazmat** | ×1.25–1.5 surcharge (assumption) | same assumption | same assumption |

### Why SHA and RTM show port storage = 0 ｜ 为什么上海、鹿特丹的港口仓储费显示 0

The example carrier tariffs we could verify for China and the Netherlands state that their daily charge
**includes** terminal storage. So the whole daily cost sits in `carrier_demurrage_per_day` and
`port_demurrage_per_day` is 0 **because the source bundles it, not because the port charges nothing.**
A terminal's own storage tariff, if billed separately under a different carrier, is not modelled.

上海、鹿特丹用的示例船公司费率写明"含码头仓储"，所以费用全部在 `carrier_demurrage_per_day`，
`port_demurrage_per_day` 为 0 **是因为来源把它打包了，不是港口不收费**。换一家船公司、码头单独计费的情况没有建模。

---

## What is NOT modelled ｜ 没建模的

- **Contract / negotiated rates.** Large shippers rarely pay the public tariff.
- **Demurrage vs. detention split.** We show one daily figure while the box is in the terminal; detention after pickup is out of scope.
- **Other carriers.** One example carrier per port. A box with a different carrier code is still priced at the example rate.
- **Reefer plug-in / monitoring fees, exam fees, chassis, drayage waiting time.**
- **Weekends, holidays, free-time clock rules** (working vs. calendar days, when the clock starts).
- **FX.** Fixed rates in `FX_TO_USD`, for cross-port stats only.
- **Zones.** "Zone A / Zone B" are simulated yard zones so a power-loss scenario can be shown. They are not a map of any terminal at LA, Yangshan or Rotterdam.
- **Local data.** SHA and RTM re-price the LA-shaped dataset. No Shanghai or Rotterdam container data, hold types, or operating procedures are used; customs agency names and outreach language are localized, the operations are not.

---

## How to read a figure ｜ 怎么读一个数字

`demurrage_per_day` on a box = `port_demurrage_per_day` + `carrier_demurrage_per_day`, both from the
tier matching `days_overdue` (free time exhausted). A box with `free_days_left > 0` carries a *rate* but is not
paying yet; `next_actions` only counts boxes with `free_days_left <= 0` as having anything to unlock.

`/stats` compares FIFO against priority ordering using the per-day *rates* of every unserved box regardless of
free time; it is a rate-exposure comparison, not realised savings. Under a stricter reading (only boxes past free
time), priority ordering costs *more* demurrage than FIFO, by design: in crisis mode the engine trades money for
cargo safety (`WEIGHTS_CRISIS.cost = 0.05`). The honest headline is cargo risk — at 4 lanes, FIFO gets 2 of 9
at-risk reefers out today; Gate Triage gets 9 — not dollars saved.

---

## Planned (post-hackathon) ｜ 赛后计划

- Carrier-aware pricing: look up the box's carrier code; if no matching tariff, return `rate: null, basis: "missing applicable tariff"` instead of the example rate.
- Separate terminal storage and carrier detention, with each side's free-time clock.
- Replace the synthetic feed with Terminal49 (`gate_triage/terminal49_adapter.py`) for holds, fees and last free day.

Sources are cited inline in `gate_triage/port_profiles.py` and `scripts/generate.py`.
