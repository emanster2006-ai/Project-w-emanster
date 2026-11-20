from retrieval.tokenize import tokenize


def test_strips_attached_punctuation():
    assert tokenize("Revenue grew in 2018, then fell.") == [
        "revenue",
        "grew",
        "in",
        "2018",
        "then",
        "fell",
    ]


def test_keeps_numbers_with_separators_whole():
    assert "1,577" in tokenize("Capex was $1,577 million")
    assert "24.26" in tokenize("turnover ratio of 24.26.")


def test_is_case_insensitive():
    assert tokenize("3M Company") == ["3m", "company"]


def test_empty_text():
    assert tokenize("") == []
