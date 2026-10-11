import numpy as np

from app.demo.generate import generate_demo_snapshot
from app.engine.categories import PRIM_IDX
from app.identity.players import normalize_name
from app.projections.snapshot import Snapshot, validate_snapshot


def test_normalize_name_handles_accents_suffixes_punctuation():
    assert normalize_name("Luka Dončić") == "luka doncic"
    assert normalize_name("Gary Trent Jr.") == "gary trent"
    assert normalize_name("De'Aaron Fox") == "deaaron fox"
    assert normalize_name("Shai Gilgeous-Alexander") == "shai gilgeous alexander"


def test_demo_snapshot_is_coherent_labeled_and_deterministic():
    s = generate_demo_snapshot()
    assert s.n == 600 and s.is_demo and s.source == "demo"
    assert validate_snapshot(s) == []
    pg = s.per_game
    assert np.all(pg[:, PRIM_IDX["FG3M"]] <= pg[:, PRIM_IDX["FGM"]] + 1e-9)
    assert np.all(pg[:, PRIM_IDX["FTM"]] <= pg[:, PRIM_IDX["FTA"]] + 1e-9)
    assert 100 < np.isfinite(s.adp).sum() <= 200
    assert all(p.eligible_positions for p in s.players)
    assert all(p.player_id.startswith("demo:") for p in s.players)
    s2 = generate_demo_snapshot()
    assert s2.snapshot_id == s.snapshot_id
    assert np.array_equal(s2.per_game, s.per_game)


def test_snapshot_roundtrip(tmp_path):
    s = generate_demo_snapshot(n_players=50)
    s.save(tmp_path / "snap")
    t = Snapshot.load(tmp_path / "snap")
    assert t.snapshot_id == s.snapshot_id and t.n == 50
    assert np.allclose(t.per_game, s.per_game) and np.array_equal(np.isnan(t.adp), np.isnan(s.adp))
    assert t.players[3] == s.players[3]
    tot = t.totals()
    assert tot[0, PRIM_IDX["PTS"]] == np.float64(s.per_game[0, PRIM_IDX["PTS"]] * s.games[0])
    assert tot[0, PRIM_IDX["MIN"]] == s.per_game[0, PRIM_IDX["MIN"]]
