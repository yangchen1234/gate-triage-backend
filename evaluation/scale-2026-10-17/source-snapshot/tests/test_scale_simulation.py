import copy
from collections import Counter
import json

import pytest

from gate_triage.workbench.scale_simulation import (TERMINAL_IDS, get_profile, initial_resource_state,
    iter_movement_batches, profile_catalog, schedule_window)


def movement(identifier,arrival=0,ready=0,service=5,priority=50,blocked=False,terminal=None):
    return {"id":identifier,"number":f"SIM-{identifier}","terminal_id":terminal or TERMINAL_IDS[0],"category":"loaded_import","teu":2,"arrival_min":arrival,"ready_min":ready,"service_min":service,"priority":priority,"blocked":blocked,"payload":{}}


def apply_rows(rows,updates):
    index={r["id"]:r for r in rows}
    for update in updates:
        if update["id"] in index:index[update["id"]].update(update)


def test_seven_day_stream_exact_rounded_teu_and_bounded_batches():
    profile=get_profile("la_seven_day")
    count=teu=0;terminals=Counter();sizes=Counter();days=Counter()
    ids=set()
    for batch in iter_movement_batches("la_seven_day",17,997):
        assert 1<=len(batch)<=997
        for row in batch:
            count+=1;teu+=row["teu"];terminals[row["terminal_id"]]+=1;sizes[row["teu"]]+=1;days[row["payload"]["day_index"]]+=row["teu"]
            assert row["id"] not in ids;ids.add(row["id"])
            assert len(row["number"])<=30
            assert row["ready_min"]>=row["arrival_min"]
    assert count==119014==profile["record_count"]
    assert teu==196371==profile["generated_teu_total"]
    assert set(days.values())=={28053}
    assert set(terminals)==set(TERMINAL_IDS)
    assert len(set(terminals.values()))==1
    assert abs(sizes[2]/count-.65)<.0001


def test_generator_reproducible_and_profile_targets_distinguish_peak():
    a=next(iter_movement_batches("la_average_day",17,20));b=next(iter_movement_batches("la_average_day",17,20));c=next(iter_movement_batches("la_average_day",18,20))
    assert a==b and a!=c
    assert get_profile("la_peak_month_day")["record_count"]==19938
    assert get_profile("la_peak_month_day")["daily_teu_target"]==32898
    assert all(p["calibration"]["record_unit"]!="unique container" for p in profile_catalog())


def test_bounded_slot_negative_control_exact_capacity_and_persistent_active_state():
    rows=[movement(str(i))for i in range(100)]
    resources=initial_resource_state(2)
    first=schedule_window(rows,0,90,resources)
    assert first["metrics"]["completed_movements"]==36
    apply_rows(rows,first["updates"])
    second=schedule_window(rows,90,240,first["resource_state"])
    assert first["metrics"]["completed_movements"]+second["metrics"]["completed_movements"]==96
    assert sum(u["status"]=="completed"for u in second["updates"])==60
    assert resources["clock_min"]==0
    json.dumps(second,allow_nan=False)


def test_priority_never_prebooks_a_future_arrival_ahead_of_ready_work():
    rows=[movement("now",service=5,priority=1),movement("future",arrival=10,ready=10,service=5,priority=100)]
    result=schedule_window(rows,0,20,initial_resource_state(1,"priority"))
    updates={u["id"]:u for u in result["updates"]}
    assert updates["now"]["started_min"]==0
    assert updates["future"]["started_min"]==10


def test_terminal_scoped_closure_preserves_other_work_and_original_hold():
    rows=[movement("east"),movement("other",terminal=TERMINAL_IDS[1]),movement("held",blocked=True)]
    closed=schedule_window(rows,0,15,initial_resource_state(1),{TERMINAL_IDS[0]:{"closed":True}})
    update={u["id"]:u for u in closed["updates"]}
    assert update["east"]["status"]=="blocked"
    assert update["held"]["status"]=="blocked"
    assert update["other"]["status"]=="completed"
    apply_rows(rows,closed["updates"])
    opened=schedule_window(rows,15,30,closed["resource_state"],{})
    update={u["id"]:u for u in opened["updates"]}
    assert update["east"]["status"]=="completed"
    assert update["held"]["status"]=="blocked"


