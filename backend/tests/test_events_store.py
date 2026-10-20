import pytest

from app.draft.events import DraftError, EventType
from app.league.config import demo_league_config
from app.league.strategy import PuntKind, Strategy
from app.persistence.store import ConflictError, SessionStore


@pytest.fixture
def store(tmp_path):
    s = SessionStore(tmp_path / "t.sqlite")
    yield s
    s.close()


def new_session(store):
    cfg = demo_league_config()
    return store.create_session(cfg, name="t")


def commit(store, sid, player, expected=None, key=None, manager=None):
    st = store.state(sid)
    payload = {
        "player_id": player,
        "overall": st.current_pick.overall,
        "manager_id": manager or st.current_pick.manager_id,
    }
    return store.append(sid, EventType.pick_committed, payload, key, expected)


def test_commit_updates_availability_and_clock(store):
    sid = new_session(store)
    ev, st, dup = commit(store, sid, "p1")
    assert not dup and st.current_pick.overall == 2 and st.on_clock_manager_id == "m02"
    assert "p1" in st.drafted_player_ids
    assert st.draft_revision == ev.seq == 2
    assert st.roster("m01")[0].player_id == "p1"


def test_duplicate_player_and_wrong_manager_rejected(store):
    sid = new_session(store)
    commit(store, sid, "p1")
    with pytest.raises(DraftError) as e:
        commit(store, sid, "p1")
    assert e.value.code == "duplicate_player"
    with pytest.raises(DraftError) as e:
        commit(store, sid, "p2", manager="m07")
    assert e.value.code == "wrong_manager"
    with pytest.raises(DraftError) as e:
        store.append(sid, EventType.pick_committed, {"player_id": "p9", "overall": 5, "manager_id": "m05"})
    assert e.value.code == "not_on_clock"


def test_idempotency_and_optimistic_concurrency(store):
    sid = new_session(store)
    ev1, st1, _ = commit(store, sid, "p1", key="k1")
    ev2, st2, dup = commit(store, sid, "p1", key="k1")  # retry of the same submission
    assert dup and ev2.seq == ev1.seq and st2.current_pick.overall == 2
    with pytest.raises(ConflictError):
        commit(store, sid, "p2", expected=1)  # stale client revision
    _, st3, _ = commit(store, sid, "p2", expected=st2.last_seq)
    assert st3.current_pick.overall == 3


def test_undo_only_last_and_correction_anywhere(store):
    sid = new_session(store)
    commit(store, sid, "p1")
    commit(store, sid, "p2")
    with pytest.raises(DraftError) as e:
        store.append(sid, EventType.pick_undone, {"overall": 1})
    assert e.value.code == "not_last_pick"
    _, st, _ = store.append(sid, EventType.pick_undone, {})
    assert st.current_pick.overall == 2 and "p2" not in st.drafted_player_ids
    _, st, _ = store.append(sid, EventType.pick_corrected, {"overall": 1, "player_id": "p3"})
    assert st.roster("m01")[0].player_id == "p3" and "p1" not in st.drafted_player_ids
    # correcting to a player drafted elsewhere is rejected
    commit(store, sid, "p4")
    with pytest.raises(DraftError) as e:
        store.append(sid, EventType.pick_corrected, {"overall": 1, "player_id": "p4"})
    assert e.value.code == "duplicate_player"


def test_strategy_change_bumps_strategy_revision_not_draft_revision(store):
    sid = new_session(store)
    commit(store, sid, "p1")
    s = Strategy(punts={"FT_PCT": PuntKind.fixed})
    ev, st, _ = store.append(sid, EventType.strategy_changed, {"strategy": s.model_dump(mode="json")})
    assert st.strategy_revision == ev.seq and st.draft_revision == 2
    assert st.strategy.fixed_punts() == ["FT_PCT"]


def test_order_change_keeps_picks_and_warns(store):
    sid = new_session(store)
    commit(store, sid, "p1")  # m01 at pick 1
    _, st, _ = store.append(sid, EventType.order_changed, {"overrides": {1: "m02", 2: "m01"}})
    assert st.picks[1].player_id == "p1"
    assert any("pick 1" in w for w in st.warnings)
    assert st.current_pick.overall == 2 and st.on_clock_manager_id == "m01"


def test_replay_after_reload_and_export_import_roundtrip(store, tmp_path):
    sid = new_session(store)
    commit(store, sid, "p1")
    commit(store, sid, "p2")
    store.append(sid, EventType.pick_undone, {})
    store.close()
    s2 = SessionStore(tmp_path / "t.sqlite")
    st = s2.state(sid)
    assert st.current_pick.overall == 2 and st.drafted_player_ids == {"p1"}
    data = s2.export_session(sid)
    assert data["schema_version"] == 1 and len(data["events"]) == 4
    sid2 = s2.import_session(data)
    st2 = s2.state(sid2)
    assert st2.drafted_player_ids == st.drafted_player_ids and st2.last_seq == st.last_seq
    s2.close()


def test_user_next_pick_and_distance(store):
    sid = new_session(store)
    st = store.state(sid)
    assert st.user_next_pick().overall == 6 and st.picks_until_user_turn() == 5
    for i in range(6):
        commit(store, sid, f"p{i}")
    st = store.state(sid)
    assert st.current_pick.overall == 7 and st.user_next_pick().overall == 19
    assert st.picks_until_user_turn() == 12
    assert st.user_following_pick().overall == 30
    assert st.remaining_picks_for("m06") == 12


