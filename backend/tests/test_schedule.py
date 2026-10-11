from app.draft.schedule import build_pick_schedule, next_pick_for_manager, picks_between, picks_for_manager
from app.league.config import Keeper, LeagueConfig, Manager, TradedPick, demo_league_config


def test_snake_order_and_distances():
    cfg = demo_league_config(user_pick=6)
    s = build_pick_schedule(cfg)
    assert len(s) == 12 * 13
    assert [p.manager_id for p in s[:12]] == [f"m{i:02d}" for i in range(1, 13)]
    assert s[12].manager_id == "m12" and s[23].manager_id == "m01"  # round 2 reversed
    mine = picks_for_manager(s, "m06")
    assert [p.overall for p in mine[:3]] == [6, 19, 30]
    nxt = next_pick_for_manager(s, "m06", after_overall=6)
    assert nxt.overall == 19
    assert picks_between(6, 19) == 12
    assert next_pick_for_manager(s, "m06", after_overall=156) is None


def test_third_round_reversal():
    ms = [Manager(id=c, name=c) for c in "abcd"]
    cfg = LeagueConfig(
        managers=ms, user_manager_id="a", third_round_reversal=True, starting_slots=["PG", "SG"], bench_slots=3
    )
    s = build_pick_schedule(cfg)
    rounds = [[p.manager_id for p in s if p.round == r] for r in range(1, 6)]
    assert rounds[0] == list("abcd")
    assert rounds[1] == list("dcba")
    assert rounds[2] == list("dcba")
    assert rounds[3] == list("abcd")
    assert rounds[4] == list("dcba")


def test_linear_order():
    ms = [Manager(id=c, name=c) for c in "abc"]
    cfg = LeagueConfig(managers=ms, user_manager_id="a", draft_type="linear", starting_slots=["PG"], bench_slots=1)
    s = build_pick_schedule(cfg)
    assert [p.manager_id for p in s] == list("abcabc")


def test_keepers_and_traded_picks_and_overrides():
    ms = [Manager(id=c, name=c) for c in "abcd"]
    cfg = LeagueConfig(
        managers=ms,
        user_manager_id="a",
        starting_slots=["PG", "SG"],
        bench_slots=1,
        keepers=[Keeper(manager_id="b", player_id="p-keep", round=1)],
        traded_picks=[TradedPick(round=2, from_manager_id="a", to_manager_id="c")],
    )
    s = build_pick_schedule(cfg, overrides={12: "d"})
    assert s[1].manager_id == "b" and s[1].keeper_player_id == "p-keep"
    # round 2 is reversed: d c b a ; a's slot (overall 8) now belongs to c
    r2 = [p for p in s if p.round == 2]
    assert r2[3].original_manager_id == "a" and r2[3].manager_id == "c"
    assert s[11].manager_id == "d"
    # the next non-keeper pick for b after the draft starts is in round 2
    assert next_pick_for_manager(s, "b", 0).round == 2