def test_interrupted_service_cannot_complete_during_closed_capacity():
    rows=[movement("ongoing",service=10)]
    first=schedule_window(rows,0,3,initial_resource_state(1));apply_rows(rows,first["updates"])
    assert rows[0]["status"]=="in_service"
    closed=schedule_window(rows,3,20,first["resource_state"],{TERMINAL_IDS[0]:{"capacity":0}})
    assert closed["metrics"]["completed_movements"]==0
    assert closed["metrics"]["interrupted_movements"]==1
    assert not closed["resource_state"]["in_service"]
    apply_rows(rows,closed["updates"])
    recovered=schedule_window(rows,20,35,closed["resource_state"])
    assert recovered["metrics"]["completed_movements"]==1
    assert recovered["updates"][0]["started_min"]==20


def test_input_limits_and_invalid_values_fail_without_mutating_state():
    resources=initial_resource_state(1);before=copy.deepcopy(resources)
    with pytest.raises(ValueError):schedule_window([movement(str(i))for i in range(2001)],0,30,resources)
    with pytest.raises(ValueError):schedule_window([movement("invalid",service=0)],0,30,resources)
    with pytest.raises(ValueError):schedule_window([movement("ok")],0,1500,resources)
    assert resources==before


def test_source_outage_marks_freshness_without_fabricating_a_physical_closure():
    rows=[movement("running",service=10),movement("later",arrival=4,ready=4)]
    first=schedule_window(rows,0,3,initial_resource_state(1));apply_rows(rows,first["updates"])
    during=schedule_window(rows,3,20,first["resource_state"],{TERMINAL_IDS[0]:{"source_offline":True}})
    updates={u["id"]:u for u in during["updates"]}
    assert updates["running"]["status"]=="completed"
    assert updates["later"]["status"]=="completed"
    assert during["metrics"]["source_freshness_unknown"]==1
    assert during["metrics"]["source_verification_waiting"]==0
    assert during["metrics"]["interrupted_movements"]==0


def test_channel_blocks_new_inbound_arrivals_not_queued_or_export_work():
    queued=movement("already",arrival=0);queued["status"]="queued"
    inbound=movement("new-import",arrival=5,ready=5)
    outbound=movement("new-export",arrival=5,ready=5);outbound["category"]="loaded_export";outbound["payload"]={"arrival_phase":"gate_in"}
    result=schedule_window([queued,inbound,outbound],3,30,initial_resource_state(2),{TERMINAL_IDS[0]:{"arrival_blocked":True}})
    updates={u["id"]:u for u in result["updates"]}
    assert updates["already"]["status"]=="completed"
    assert updates["new-export"]["status"]=="completed"
    assert updates["new-import"]["status"]=="blocked"


def test_newly_reported_hold_interrupts_service_and_duplicate_rows_are_rejected():
    rows=[movement("held-later",service=10)]
    first=schedule_window(rows,0,3,initial_resource_state(1));apply_rows(rows,first["updates"])
    rows[0]["blocked"]=True
    result=schedule_window(rows,3,30,first["resource_state"])
    assert result["metrics"]["completed_movements"]==0
    assert result["updates"][0]["status"]=="blocked"
    with pytest.raises(ValueError,match="distinct"):
        schedule_window([movement("same"),movement("same")],0,30)


def phased(identifier,category,arrival=0,service=5,status="scheduled"):
    row=movement(identifier,arrival=arrival,ready=arrival,service=service)
    row["category"]=category
    inbound=category.endswith("import")
    row["payload"]={"arrival_phase":"vessel_unload" if inbound else "gate_in","completion_phase":"gate_out" if inbound else "vessel_load"}
    row["status"]=status
    return row


def restriction(scenario,minute=3):
    return {TERMINAL_IDS[0]:{"phase_incidents":[{"scenario_id":scenario,"started_at_min":minute}]}}


