import pandas as pd

from app.demo.generate import generate_demo_snapshot
from app.season.live_status import status_overlay


def test_status_overlay_marks_players_without_a_team():
    from dataclasses import replace

    snap = generate_demo_snapshot(n_players=5)
    players = [replace(p, espn_id=1000 + i) for i, p in enumerate(snap.players)]
    snap = replace(snap, players=tuple(players))
    live = pd.DataFrame(
        {
            "espn_id": [1000, 1001, 1002],
            "injury_status": ["ACTIVE", "ACTIVE", "OUT"],
            "percent_owned": [50.0, 60.0, 1.0],
            "team": ["BOS", None, "MIL"],
            "fetched_at": ["t", "t", "t"],
        }
    )
    ov = status_overlay(snap, live)
    assert ov[players[0].player_id]["injury_status"] == "ACTIVE" and ov[players[0].player_id]["team"] == "BOS"
    assert ov[players[1].player_id]["injury_status"] == "NO_TEAM" and ov[players[1].player_id]["team"] is None
    assert ov[players[2].player_id]["injury_status"] == "OUT"
    assert ov[players[3].player_id]["injury_status"] == players[3].injury_status  # no live row: snapshot status
