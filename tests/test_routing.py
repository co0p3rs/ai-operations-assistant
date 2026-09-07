from app.routing import Intent, route_intent


def test_keyword_routing() -> None:
    assert route_intent("Show 12-month LTV by cohort") is Intent.COHORT
    assert route_intent("What is inventory days cover in the west warehouse?") is Intent.INVENTORY
    assert route_intent("How is lookalike-summer CPA?") is Intent.ADS
    assert route_intent("What was revenue last week?") is Intent.COMMERCE
    assert route_intent("hello there") is Intent.UNKNOWN
