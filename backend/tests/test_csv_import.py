import pytest

from app.demo.generate import generate_demo_snapshot
from app.engine.categories import PRIM_IDX
from app.imports.csv_import import (
    apply_adp,
    apply_eligibility,
    apply_projections,
    picks_to_events,
    preview_adp,
    preview_eligibility,
    preview_picks,
    preview_projections,
)


@pytest.fixture(scope="module")
def snap():
    return generate_demo_snapshot()


def proj_csv(rows):
    head = "player_id,name,team,season,games,minutes_per_game,pts_per_game,reb_per_game,ast_per_game,stl_per_game,blk_per_game,fg3m_per_game,fg3a_per_game,fgm_per_game,fga_per_game,ftm_per_game,fta_per_game,tov_per_game,uncertainty_cv,source"
    return head + "\n" + "\n".join(rows) + "\n"


def test_projection_preview_validates_units_and_coherence(snap):
    p0, p1, p2, p3 = snap.players[:4]
    text = proj_csv(
        [
            f"{p0.player_id},,,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,mine",
            f",{p1.name},{p1.team},x,70,34,20,5,5,1,0.5,2,5,7,15,3,4,2,,mine",  # resolve by name
            f",{p2.name},{p2.team},x,70,34,20,5,5,1,0.5,9,5,7,15,3,4,2,,mine",  # fg3m > fgm
            ",Nobody Real,ZZZ,x,70,34,20,5,5,1,0.5,2,5,7,15,3,4,2,,mine",  # unknown
            f",{p3.name},{p3.team},x,90,34,20,5,5,1,0.5,2,5,7,0,3,4,2,,mine",  # games>82, fga=0
        ]
    )
    pv = preview_projections(text, snap)
    assert pv.missing_columns == () and pv.n_ok == 2 and pv.n_error == 3
    assert pv.rows[0].player_id == p0.player_id and pv.rows[1].player_id == p1.player_id
    assert any("fg3m > fgm" in e for e in pv.rows[2].errors)
    assert any("no player named" in e for e in pv.rows[3].errors)
    assert any("games > 82" in e for e in pv.rows[4].errors) and any("fga_per_game" in e for e in pv.rows[4].errors)
    dup = preview_projections(
        proj_csv(
            [
                f"{p0.player_id},,,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,a",
                f"{p0.player_id},,,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,b",
            ]
        ),
        snap,
    )
    assert dup.n_ok == 0 and all("duplicate" in e for r in dup.rows for e in r.errors)
    # a bad percentage-free file is rejected: missing fga column
    pv2 = preview_projections("name,games\nX,70\n", snap)
    assert "fga_per_game" in pv2.missing_columns


def test_apply_projections_creates_new_snapshot_without_mutating(snap):
    p0 = snap.players[0]
    text = proj_csv([f"{p0.player_id},,,x,70,34,26.5,12,9.5,1.4,0.8,1.5,3.9,10.3,18,4.4,5.4,3.2,0.1,mine"])
    pv = preview_projections(text, snap)
    before = snap.per_game[0].copy()
    new = apply_projections(pv, snap)
    assert new.snapshot_id != snap.snapshot_id
    assert new.per_game[0, PRIM_IDX["PTS"]] == 26.5 and new.projection_source[0] == "import:mine"
    assert (snap.per_game[0] == before).all() and snap.projection_source[0] == "demo"
    assert new.provenance["imports"][0]["rows"] == 1


def test_eligibility_import(snap):
    p0 = snap.players[0]
    text = f"player_id,name,primary_position,eligible_positions,source\n{p0.player_id},,PF,PF;C,espn-manual\n,{snap.players[1].name},PG,SG,manual\n,{snap.players[2].name},,XX,manual\n"
    pv = preview_eligibility(text, snap)
    assert pv.n_ok == 1 and pv.n_error == 2
    assert any("primary_position must be" in e for e in pv.rows[1].errors)
    new = apply_eligibility(pv, snap)
    assert new.players[0].eligible_positions == frozenset({"PF", "C"}) and new.players[0].eligibility_verified
    assert (
        snap.players[0].eligible_positions != new.players[0].eligible_positions
        or snap.players[0].eligibility_source == "demo"
    )


def test_adp_import_labels_platform(snap):
    p0 = snap.players[0]
    text = f"player_id,name,platform,adp,rank,as_of_date\n{p0.player_id},,yahoo,3.5,2,2026-10-01\n,{snap.players[1].name},espn,,5,\n,{snap.players[2].name},,,,\n"
    pv = preview_adp(text, snap)
    assert pv.n_ok == 2 and any("not ESPN-specific" in w for w in pv.rows[0].warnings)
    assert any("adp or rank required" in e for e in pv.rows[2].errors)
    new = apply_adp(pv, snap)
    assert new.adp[0] == 3.5 and new.rank[1] == 5 and "yahoo" in new.adp_platform


def test_picks_import_to_events(snap):
    names = {snap.players[i].name for i in range(3)}
    text = "overall,manager_id,manager_name,name\n2,,Team 2,{}\n1,m01,,{}\n3,m99,,{}\n".format(*names)
    pv = preview_picks(
        text, snap, [f"m{i:02d}" for i in range(1, 13)], {f"m{i:02d}": f"Team {i}" for i in range(1, 13)}
    )
    assert pv.n_ok == 2 and any("unknown manager" in e for e in pv.rows[2].errors)
    evs = picks_to_events(pv)
    assert [e["overall"] for e in evs] == [1, 2] and evs[1]["manager_id"] == "m02"
