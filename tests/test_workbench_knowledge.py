from gate_triage.workbench.knowledge import search_sources


def test_retrieval_keeps_scope_and_hold_restrictions():
    result = search_sources("customs hold authorization")
    assert result["llm_used"] is False
    assert result["items"][0]["id"] == "departure"
    assert "never overrides" in result["items"][0]["passage"]
    assert result["items"][0]["url"].startswith("https://terminal49.com/")


def test_retrieval_unknown_query_is_empty_not_invented():
    assert search_sources("xyzzy987654")['items'] == []


def test_chinese_delay_query_finds_feed_policy():
    assert search_sources("延迟重复数据")["items"][0]["id"] == "feed"
