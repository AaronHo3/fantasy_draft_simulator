from app.league.config import demo_league_config


def make_session(client):
    r = client.post("/api/sessions", json={"league": demo_league_config().model_dump(mode="json")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def commit(client, sid, player_id, expected=None, key=None):
    st = client.get(f"/api/sessions/{sid}/state").json()
    body = {
        "type": "pick_committed",
        "payload": {
            "player_id": player_id,
            "overall": st["current_pick"]["overall"],
            "manager_id": st["current_pick"]["manager_id"],
        },
        "idempotency_key": key,
        "expected_revision": expected,
    }
    return client.post(f"/api/sessions/{sid}/events", json=body)


def test_health_and_snapshots(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["snapshots"][0]["is_demo"] and h["snapshots"][0]["n_players"] == 600
    players = client.get(f"/api/snapshots/{h['default_snapshot_id']}/players", params={"limit": 5}).json()
    assert len(players) == 5 and players[0]["rank"] == 1.0


def test_search_is_accent_and_token_insensitive(client):
    h = client.get("/api/health").json()
    sid_snap = h["default_snapshot_id"]
    all_players = client.get(f"/api/snapshots/{sid_snap}/players", params={"limit": 600}).json()
    name = all_players[10]["name"]
    first, last = name.split()[0], name.split()[-1]
    res = client.get(f"/api/snapshots/{sid_snap}/players", params={"q": f"{last.upper()} {first[:3]}"}).json()
    assert any(p["name"] == name for p in res)


def test_full_pick_loop_recommendation_excludes_drafted(client):
    sid = make_session(client)
    rec = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 10}).json()
    assert rec["tier"] == "A" and rec["ids"]["draft_revision"] == 0 and len(rec["shortlist"]) == 10
    assert any("DEMO" in n for n in rec["notes"]) and any("format" in n.lower() for n in rec["notes"])
    top = rec["highlighted"]["player_id"]
    assert rec["highlighted"]["reasons"] and rec["highlighted"]["category_deltas"]
    r = commit(client, sid, top)
    assert r.status_code == 200 and r.json()["state"]["current_pick"]["overall"] == 2
    rec2 = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 50}).json()
    assert all(c["player_id"] != top for c in rec2["shortlist"])
    assert rec2["ids"]["draft_revision"] == r.json()["event"]["seq"]
    # the drafted player is still searchable, flagged as drafted
    snap = client.get("/api/health").json()["default_snapshot_id"]
    pv = client.get(
        f"/api/snapshots/{snap}/players", params={"q": rec["highlighted"]["name"], "session_id": sid}
    ).json()
    assert pv[0]["drafted_by"] == "m01" and pv[0]["drafted_overall"] == 1


def test_errors_duplicate_conflict_wrong_manager(client):
    sid = make_session(client)
    commit(client, sid, "demo:0001")
    r = commit(client, sid, "demo:0001")
    assert r.status_code == 422 and r.json()["code"] == "duplicate_player"
    r = commit(client, sid, "demo:0002", expected=1)
    assert r.status_code == 409 and r.json()["code"] == "revision_conflict"
    r = client.post(
        f"/api/sessions/{sid}/events",
        json={"type": "pick_committed", "payload": {"player_id": "demo:0003", "overall": 2, "manager_id": "m09"}},
    )
    assert r.status_code == 422 and r.json()["code"] == "wrong_manager"
    assert client.get("/api/sessions/nope/state").status_code == 404


def test_idempotent_retry(client):
    sid = make_session(client)
    a = commit(client, sid, "demo:0001", key="k").json()
    b = commit(client, sid, "demo:0001", key="k").json()
    assert b["deduplicated"] and a["event"]["seq"] == b["event"]["seq"]


