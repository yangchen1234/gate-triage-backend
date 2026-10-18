> **Current integration:** the active yard UI now uses the persistent non-agent API.
> The browser-only lifecycle described in earlier design sections is retained as
> historical context/reference tests. See [yard-backend.md](yard-backend.md) for the
> current server/database contract and deployment limits.

# Yard action desk — UI prototype

This isolated React preview uses reproducible, locally generated data. It borrows the block-oriented yard and searchable inventory patterns in RBS TOPS public product material, focusing on exception decisions rather than equipment execution.

Run the existing web dev script and open `/?preview=yard`. The default `/` operations console is unchanged. No backend, Claude, Terminal49, equipment, dispatch or external messaging calls are made. Synthetic reviews and workflow state are saved in this browser, survive reload, and reset on fixture regeneration. The branch incorporates main through `2e398b8`; it does not activate the new Terminal49 adapter or merge the independent PostgreSQL workbench.

## Research boundary and revised yard model

Official sources checked on October 17, 2026:

- [APM Terminals Pier 400 driver procedures](https://www2.apmterminals.com/en/los-angeles/practical-information/driver-information) identify a specific reefer receiving area, Row 842, and separate import, export, empty and reefer/genset steps. This supports separating facility capabilities and workflows; it does not provide our fixture's electrical topology.
- [Port of Los Angeles 2025 container-terminal map](https://kentico.portoflosangeles.org/getmedia/b1277c2b-c88c-4c1e-aedb-113706d28543/2025-pola-container-terminals-map) lists finite terminal-level reefer plug counts, e.g. Fenix 706 and APMT 2,400. These dated published totals are context, not real-time availability or per-block placement.
- [RBS TOPS](https://www.rbs-emea.com/products/tops-expert-cloud), [Tideworks Terminal View](https://tideworks.com/terminal-view/) and [Kaleris container-terminal systems](https://kaleris.com/solutions/terminal-operating-system/container-terminals/) are commercial UI/product references. No superiority claim is made.

There is no basis for assuming all yard positions have refrigeration connections. In the preview, zone purpose, slot count, connection capability, assignment and energized state are distinct:

| Block | Modeled purpose | Maximum tiers | Modeled plugs | Circuit |
|---|---|---:|---:|---|
| A01–A02 | Import storage | 4 | 0 | None |
| A03–A04 | Export staging | 4 | 0 | None |
| B01–B02 | Reefer storage, with unpowered buffer rows | 3 | 108 each | R1 |
| B03 | Empty equipment | 5 | 0 | None |
| B04 | DG-designated storage | 2 | 0 | None |
| C01 | Reefer reserve / buffer | 2 | 72 | R2 |
| C02 | Inspection staging | 1 | 0 | None |
| C03 | Import pickup staging | 2 | 0 | None |
| C04 | Empty pickup staging | 2 | 0 | None |

All twelve blocks have 18 bays and four ground rows in the schematic. Only rows 1–2 in B01/B02/C01 have connections, including modeled tier positions. Loaded reefer fixtures only occupy these equipped positions; other positions have no reefer connection. Non-reefer fixtures in equipped blocks are in their unpowered rows. Every occupied reefer has a unique plug assignment. Tier limits and layout are illustrative, not validated stacking instructions. A DG label does not establish segregation/compatibility compliance; that requires real cargo and terminal rules outside this preview.

Geometry, zone names, circuits and capacities are invented. They are not a surveyed Los Angeles terminal, a replica of Fenix/Pier 400, or all-port scale. The regenerated default fixture is now 1,780 containers / 2,592 slots, with 288 plugs in three blocks; older screenshots with 2,392 containers used the superseded homogeneous model. Slot counts are abstract container positions, not TEU or terminal throughput.

The R1 scenario interrupts only assigned R1 reefer connections (B01/B02). C01/R2 remains energized; dry/empty cargo in the same zone is not assigned a cold-chain power-loss flag. This scenario does not imply cranes, gates or the whole terminal have lost power. Congestion affects the modeled outbound access of C03/C04 only. Other flows are not automatically closed.

Resource cards reconcile assigned, unoccupied energized and offline connections. Under R1 outage the default fixture has 134 connected units affected and zero free energized R1 connections. C01 has 43 unoccupied energized connections, insufficient for all affected units. Free does not mean reserved, compatible, reachable or approved. A transfer suggestion requires verification of actual live capacity, cargo compatibility, safe access, handling permission and independent holds. No automatic allocation or physical move is performed.

## Action matrix

The Actions workspace has four stable cells: Do first (important/urgent), Plan & unblock (important/less urgent), Coordinate promptly (lower importance/urgent), Monitor (lower importance/less urgent). The fixed placement makes comparisons possible across scenarios. Rows in the action queue represent individual pending actions, not only a container's primary exception. A container can therefore have urgent power-care and planned customs-follow-up rows simultaneously. Yard inventory remains one row per container.

Importance measures the consequence of the follow-up (cargo care, prerequisite/compliance, affected flow). Urgency measures response pressure from an active scenario or synthetic handling/telemetry window. Scores are independent; no single random priority number determines the quadrant. `actionFor` is a deterministic, inspectable frontend demo policy. It is not an optimization solver, a trained agent, or an industry-approved safety classifier.

| Action | Importance | Urgency | Context |
|---|---:|---:|---|
| Power recovery / safe transfer assessment | 98 | 98 | Assigned connection on interrupted R1 |
| Temperature verification | 95 | 95 | Fixture excursion; no inference of damage |
| Weight / identity verification | 85 | 85 or 40 | Higher urgency if synthetic next handling window ≤60 minutes and no scenario pickup/care blocker |
| Customs-status follow-up | 80 | 80 or 30 | Same synthetic handling-window rule; clearance remains mandatory in every quadrant |
| Telemetry / unit verification | 80 for higher-sensitivity fixture cargo, otherwise 45 | 75 if report age ≥90 min, otherwise 35 | Under confirmed scenario connection interruption, becomes importance 90 / urgency 95 |
| Outbound coordination | 88 | 90 | Container in C03/C04 in an access-disruption scenario |

High importance is ≥70; high urgency is ≥60. All numeric thresholds, cargo sensitivity, and handling windows are mock policy parameters, not actual cargo tolerances, regulatory deadlines, SLAs or empirical estimates. Handling windows do not count down in wall time. An interrupted pickup reduces immediate urgency of prerequisite follow-up in this demonstration, not the obligation to clear it; it must never override a real statutory/safety deadline. Legal, safety and authority gates are independent of this matrix. “Coordinate promptly” routes a suggestion to a responsible role; it sends no message or task.

The matrix recalculates from unchanged inventory and current scenario. Per-action reasons, independent I/U meters and a routine-to-current comparison appear in the inspector. Clicking a quadrant filters the pending queue; clicking a card or row selects that exact action, including non-primary flags. Search/block filters apply to matrix and queue, and all independent issue labels are searchable. Search does not filter through the selected quadrant a second time, avoiding disappearing quadrant totals. CSV uses the same action rows/quadrant when exported from Actions.

Accepting an action removes its container/issue from the pending matrix and creates a Post-action task; dismissal removes only its scenario/container/issue suggestion. Acceptance does not clear an exception or complete handling. Other actions on the same container remain. Review history records the original scenario; the workflow tracks accepted work across scenario switches. A production system would additionally need authoritative incident IDs, server revisions and multi-user reassessment.

## Reproducible simulation checks

Seed `27149`, before operator reviews or filters:

| Scenario | Containers | Flagged containers | Pending actions | Do first | Plan | Coordinate | Monitor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Routine | 1,780 | 59 | 59 | 14 | 30 | 9 | 6 |
| R1 outage | 1,780 | 170 | 193 | 162 | 29 | 1 | 1 |
| Outbound congestion | 1,780 | 253 | 256 | 211 | 30 | 9 | 6 |
| Combined | 1,780 | 364 | 390 | 359 | 29 | 1 | 1 |

Different action/container counts reflect simultaneous independent exceptions. These counts validate fixture behavior, not throughput gains or real-port performance.

Examples:

1. `SIMU2000847`, B01: telemetry age 87 min, standard demo cargo. Routine I45/U35 → Monitor; R1 outage I90/U95 → Do first. The circuit outage adds a separate power-care task. Returning to routine restores the original classification without redrawing the inventory.
2. `SIMU2000895`, B01: in the combined scenario, power-care is Do first and customs follow-up is Plan. Accepting power-care leaves the customs action pending, its hold recorded and supply interrupted.
3. C01/R2 telemetry tasks stay in their original lower quadrants during R1 outage. Zone label alone does not cause a power-loss action.

## Verification and limitations

- 21 frontend tests cover existing session/security behavior plus fixture uniqueness, repeatability, tier/plug capacity reconciliation across seeds, scoped circuit disruption, independent holds, quadrant boundaries, scenario-driven action changes, action identity, all four quadrants and filter composition.
- TypeScript/Vite build passes. Actual browser checks cover scenario counts, exact action selection, quadrant filtering, separate action rows for one container, independent review/holds and power-infrastructure cards/layer.
- Map zoom, stack selection, exception/cargo/power layers, block filtering, search, pagination, evidence, local reviews/history and CSV remain local prototype functions. There are no real operational data feeds or notifications.
- The previous drag/click interference was fixed by allowing panning only in space outside the block groups. Real GIS geometry, power telemetry, yard slot allocation, hazard segregation validation, physical task execution and multi-user synchronization remain outside this draft. Synthetic workflow state is now saved in browser storage as described below.

## Block detail pages and current-inventory query

Click the empty block background to open that block's dedicated view. Clicking an occupied stack opens a compact tier chooser in the current view; selecting a tier then updates the exact container without opening a block page. Keyboard activation of the background provides the equivalent explicit navigation. It renders only that block, enlarged stack geometry, block-scoped metrics, infrastructure and tier selection on the left, with the normal container inspector on the right. The inventory table is hidden within block detail. The upper Back arrow or Escape restores the previous workspace view, filters, selected container, pagination, map zoom and document scroll. An exact query result selects its container ID and tier in place instead of substituting a stack representative or opening a block page. Switching scenarios while focused keeps the same block. The independent Expand control on the Yard overview section opens a map-only workspace, with all 12 blocks and no unrelated table/inspector; clicking a block there enters its detail.

The selected stack lists individual tiers so the operator can select containers hidden underneath the displayed representative. The “View selected container details” control scrolls to the enlarged inspector. Container information now follows a linear reading order in all layouts: basic identity/location/zone, problem, suggested action, importance/urgency quadrant explanation, evidence, operator review. Priority cards no longer precede the problem or recommendation.

The collapsible left Query rail searches all current inventory, independently of exception, block or quadrant filters. It supports partial container numbers (case-insensitive, optional spaces/hyphens), carrier codes and carrier names; filling both fields applies AND logic. “Show matching inventory” applies those query fields to the full inventory view with exceptions-only disabled. Results are paginated and show carrier, location and current flag. A result selects the exact container and updates its inspector without changing the page. If its block differs from the currently expanded block, a notice names both blocks; no unrelated stack is mislabeled as its location. On narrow layouts the query is a dismissible drawer; it starts closed and closes after locating a result. No owner or customer relation is inferred: `carrier` is the company field in this demonstration, and cargo ownership is explicitly not modeled.

`yardStatus` distinguishes `in-yard` from `departed`; initial fixtures are all in-yard by construction; the post-action projection now excludes confirmed departures. `queryYardInventory` explicitly excludes departed records, verified with a departed test fixture. Query metadata introduces no new random draws, so the seed and previous scenario counts remain unchanged. The default Maersk/MAEU query returns 343 current containers, including normal records. CSV exports now include carrier code/name and yard status as well as the current view's actions.

Verification: 23 frontend tests pass, including carrier-name/code equivalence, number normalization, composed filters, invalid/empty results, normal-container inclusion and departed-record exclusion. Browser checks cover company lookup (343 results), exact-number positioning (`SIMU2000096`, A01 bay 08 / row 3 / tier 2), block-only scope, background click, specific tier selection, scenario changes inside a block, empty-query recovery, query pagination, map-only expansion, Escape/Back, and return restoration (page 2 of a 343-record query with 125% zoom). Inspector DOM order was checked for the requested basic → problem → action → quadrant sequence. Local preview remains on port 5176; no source or fixture is published by this change.

Container-click refinement: navigation is attached to the SVG background rectangle rather than the whole block group. Stack click/Enter/Space handlers select in place and stop propagation. Decorative labels/empty-position placeholders let background clicks pass through. Power-resource cards also select in place. In the map-only expanded workspace a container selection reveals stack/inspector details while retaining all 12 blocks. Actual browser checks verified: overview stack → 12 blocks/no Back button; empty B02 background → one B02 block/Back button; B02 stack → still B02; cross-block query result → same B02 page with an explicit location notice; normal query result → overview retained; expanded map stack → same 12-block expanded view with inspector revealed. No inventory, scoring or model API behavior changed.


## Post-action workflow and vertical stack update

The isolated preview now implements a synthetic lifecycle: accept an action → Queued → In progress → Verify result → Resolved. Each accepted `(containerId, issue)` has one task, independent of scenario switches. Work completion requires a summary; resolving requires an explicit result confirmation and evidence reference. Invalid, repeated or stale transitions fail without changing stock. Dismissal remains a review decision and changes no cargo condition.

A verified result clears only its specific exception. Weight verification reconciles the demo declaration to its measured value; temperature verification records the simulated setpoint; telemetry verification records a fresh report. Power verification models a confirmed backup for that unit, leaving R1 offline and other units affected. Verified alternate access is also per-container and does not reopen a whole region. Independent customs holds remain active until their own verification.

A normal container stays at its modeled position and is searchable in current inventory. Gate-out is blocked by any remaining active exception or open accepted task, including a task from another scenario. Gate-out additionally requires release-condition confirmation, physical-exit confirmation and a reference. Only then does the active yard projection remove that ID, decrease inventory and occupied plug count where applicable, and increase free modeled tier slots by exactly one. Audit records and last location remain in the Gated out tab; repeated gate-out cannot free another slot. Switching scenarios or reloading does not resurrect departures.

Selected stack cards render in one vertical column at all widths, highest tier first, with ground level labeled below. Every modeled tier up to the block's tier limit has an equally sized card; vacant tiers show a dashed, striped Empty slot card. Occupied tiers remain selectable without page navigation. Positions are retained, not automatically repacked after an exit. These are modeled addresses, not validated physical stacking, rehandling instructions or lift approval; equipment moves are outside this preview.

Versioned synthetic state (seed, decisions, jobs, resolutions, departures) is saved in this browser's localStorage. Loading validates the fixture IDs, locations, uniqueness and resolution/departure consistency. Storage failure displays a visible warning; it does not pretend to be durable. Regenerate demo data explicitly creates a new cohort and clears its workflow. This is browser-local persistence, not a database-backed or multi-user operational system, and has no Terminal49, model or equipment side effects.

UI copy cleanup removes the requested explanatory paragraphs beneath the query controls and the overview map hint. The existing synthetic badge and About dialog retain the demo context.

Validation: 32 frontend tests and the production TypeScript/Vite build pass. The nine new workflow tests cover acceptance without clearance, ordered transitions and evidence, stale/repeated updates, independent holds, per-unit backup/access, gate-out confirmation, fixed capacity and exact inventory/plug reconciliation, single-tier ground-cell vacancy, scenario persistence, and corrupted-cache rejection. Browser testing completed temperature task SIMU2000827 through all four stages: resolved inventory remained 1,780 / 2,592 with 812 free slots; confirmed gate-out changed it to 1,779 / 2,592 with 813 free slots, removed its query match, and reduced B01 occupied plugs from 62 to 61. Reload preserved the result. Its former tier displayed Empty slot, with all three tier cards measured at the same size in a single column; the subsequent compact layout reduces each card to 440 × 76 CSS pixels on desktop. Browser console reported no errors or warnings.


## Port profiles and Dutch Rotterdam demonstration

The header port selector switches between Los Angeles · EN and Rotterdam · NL. New page loads always start on LA. Switching ports remounts the isolated workspace, clearing obsolete focus, filters, selection, scenario and open dialogs, while restoring that port's saved synthetic workflow. Language follows the port; dates use America/Los_Angeles or Europe/Amsterdam, numbers use en-US or nl-NL, and the document language is en or nl. Existing route / and server/model integrations are unchanged.

| Profile | Seed | Blocks | Arrangement | Initial containers | Modeled tier slots | Initial free slots |
|---|---:|---:|---|---:|---:|---:|
| Los Angeles | 27149 | 12 | 4 columns × 3 rows | 1,780 | 2,592 | 812 |
| Rotterdam | 44329 | 8 | 4 columns × 2 rows | 1,142 | 1,800 | 658 |

These are initial generated values, not observed port totals; saved gate-outs change occupancy. Rotterdam uses A01 import, A03 export, B01/B02 reefer, B03 empty, C01 reefer buffer and C03/C04 pickup zones. Every block keeps finite tier limits and modeled reefer connections; R1 and access restrictions use the same explicit boundaries. The ID prefix RTDM distinguishes Rotterdam's generated records from LA's SIMU IDs. Neither prefix/sequence is a verified operational container registry. Layout height derives from actual block rows, so the Rotterdam map contains no unused third row.

LA retains its original browser-storage key and accepts legacy records lacking a port tag as LA. Rotterdam has a separate key. Cache validation generates the fixture for the saved port, rejecting unknown ports and IDs or departures from the other cohort. Per-port switch/save/restore has regression coverage. User notes and evidence are retained verbatim; UI copy, issue/action metadata, quadrants, confirmation dialogs and CSV labels are translated at the presentation boundary. Dutch is maintained in yard-language.ts; no external translation API is used.

Reference context: [Port of Rotterdam — terminals](https://www.portofrotterdam.com/nl/logistiek/op-en-overslag/terminals) describes container handling, empty depots and reefer services; [container depots](https://www.portofrotterdam.com/nl/logistiek/op-en-overslag/container-depots) describes storage, inspection and repositioning. These pages informed terminology and broad functions only. The eight zones, capacity, incidents and container records are invented for the demo and do not represent any named Rotterdam operator or actual terminal plan.

## Stack-first inspection and two-column block workspace

An occupied map cell now opens a compact, accessible chooser before selecting an exact container. Thumbnail cards render each modeled tier from highest to ground, including disabled vacant positions of the same size. Choosing a container updates its exact ID and tier in the right inspector; opening or canceling the chooser leaves the previous selection and page unchanged. The same tier component is reused for the left-side selected-stack panel, so popup and workspace cannot disagree about order or vacancies. There is no automatic navigation from a container hit target. Only activating the block's empty background enters block detail.

Block detail collapses the query rail to provide space, displays map / infrastructure / selected stack on the left and the familiar independently scrolling inspector on the right, and hides the inventory table. Back restores the previous query visibility along with prior filters and selection. Responsive layouts retain the normal narrow-screen inspector placement.

Validation: 38 frontend tests and the production build pass. Added coverage verifies the eight-block two-row Rotterdam geometry, IDs disjoint from LA, repeatability, occupancy/plug limits, independent scenario constraints, per-port gate-out validation and browser cache isolation, legacy LA migration, Dutch whole-message translation/number/time formatting, and top-to-ground tier/vacancy ordering. Browser tests verified Rotterdam's 8 blocks and Dutch UI, a complete Dutch work/verification flow retaining 1,142 containers and 658 free slots, switch back to the unchanged saved LA run, restored Rotterdam task progress, and LA default on reload. Both ports' block pages showed one block, zero inventory tables and a right-hand inspector. LA grid click retained the prior selected ID until a precise tier was chosen, and returned to the same 12-block view. Browser console reported no errors or warnings. No GitHub push or deployment is performed for this local preview.
