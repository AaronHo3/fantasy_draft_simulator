from __future__ import annotations

import pandas as pd
import pytest

from app.identity.crosswalk import CROSSWALK_COLUMNS, build_crosswalk
from app.sources.espn_public import parse_players
from app.sources.nba_stats import normalize_players


def _nba(rows):
    return pd.DataFrame(rows, columns=["nba_id", "name", "team"])


def _espn(rows):
    return pd.DataFrame(rows, columns=["espn_id", "name", "team"])


def test_stage_a_name_and_team_keeps_same_name_players_separate():
    nba = _nba([(1, "Jalen Williams", "OKC"), (2, "Jalen Williams", "SAS"), (3, "Luka Dončić", "LAL")])
    espn = _espn([(10, "Jalen Williams", "SAS"), (11, "Jalen Williams", "OKC"), (12, "Luka Doncic", "LAL")])
    xw, unresolved = build_crosswalk(nba, espn)
    assert list(xw.columns) == list(CROSSWALK_COLUMNS) and unresolved == []
    by_nba = xw.set_index("nba_id")
    assert by_nba.loc[1, "espn_id"] == 11 and by_nba.loc[2, "espn_id"] == 10
    assert (by_nba.loc[[1, 2], "match_method"] == "name_team").all()
    assert by_nba.loc[3, "espn_id"] == 12 and by_nba.loc[3, "match_method"] == "name_team"
    assert (xw["confidence"] == 1.0).all()
    assert set(xw["player_id"]) == {"nba:1", "nba:2", "nba:3"}


def test_stage_b_unique_name_links_across_team_mismatch():
    nba = _nba([(1, "Anfernee Simons", "CHI"), (2, "Mike Conley", "BOS")])
    espn = _espn([(10, "Anfernee Simons", "BOS"), (11, "Mike Conley", None)])
    xw, unresolved = build_crosswalk(nba, espn)
    assert unresolved == []
    by = xw.set_index("nba_id")
    assert by.loc[1, "espn_id"] == 10 and by.loc[1, "match_method"] == "name_unique"
    assert by.loc[1, "confidence"] == 0.9 and by.loc[1, "team"] == "CHI"  # NBA team wins
    assert by.loc[2, "espn_id"] == 11 and by.loc[2, "match_method"] == "name_unique"


def test_shared_name_without_team_agreement_is_never_merged():
    nba = _nba([(1, "Jaylin Williams", "OKC"), (2, "Jaylin Williams", "SAS")])
    espn = _espn([(10, "Jaylin Williams", "OKC"), (11, "Jaylin Williams", None)])
    xw, unresolved = build_crosswalk(nba, espn)
    by = xw.set_index("player_id")
    assert by.loc["nba:1", "espn_id"] == 10 and by.loc["nba:1", "match_method"] == "name_team"
    assert pd.isna(by.loc["nba:2", "espn_id"]) and by.loc["nba:2", "match_method"] == "nba_only"
    assert by.loc["espn:11", "match_method"] == "espn_only" and pd.isna(by.loc["espn:11", "nba_id"])
    reasons = {(u["source"], u["id"]): u["reason"] for u in unresolved}
    assert reasons == {("nba_api", 2): "ambiguous_name", ("espn_public", 11): "ambiguous_name_no_team"}


def test_unresolved_rows_and_canonical_ids():
    nba = _nba([(1, "Rookie Guy", "BOS"), (2, "Known Star", "PHI")])
    espn = _espn([(10, "Known Star", "PHI"), (11, "ESPN Only", None)])
    xw, unresolved = build_crosswalk(nba, espn)
    assert len(xw) == 3 and str(xw["nba_id"].dtype) == "Int64" and str(xw["espn_id"].dtype) == "Int64"
    assert set(xw["player_id"]) == {"nba:1", "nba:2", "espn:11"}
    assert xw["player_id"].is_unique
    assert [(u["source"], u["id"], u["reason"]) for u in unresolved] == [
        ("espn_public", 11, "no_candidate"),
        ("nba_api", 1, "no_candidate"),
    ]
    assert xw.set_index("player_id").loc["espn:11", "confidence"] == 0.0


def test_inputs_are_not_mutated_and_columns_validated():
    nba = _nba([(1, "A B", "BOS")])
    espn = _espn([(10, "A B", "BOS")])
    nba_before, espn_before = nba.copy(deep=True), espn.copy(deep=True)
    build_crosswalk(nba, espn)
    pd.testing.assert_frame_equal(nba, nba_before)
    pd.testing.assert_frame_equal(espn, espn_before)
    with pytest.raises(ValueError, match="lacks columns"):
        build_crosswalk(nba.drop(columns=["team"]), espn)


def test_crosswalk_on_recorded_fixtures(players_payload, espn_players_payload):
    nba = normalize_players(players_payload, "2026-27")
    espn = parse_players(espn_players_payload, 2027)
    xw, unresolved = build_crosswalk(nba, espn)
    linked = xw[xw["nba_id"].notna() & xw["espn_id"].notna()]
    assert len(linked) == 21 and (linked["match_method"] == "name_team").all()
    assert xw["player_id"].is_unique and len(xw) == 23  # 21 linked + 1 nba_only + 1 espn_only
    names = {(u["source"], u["name"]) for u in unresolved}
    assert names == {("nba_api", "Tucker DeVries"), ("espn_public", "N'Faly Dante")}
    gonzalez = linked[linked["name"].str.startswith("Hugo")].iloc[0]
    assert gonzalez["espn_id"] == 5175647  # accent-insensitive: González vs Gonzalez