def test_undo_correct_strategy_and_preview(client):
    sid = make_session(client)
    for i in range(1, 6):
        commit(client, sid, f"demo:{i:04d}")
    st = client.get(f"/api/sessions/{sid}/state").json()
    assert st["on_clock_manager_id"] == "m06" and st["picks_until_user_turn"] == 0
    rec = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 5}).json()
    pick = rec["highlighted"]["player_id"]
    prev = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 5, "preview_player_id": pick}).json()
    assert prev["preview_player_id"] == pick and all(c["player_id"] != pick for c in prev["shortlist"])
    assert prev["preview_candidate"]["player_id"] == pick and prev["preview_candidate"]["category_deltas"]["PTS"]["delta"] > 0
    far = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 5, "preview_player_id": "demo:0500"}).json()
    assert far["preview_candidate"]["player_id"] == "demo:0500" and far["preview_candidate"]["category_deltas"] is not None
    assert any(a["player_id"] == pick for a in prev["user_roster"]["assignments"])
    commit(client, sid, pick)
    r = client.post(f"/api/sessions/{sid}/events", json={"type": "pick_undone", "payload": {}})
    assert r.status_code == 200 and r.json()["state"]["current_pick"]["overall"] == 6
    r = client.post(
        f"/api/sessions/{sid}/events",
        json={"type": "pick_corrected", "payload": {"overall": 1, "player_id": "demo:0099"}},
    )
    assert r.status_code == 200 and r.json()["state"]["rosters"]["m01"] == ["demo:0099"]
    strat = {"punts": {"FT_PCT": "fixed"}, "weights": {"AST": 1.3}}
    r = client.post(f"/api/sessions/{sid}/events", json={"type": "strategy_changed", "payload": {"strategy": strat}})
    assert r.status_code == 200 and r.json()["state"]["strategy_revision"] == r.json()["event"]["seq"]
    rec2 = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 5}).json()
    assert rec2["category_profile"]["punt_labels"]["FT_PCT"] == "fixed"
    assert rec2["category_profile"]["weights"]["FT_PCT"] == 0.0 and rec2["category_profile"]["weights"]["AST"] == 1.3
    assert rec2["ids"]["strategy_revision"] == r.json()["event"]["seq"]
    r = client.post(f"/api/sessions/{sid}/events", json={"type": "format_confirmed", "payload": {}})
    assert r.json()["state"]["format_confirmed"] is True


def test_compare_and_export_import(client):
    sid = make_session(client)
    rec = client.post(f"/api/sessions/{sid}/recommend/fast", json={"limit": 3}).json()
    ids = [c["player_id"] for c in rec["shortlist"]]
    cmp_ = client.post(f"/api/sessions/{sid}/compare", json={"player_ids": ids}).json()
    assert len(cmp_["players"]) == 3 and cmp_["keys"][0] == "PTS"
    commit(client, sid, ids[0])
    exp = client.get(f"/api/sessions/{sid}/export").json()
    assert exp["schema_version"] == 1 and len(exp["events"]) == 2
    imp = client.post("/api/sessions/import", json=exp)
    assert imp.status_code == 201
    st = client.get(f"/api/sessions/{imp.json()['id']}/state").json()
    assert st["drafted_player_ids"] == [ids[0]]
    bad = dict(exp)
    bad["schema_version"] = 99
    assert client.post("/api/sessions/import", json=bad).status_code == 422


def test_batch_import_atomic(client):
    sid = make_session(client)
    items = [
        {"type": "pick_committed", "payload": {"player_id": "demo:0001", "overall": 1, "manager_id": "m01"}},
        {"type": "pick_committed", "payload": {"player_id": "demo:0001", "overall": 2, "manager_id": "m02"}},
    ]
    r = client.post(f"/api/sessions/{sid}/events/batch", json={"items": items})
    assert r.status_code == 422
    assert client.get(f"/api/sessions/{sid}/state").json()["drafted_player_ids"] == []
    items[1]["payload"]["player_id"] = "demo:0002"
    r = client.post(f"/api/sessions/{sid}/events/batch", json={"items": items})
    assert r.status_code == 200 and r.json()["current_pick"]["overall"] == 3


def test_refine_job_lifecycle_or_501(client):
    sid = make_session(client)
    r = client.post(f"/api/sessions/{sid}/recommend/refine", json={"limit": 4})
    assert r.status_code in (202, 501)
    if r.status_code == 202:
        import time

        jid = r.json()["job_id"]
        for _ in range(100):
            j = client.get(f"/api/jobs/{jid}", params={"session_id": sid}).json()
            if j["status"] in ("done", "failed"):
                break
            time.sleep(0.05)
        assert j["status"] == "done", j.get("error")
        commit(client, sid, "demo:0001")
        j2 = client.get(f"/api/jobs/{jid}", params={"session_id": sid}).json()
        assert j2["stale"] is True and j2["result"] is None


