import os

os.environ["MERIDIAN_EMBEDDING"] = "tfidf"
os.environ.pop("OPENAI_API_KEY", None)

from meridian.agent import run_desk
from meridian.calculate import liquidity_coverage_ratio, scenario_on_book, DEMO_BOOK
from meridian.compose import SAMPLE_POLICY, assess_policy
from meridian.guard import unsupported_instruments
from meridian.index import get_index
from meridian.questions import all_questions
from meridian.review import review_draft


def test_inflow_cap_changes_the_ratio():
    capped = liquidity_coverage_ratio(10, 10, 9)
    assert capped["inflows_recognised"] == 7.5
    assert capped["net_cash_outflow"] == 2.5
    assert capped["lcr_pct"] == 400.0

    plain = liquidity_coverage_ratio(12, 15, 5)
    assert plain["lcr_pct"] == 120.0
    assert plain["meets_minimum"] is True


def test_outflow_shock_can_breach_the_minimum():
    base = liquidity_coverage_ratio(12, 15, 5)
    shocked = liquidity_coverage_ratio(12, 18, 5)
    assert base["lcr_pct"] == 120.0
    assert shocked["lcr_pct"] == 92.3
    assert shocked["meets_minimum"] is False


def test_gold_labels_match_the_corpus():
    index = get_index()
    for question in all_questions():
        for chunk_id in question["gold_chunk_ids"]:
            assert chunk_id in index.by_id, chunk_id
        blob = " ".join(index.by_id[chunk_id].text for chunk_id in question["gold_chunk_ids"])
        for fact in question["gold_facts"]:
            assert fact.lower() in blob.lower(), (question["id"], fact)


def test_fake_instrument_abstains_and_real_article_does_not():
    index = get_index()
    assert unsupported_instruments("According to ECB Regulation XYZ-999, what is the LCR?", index)
    assert not unsupported_instruments(
        "What does Commission Delegated Regulation (EU) 2015/61 require?",
        index,
    )
    fake = run_desk("According to ECB Regulation XYZ-999, what minimum LCR may a bank hold?")
    assert fake["abstained"] is True
    assert "Insufficient evidence" in fake["answer"]
    assert fake["review"]["verdict"] == "abstained"
    real = run_desk("What is the LCR stress horizon?")
    assert real["abstained"] is False
    assert "30 calendar days" in real["answer"]
    assert real["review"]["verdict"] == "cleared"


def test_calculator_is_independent_of_the_model():
    result = run_desk("HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What is the LCR?")
    assert result["abstained"] is False
    assert "120.0 percent" in result["answer"]
    assert result["tool_result"]["base"]["lcr_pct"] == 120.0
    assert any(check["name"] == "Independent recalculation" and check["passed"] for check in result["review"]["checks"])


def test_reviewer_rejects_a_tampered_ratio():
    clean = run_desk("HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What is the LCR?")
    state = {
        "question": clean["question"],
        "draft": "On these inputs, the liquidity coverage ratio is 80.0 percent.",
        "citations": [],
        "chunks": [],
        "coverage": [],
        "unsupported": [],
        "abstain": False,
        "iteration": 1,
        "tool_result": {
            "tool": "lcr",
            "inputs": {"hqla": 12, "outflows": 15, "inflows": 5},
            "narrative": "On these inputs, the liquidity coverage ratio is 120.0 percent.",
        },
    }
    packet = review_draft(state, get_index())
    assert packet["review"]["verdict"] == "abstained"
    assert "Insufficient evidence" in packet["draft"]


def test_policy_excerpt_is_not_treated_as_the_bank_policy_when_absent():
    result = run_desk(
        "Compare our internal liquidity policy against EBA/ECB requirements and identify potential gaps."
    )
    assert result["abstained"] is False
    assert "cannot identify gaps" in result["answer"]
    covered = assess_policy(SAMPLE_POLICY, get_index().search)
    status = {row["id"]: row["status"] for row in covered}
    assert status["horizon"] == "mentioned"
    assert status["survival"] == "not_mentioned"
    assert status["intraday"] == "not_mentioned"


def test_wholesale_scenario_uses_the_illustrative_book():
    result = run_desk("How would a 20% increase in wholesale deposit outflows affect the bank's liquidity position?")
    expected = scenario_on_book(dict(DEMO_BOOK), "wholesale", 0.20)
    assert result["tool_result"]["base"]["lcr_pct"] == expected["base"]["lcr_pct"]
    assert result["tool_result"]["shocked"]["lcr_pct"] == expected["shocked"]["lcr_pct"]
    assert "illustrative book" in result["answer"]
    assert result["review"]["verdict"] == "cleared"
    assert result["orchestrator"] == "langgraph"