def test_batch_is_atomic(store):
    sid = new_session(store)
    items = [
        (EventType.pick_committed, {"player_id": "a", "overall": 1, "manager_id": "m01"}, None),
        (EventType.pick_committed, {"player_id": "a", "overall": 2, "manager_id": "m02"}, None),
    ]
    with pytest.raises(DraftError):
        store.append_batch(sid, items)
    assert store.state(sid).drafted_player_ids == frozenset()


# --- post-draft roster changes ----------------------------------------------------------------


def small_complete_session(store):
    """Two managers, two starters + one bench, every pick committed -> a complete draft."""
    cfg = demo_league_config(user_pick=1, n_managers=2).model_copy(
        update={"starting_slots": ["G", "F"], "bench_slots": 1, "ir_slots": 1}
    )
    sid = store.create_session(cfg, name="small")
    for i in range(cfg.n_managers * cfg.roster_size):
        commit(store, sid, f"p{i + 1}")
    st = store.state(sid)
    assert st.is_complete
    return sid


def roster_change(store, sid, moves, key=None, expected=None):
    return store.append(
        sid, EventType.roster_changed, {"moves": moves, "effective_at": "2026-10-19T00:00:00+00:00"}, key, expected
    )


def test_roster_changed_requires_complete_draft(store):
    sid = new_session(store)
    commit(store, sid, "p1")
    with pytest.raises(DraftError) as e:
        roster_change(store, sid, [{"manager_id": "m01", "added": ["fa1"], "dropped": ["p1"], "source_ref": "manual"}])
    assert e.value.code == "draft_incomplete"


def test_roster_changed_trade_is_atomic(store):
    sid = small_complete_session(store)
    before = store.state(sid)
    assert before.current_roster("m01") == ("p1", "p4", "p5")  # snake: m01 picks 1, 4, 5
    assert before.current_roster("m02") == ("p2", "p3", "p6")
    _, st, _ = roster_change(
        store,
        sid,
        [
            {"manager_id": "m01", "added": ["p2"], "dropped": ["p1"], "source_ref": "espn:tx1"},
            {"manager_id": "m02", "added": ["p1"], "dropped": ["p2"], "source_ref": "espn:tx1"},
        ],
    )
    assert st.current_roster("m01") == ("p4", "p5", "p2")
    assert st.current_roster("m02") == ("p3", "p6", "p1")
    assert st.owned_player_ids == before.owned_player_ids
    assert st.has_roster_moves and len(st.moves) == 2
    assert st.draft_revision == st.last_seq


def test_roster_changed_rejects_add_of_owned_player(store):
    sid = small_complete_session(store)
    with pytest.raises(DraftError) as e:
        roster_change(store, sid, [{"manager_id": "m01", "added": ["p2"], "dropped": ["p1"], "source_ref": "manual"}])
    assert e.value.code == "roster_conflict"
    assert store.state(sid).current_roster("m01") == ("p1", "p4", "p5")


def test_roster_changed_rejects_drop_by_non_owner(store):
    sid = small_complete_session(store)
    with pytest.raises(DraftError) as e:
        roster_change(store, sid, [{"manager_id": "m01", "added": [], "dropped": ["p2"], "source_ref": "manual"}])
    assert e.value.code == "roster_conflict"


def test_roster_changed_allows_ir_size(store):
    sid = small_complete_session(store)
    _, st, _ = roster_change(
        store, sid, [{"manager_id": "m01", "added": ["fa1"], "dropped": [], "source_ref": "manual"}]
    )
    assert st.current_roster("m01") == ("p1", "p4", "p5", "fa1")
    assert "fa1" in st.owned_player_ids
    assert st.current_rosters()["m02"] == ("p2", "p3", "p6")


def test_undo_locked_after_roster_change(store):
    sid = small_complete_session(store)
    roster_change(store, sid, [{"manager_id": "m01", "added": ["fa1"], "dropped": ["p1"], "source_ref": "manual"}])
    with pytest.raises(DraftError) as e:
        store.append(sid, EventType.pick_undone, {})
    assert e.value.code == "draft_locked"
    with pytest.raises(DraftError) as e2:
        store.append(sid, EventType.pick_corrected, {"overall": 1, "player_id": "zz"})
    assert e2.value.code == "draft_locked"


def test_state_view_exposes_current_rosters(store):
    from app.recommend.service import state_view

    sid = small_complete_session(store)
    roster_change(store, sid, [{"manager_id": "m01", "added": ["fa1"], "dropped": ["p1"], "source_ref": "manual"}])
    view = state_view(store.state(sid))
    assert view.current_rosters["m01"] == ["p4", "p5", "fa1"]
    assert "p1" not in view.owned_player_ids and "fa1" in view.owned_player_ids
    assert view.has_roster_moves is True
    assert view.rosters["m01"] == ["p1", "p4", "p5"]  # draft record is unchanged


def test_session_sync_roundtrip(store):
    sid = new_session(store)
    assert store.get_sync(sid) is None
    rec = {
        "league_id": 1,
        "fetched_at": "2026-10-19T00:00:00+00:00",
        "summary": "ESPN sync: 0 adds",
        "warnings": [],
        "changes": [],
        "power": None,
        "current_period": 1,
    }
    store.set_sync(sid, rec)
    assert store.get_sync(sid) == rec
    store.set_sync(sid, {**rec, "fetched_at": "later"})
    assert store.get_sync(sid)["fetched_at"] == "later"
    store.delete_session(sid)
    assert store.get_sync(sid) is None
