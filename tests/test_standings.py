import pandas as pd

from brighton.transform.standings import final_table, standings_by_round


def _matches(rows):
    return pd.DataFrame(rows, columns=["season", "team_id", "round", "pts", "goals_for", "goals_against"])


def test_tiebreak_points_then_goal_difference_then_goals():
    df = _matches(
        [
            # A e B empatam em pontos e saldo; A fez mais gols
            (2026, "A", 1, 3, 3, 1),
            (2026, "B", 1, 3, 2, 0),
            (2026, "C", 1, 0, 1, 3),
            (2026, "D", 1, 0, 0, 2),
            (2026, "A", 2, 0, 0, 1),
            (2026, "B", 2, 1, 1, 1),
            (2026, "C", 2, 3, 2, 0),
            (2026, "D", 2, 1, 1, 1),
        ]
    )
    st = standings_by_round(df)
    r1 = st[st["round"] == 1].set_index("team_id")["position"].to_dict()
    assert r1 == {"A": 1, "B": 2, "C": 3, "D": 4}

    r2 = st[st["round"] == 2].set_index("team_id")
    # B 4 pts (+2), A 3 pts (+1), C 3 pts (0), D 1 pt
    assert r2["position"].to_dict() == {"A": 2, "B": 1, "C": 3, "D": 4}
    assert r2.loc["B", "ppg_cum"] == 2.0

    fin = final_table(st).set_index("team_id")
    assert fin.loc["B", "final_position"] == 1 and fin.loc["B", "pts_cum"] == 4


def test_full_tie_shares_position():
    df = _matches([(2026, "A", 1, 1, 1, 1), (2026, "B", 1, 1, 1, 1)])
    st = standings_by_round(df)
    assert set(st["position"]) == {1}