def test_import_preview_and_apply(client):
    sid = make_session(client)
    snap = client.get("/api/health").json()["default_snapshot_id"]
    players = client.get(f"/api/snapshots/{snap}/players", params={"limit": 3}).json()
    tmpl = client.get("/api/templates/projections")
    assert tmpl.status_code == 200 and tmpl.text.startswith("player_id,name")
    head = tmpl.text.splitlines()[0]
    row = f"{players[0]['player_id']},,,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,mine"
    bad = ",Nobody,ZZ,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,mine"
    text = head + "\n" + row + "\n" + bad + "\n"
    pv = client.post(f"/api/sessions/{sid}/import/preview", json={"kind": "projections", "text": text}).json()
    assert pv["n_ok"] == 1 and pv["n_error"] == 1 and pv["rows"][1]["errors"]
    r = client.post(f"/api/sessions/{sid}/import/apply", json={"kind": "projections", "text": text})
    assert r.status_code == 422 and r.json()["code"] == "rows_with_errors"
    r = client.post(
        f"/api/sessions/{sid}/import/apply", json={"kind": "projections", "text": text, "skip_error_rows": True}
    )
    assert r.status_code == 200 and r.json()["applied_rows"] == 1
    new_snap = r.json()["snapshot_id"]
    assert new_snap != snap and client.get(f"/api/sessions/{sid}").json()["meta"]["snapshot_id"] == new_snap
    pv2 = client.get(f"/api/snapshots/{new_snap}/players", params={"q": players[0]["name"]}).json()
    assert pv2[0]["per_game"]["PTS"] == 26.5 and pv2[0]["projection_source"] == "import:mine"
    # picks import through the same endpoint
    text = "overall,manager_id,name\n1,m01,{}\n2,m02,{}\n".format(players[1]["name"], players[2]["name"])
    r = client.post(f"/api/sessions/{sid}/import/apply", json={"kind": "picks", "text": text})
    assert r.status_code == 200 and r.json()["state"]["current_pick"]["overall"] == 3


def test_registry_skips_corrupt_snapshot_and_serves_demo(tmp_path):
    from app.projections.registry import SnapshotRegistry

    bad = tmp_path / "snaps" / "bad"
    bad.mkdir(parents=True)
    (bad / "meta.json").write_text("{not json")
    reg = SnapshotRegistry(tmp_path / "demo", tmp_path / "snaps")
    reg.load_all()
    assert reg.list()[0].is_demo and "bad" in reg.errors


def test_league_profiles_rank_and_update(client):
    sid = make_session(client)
    p0 = client.get(f"/api/sessions/{sid}/profiles").json()
    assert len(p0["managers"]) == 12 and p0["keys"][0] == "PTS"
    assert all(m["n_players"] == 0 and m["totals"]["FG_PCT"] is None and m["rank"]["FG_PCT"] is None for m in p0["managers"])
    commit(client, sid, "demo:0001")
    p1 = client.get(f"/api/sessions/{sid}/profiles").json()
    m1 = p1["managers"][0]
    assert m1["manager_id"] == "m01" and m1["n_players"] == 1 and m1["rank"]["PTS"] == 1
    assert m1["totals"]["FG_PCT"] is not None and m1["attempts"]["FGA"] > 0
    assert p1["ids"]["draft_revision"] == 2
    # TOV: the only team with players has the most turnovers -> rank 12 among known... others have 0 TOV which ranks better
    assert m1["rank"]["TOV"] == 12


def test_punt_advisor_compares_scenarios_without_applying(client):
    sid = make_session(client)
    for i in range(1, 6):
        commit(client, sid, f"demo:{i:04d}")
    r = client.post(f"/api/sessions/{sid}/punt-advisor", json={"budget_ms": 8000})
    assert r.status_code == 200, r.text
    body = r.json()
    keys = [s["key"] for s in body["scenarios"]]
    assert "balanced" in keys and any(k.startswith("punt_") for k in keys)
    assert all(set(s["category_win_probs"]) == {"PTS", "REB", "AST", "STL", "BLK", "FG3M", "FG_PCT", "FT_PCT", "TOV"} for s in body["scenarios"])
    assert body["objective_label"].startswith("expected categories won")
    assert body["scenarios"] == sorted(body["scenarios"], key=lambda s: -s["objective"])
    # nothing was applied
    st = client.get(f"/api/sessions/{sid}/state").json()
    assert st["strategy"]["punts"] == {}
