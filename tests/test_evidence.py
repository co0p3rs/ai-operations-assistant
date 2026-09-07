from app.evidence import evidence_gap_response, evidence_issues


def test_rejects_claimed_source_without_a_tool_call() -> None:
    issues = evidence_issues(
        "I checked Commerce and revenue is up.",
        successful_tools=set(),
    )
    assert issues
    assert issues[0].source == "Commerce"


def test_allows_source_after_successful_tool() -> None:
    issues = evidence_issues(
        "I checked Commerce and revenue is up.",
        successful_tools={"commerce_order_totals"},
    )
    assert issues == []


def test_gap_response_names_sources() -> None:
    issues = evidence_issues("According to Ads, CPA fell.", successful_tools=set())
    text = evidence_gap_response(issues)
    assert "Ads" in text
    assert "won't claim" in text
