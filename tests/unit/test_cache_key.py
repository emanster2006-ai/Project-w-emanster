from api.middleware.cache_key import is_reusable, options_key, signature


def test_different_year_is_a_different_question():
    a = "What was 3M's capital expenditure in fiscal year 2018?"
    b = "What was 3M's capital expenditure in fiscal year 2019?"
    assert signature(a) != signature(b)


def test_different_company_is_a_different_question():
    assert signature("What was Apple's R&D expense in 2022?") != signature(
        "What was Microsoft's R&D expense in 2022?"
    )


def test_rewording_keeps_the_same_signature():
    a = "What was 3M's capital expenditure in fiscal year 2018?"
    b = "what is the capital expenditure for 3M in fiscal year 2018"
    assert signature(a) == signature(b)


def test_leading_question_word_is_ignored():
    assert "what" not in signature("What was Apple revenue in 2022?")


def test_settings_must_match():
    q = "What was 3M's capital expenditure in fiscal year 2018?"
    sig = sorted(signature(q))
    assert is_reusable(q, sig, options_key(True, True, 5), options_key(True, True, 5))
    assert not is_reusable(
        q, sig, options_key(True, True, 5), options_key(False, False, 5)
    )
    assert not is_reusable(
        q, sig, options_key(True, True, 5), options_key(True, True, 10)
    )
