from retrieval.year_boost import apply_year_bonus, query_years, year_bonus


def chunk(year):
    return {"text": "t", "metadata": {"year": year}}


def test_extracts_years_not_other_numbers():
    assert query_years("What was capex in FY2018 vs 2019?") == {"2018", "2019"}
    assert query_years("revenue of $12018 million") == set()
    assert query_years("no year here") == set()


def test_reads_two_digit_fiscal_years():
    assert query_years("Did Pfizer grow its PPNE between FY20 and FY21?") == {
        "2020",
        "2021",
    }
    assert query_years("FY '19 revenue") == {"2019"}
    assert query_years("FY2018 and FY 2019") == {"2018", "2019"}


def test_bonus_only_for_named_year(monkeypatch):
    monkeypatch.setenv("RERANK_YEAR_BONUS", "3")
    scores = apply_year_bonus(
        "3M capex FY2018",
        [chunk("2018"), chunk("2022"), {"text": "x"}],
        [1.0, 2.0, 2.0],
    )
    assert scores == [4.0, 2.0, 2.0]


def test_no_years_in_query_changes_nothing(monkeypatch):
    monkeypatch.setenv("RERANK_YEAR_BONUS", "3")
    assert apply_year_bonus("what is capex", [chunk("2018")], [1.0]) == [1.0]


def test_can_be_disabled_and_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("RERANK_YEAR_BONUS", "0")
    assert apply_year_bonus("FY2018", [chunk("2018")], [1.0]) == [1.0]
    monkeypatch.setenv("RERANK_YEAR_BONUS", "oops")
    assert year_bonus() == 3.0
