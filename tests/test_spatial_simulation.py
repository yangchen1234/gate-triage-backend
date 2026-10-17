import copy
import json

import pytest

from gate_triage.workbench.engine import create_state, apply_command, _set_incident
from gate_triage.workbench.spatial_simulation import (advance_spatial_operations, apply_incident_effects,
    initialize_in_place, resolve_incident_effects, spatial_snapshot)


def incident(identifier, effects, status="active"):
    return {"id":identifier,"scope_id":"zone-vessel-load","status":status,"severity":"critical","effects":effects}


def step(state, target):
    initialize_in_place(state)
    advance_spatial_operations(state)
    while state["clock_min"] < target:
        state["clock_min"] += 1
        advance_spatial_operations(state)


def test_spatial_workorders_are_clock_driven_and_never_count_gate_handoffs():
    state=create_state("normal_operations")
    initialize_in_place(state)
    assert len(state["spatial_operations"]["workorders"])==12
    step(state,240)
    model=spatial_snapshot(state)
    assert model["metrics"]["completed_unload_workorders"]==4
    assert model["metrics"]["completed_load_workorders"]==5
    assert model["metrics"]["completed_arrivals"]==1
    assert model["metrics"]["completed_departures"]==2
    assert len(state["containers"])==100
    assert len(state["completed"])==0
    assert all(o["progress"]==1 for o in model["workorders"])
    json.dumps(state,allow_nan=False)


def test_marine_closure_stops_transits_but_not_already_berthed_crane_work():
    base=create_state("normal_operations")
    original=json.dumps(base,sort_keys=True)
    closed=incident("channel",[{"kind":"marine_channel","status":"closed"}])
    state=apply_incident_effects(base,closed,[closed])
    step(state,100)
    metrics=spatial_snapshot(state)["metrics"]
    assert metrics["completed_unload_workorders"]==2
    assert metrics["completed_load_workorders"]==2
    assert metrics["completed_arrivals"]==0
    assert metrics["completed_departures"]==0
    state=resolve_incident_effects(state,{**closed,"status":"resolved"},[])
    step(state,240)
    assert spatial_snapshot(state)["metrics"]["completed_departures"]==2
    assert base["clock_min"]==0 and json.dumps(base,sort_keys=True)==original


def test_overlapping_capacity_layers_and_preexisting_closure_remain_independent():
    state=create_state("normal_operations")
    _set_incident(state,"closed",["west-lane-1"],0)
    one=incident("one",[{"kind":"resource_capacity","resource_id":"east-lane-1","capacity":0},
                         {"kind":"resource_capacity","resource_id":"west-lane-1","capacity":0}])
    two=incident("two",[{"kind":"resource_capacity","resource_id":"east-lane-1","capacity":0}])
    state=apply_incident_effects(state,one,[one])
    state=apply_incident_effects(state,two,[one,two])
    state=resolve_incident_effects(state,{**one,"status":"resolved"},[two])
    assert state["resources"]["east-lane-1"]["available_capacity"]==0
    state=resolve_incident_effects(state,{**two,"status":"resolved"},[])
    assert state["resources"]["east-lane-1"]["available_capacity"]==1
    assert state["resources"]["west-lane-1"]["available_capacity"]==0


def test_crane_pause_progress_excludes_closed_minutes_and_resumes():
    state=create_state("normal_operations")
    step(state,3)
    order=next(o for o in state["spatial_operations"]["workorders"]if o["status"]=="in_progress")
    before=order["service_minutes"]
    closed=incident("crane",[{"kind":"resource_capacity","resource_id":order["resource_id"],"capacity":0}])
    state=apply_incident_effects(state,closed,[closed])
    step(state,20)
    paused=next(o for o in state["spatial_operations"]["workorders"]if o["id"]==order["id"])
    assert paused["status"]=="paused"
    assert paused["service_minutes"]==before
    state=resolve_incident_effects(state,{**closed,"status":"resolved"},[])
    step(state,21)
    resumed=next(o for o in state["spatial_operations"]["workorders"]if o["id"]==order["id"])
    assert resumed["service_minutes"]==before+1


def test_overlapping_feed_incidents_never_clear_an_independent_source_outage():
    state=create_state("normal_operations")
    one=incident("cyber-a",[{"kind":"feed_offline"}]);two=incident("cyber-b",[{"kind":"feed_offline"}])
    state=apply_incident_effects(state,one,[one])
    state=apply_incident_effects(state,two,[one,two])
    state=resolve_incident_effects(state,{**one,"status":"resolved"},[two])
    assert not state["provider_online"]
    state["world_provider_online"]=False
    state=resolve_incident_effects(state,{**two,"status":"resolved"},[])
    assert not state["provider_online"]


def test_monitoring_has_no_physical_effect_and_bad_effect_is_copy_safe():
    state=create_state("normal_operations")
    notice=incident("notice",[],"monitoring")
    observed=apply_incident_effects(state,notice,[notice])
    assert all(observed["resources"][rid]["available_capacity"]==r["available_capacity"] for rid,r in state["resources"].items())
    before=json.dumps(state,sort_keys=True)
    invalid=incident("bad",[{"kind":"resource_capacity","resource_id":"invented-crane","capacity":0}])
    with pytest.raises(ValueError):
        apply_incident_effects(state,invalid,[invalid])
    assert json.dumps(state,sort_keys=True)==before
    with pytest.raises(ValueError):
        apply_incident_effects(create_state("normal_operations",mode="REPLAY_T49"),invalid,[invalid])


def test_manual_closure_and_spatial_recovery_preserve_each_others_layers():
    state=create_state("normal_operations")
    spatial=incident("spatial",[{"kind":"resource_capacity","resource_id":"east-lane-1","capacity":0}])
    state=apply_incident_effects(state,spatial,[spatial])
    state=apply_command(state,{"command":"incident","status":"closed"})
    state=resolve_incident_effects(state,{**spatial,"status":"resolved"},[])
    assert state["resources"]["east-lane-1"]["available_capacity"]==0
    assert state["resources"]["east-lane-2"]["available_capacity"]==0
    state=apply_incident_effects(state,spatial,[spatial])
    state=apply_command(state,{"command":"incident","status":"open"})
    assert state["resources"]["east-lane-1"]["available_capacity"]==0
    assert state["resources"]["east-lane-2"]["available_capacity"]==1
    state=resolve_incident_effects(state,{**spatial,"status":"resolved"},[])
    assert state["resources"]["east-lane-1"]["available_capacity"]==1


def test_full_simulation_hook_advances_vessel_work_separately_from_cohort():
    state=apply_command(create_state("normal_operations"),{"command":"advance","minutes":120,"strategy":"fifo"})
    assert spatial_snapshot(state)["metrics"]["completed_unload_workorders"]==4
    assert spatial_snapshot(state)["metrics"]["completed_load_workorders"]>=4
    assert len(state["containers"])==100
    assert len(state["completed"])<=100


def test_direct_experiment_rejects_duplicate_seeds():
    from gate_triage.workbench.engine import experiment
    with pytest.raises(ValueError,match="distinct"):
        experiment("normal_operations",[17,17],30)
