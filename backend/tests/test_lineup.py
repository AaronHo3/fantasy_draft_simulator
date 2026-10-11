from app.engine.lineup import assign_lineup, check_position_caps, completion_feasible, evaluate_roster
from app.league.config import LeagueConfig, Manager

PG, SG, SF, PF, C = (frozenset({p}) for p in ("PG", "SG", "SF", "PF", "C"))


def cfg(**kw):
    ms = [Manager(id=c, name=c) for c in "ab"]
    return LeagueConfig(managers=ms, user_manager_id="a", **kw)


def test_multi_eligible_player_fills_one_slot_and_starters_preferred():
    slots = ("PG", "SG", "G", "UTIL", "BENCH")
    players = [frozenset({"PG", "SG"}), PG, PG]
    a = assign_lineup(players, slots, n_starting=4)
    assert a.legal
    used = sorted(a.slot_of(i) for i in range(3))
    assert used == ["G", "PG", "SG"] or set(used) <= {"PG", "SG", "G", "UTIL"}
    assert len(set(a.assigned.values())) == 3  # three distinct slots
    assert "BENCH" not in used  # starting slots preferred


def test_center_cannot_fill_guard_slot_and_is_reported():
    a = assign_lineup([C, C], ("PG", "G"), n_starting=2)
    assert not a.legal
    assert a.unassigned_players == (0, 1)
    assert a.open_slots() == ["PG", "G"]


def test_g_f_util_compatibility():
    slots = ("G", "F", "UTIL")
    a = assign_lineup([SF, C, SG], slots, n_starting=3)
    assert a.legal
    assert a.slot_of(0) == "F" and a.slot_of(1) == "UTIL" and a.slot_of(2) == "G"


def test_unknown_eligibility_cannot_be_assigned():
    a = assign_lineup([frozenset()], ("UTIL",), n_starting=1)
    assert not a.legal


def test_bench_absorbs_overflow_but_coverage_shows_open_slots():
    c = cfg(starting_slots=["PG", "C"], bench_slots=2)
    rep = evaluate_roster(c, [PG, PG, PG], ["PG", "PG", "PG"], remaining_picks=1, available_positions=[C, SG])
    assert rep.legal  # all three fit (PG + two bench)
    assert rep.starting_filled == 1 and rep.open_starting_slots == ("C",)
    assert rep.bench_used == 2
    assert rep.completion_feasible  # a C is available and we have a pick left


def test_completion_infeasible_when_no_eligible_supply_or_no_picks():
    ok, why = completion_feasible(["C"], 2, [PG, SG])
    assert not ok and "C" in why
    ok, why = completion_feasible(["C", "PF"], 1, [C, PF])
    assert not ok and "picks left" in why
    ok, _ = completion_feasible(["C", "PF"], 2, [C, PF])
    assert ok
    # the same player cannot fill two open slots
    ok, _ = completion_feasible(["C", "PF"], 2, [frozenset({"C", "PF"})])
    assert not ok


def test_primary_position_caps_independent_of_slots():
    c = cfg(position_caps={"C": 2})
    check = check_position_caps(c, ["C", "C", "C", "PG"])
    assert not check.ok and check.violations == {"C": 1}
    assert check_position_caps(c, ["C", "PG"]).room == {"C": 1}