def test_wind_stops_export_loads_and_future_unloads_but_preserves_yard_import_gateouts():
    rows=[phased("yard-import","loaded_import",status="queued"),phased("export-running","loaded_export",service=10),phased("future-import","loaded_import",arrival=5)]
    before=schedule_window(rows,0,3,initial_resource_state(2));apply_rows(rows,before["updates"])
    during=schedule_window(rows,3,20,before["resource_state"],restriction("storm_wind"))
    result={r["id"]:r for r in during["updates"]}
    assert result["yard-import"]["status"]=="completed"
    assert result["export-running"]["status"]=="blocked"
    assert result["future-import"]["status"]=="blocked"
    assert during["metrics"]["interrupted_movements"]==1
    apply_rows(rows,during["updates"])
    after=schedule_window(rows,20,40,during["resource_state"])
    assert after["metrics"]["completed_movements"]==2


def test_battery_access_blocks_gate_phase_but_not_already_arrived_export_load():
    rows=[phased("running-import","loaded_import",service=10),phased("yard-export","loaded_export",status="queued"),phased("future-export","loaded_export",arrival=5)]
    before=schedule_window(rows,0,3,initial_resource_state(2));apply_rows(rows,before["updates"])
    during=schedule_window(rows,3,20,before["resource_state"],restriction("battery_access_2024"))
    result={r["id"]:r for r in during["updates"]}
    assert result["running-import"]["status"]=="blocked"
    assert result["yard-export"]["status"]=="completed"
    assert result["future-export"]["status"]=="blocked"
    assert during["metrics"]["interrupted_movements"]==1


def test_channel_preserves_berthed_exports_and_preincident_imports_and_recovers_backlog():
    rows=[phased("before","loaded_import",arrival=1),phased("after","loaded_import",arrival=5),phased("export","loaded_export",arrival=5)]
    during=schedule_window(rows,3,20,initial_resource_state(2),restriction("channel_obstruction_2024"))
    result={r["id"]:r for r in during["updates"]}
    assert result["before"]["status"]=="completed"
    assert result["export"]["status"]=="completed"
    assert result["after"]["status"]=="blocked"
    apply_rows(rows,during["updates"])
    again=schedule_window(rows,20,30,during["resource_state"],restriction("channel_obstruction_2024"))
    assert again["metrics"]["completed_movements"]==0
    apply_rows(rows,again["updates"])
    opened=schedule_window(rows,30,40,again["resource_state"])
    assert opened["metrics"]["completed_movements"]==1
    assert opened["events"][0]["at_min"]==30


def test_exit_capacity_only_limits_gate_out_not_export_crane_service():
    rows=[phased("import-a","loaded_import"),phased("import-b","loaded_import"),phased("export-a","loaded_export"),phased("export-b","loaded_export")]
    restricted=schedule_window(rows,0,5,initial_resource_state(2),restriction("exit_congestion",0))
    starts=[e for e in restricted["events"] if e["type"]=="movement.started"]
    first=[e["movement_id"] for e in starts if e["at_min"]==0]
    assert len(first)==2
    assert sum(identifier.startswith("import") for identifier in first)<=1
    assert any(identifier.startswith("export") for identifier in first)
    assert restricted["metrics"]["completed_movements"]==2


def test_phase_layers_compose_and_unknown_or_future_incidents_fail_closed_validation():
    rows=[phased("import","loaded_import"),phased("export","loaded_export")]
    rules=restriction("storm_wind",0)
    rules[TERMINAL_IDS[0]]["phase_incidents"].append({"scenario_id":"battery_access_2024","started_at_min":0})
    both=schedule_window(rows,0,30,initial_resource_state(2),rules)
    assert both["metrics"]["completed_movements"]==0
    with pytest.raises(ValueError,match="future"):
        schedule_window(rows,0,30,initial_resource_state(2),restriction("storm_wind",5))
    with pytest.raises(ValueError,match="Unknown"):
        schedule_window(rows,0,30,initial_resource_state(2),restriction("magic",0))
    resources=initial_resource_state(1)
    resources["in_service"]={"omitted":{"terminal_id":TERMINAL_IDS[0],"slot_index":0,"started_min":0,"end_min":5,"teu":1}}
    with pytest.raises(ValueError,match="all persisted active"):
        schedule_window(rows,0,30,resources)
