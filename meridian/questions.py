"""Benchmark questions for retrieval, calculation, comparison, and abstention."""

from __future__ import annotations


def _q(qid, kind, question, gold=(), facts=(), **extra):
    item = {
        "id": qid,
        "type": kind,
        "question": question,
        "gold_chunk_ids": list(gold),
        "gold_facts": list(facts),
        "expect_abstain": False,
    }
    item.update(extra)
    return item


QUESTIONS = [
    _q("F01", "factual", "What is the LCR stress horizon?", ["lcr-framework::the-30-day-liquidity-coverage-requirement"], ["30 calendar days"]),
    _q("F02", "factual", "What is the minimum LCR?", ["lcr-framework::the-binding-100-percent-minimum"], ["The minimum LCR is 100 percent"]),
    _q("F03", "factual", "Does the LCR stress scenario combine an idiosyncratic shock with a market-wide shock?", ["lcr-framework::combined-idiosyncratic-and-market-wide-stress"], ["idiosyncratic shock with a market-wide shock"]),
    _q("F04", "factual", "Which EU legal act specifies the binding liquidity coverage ratio?", ["lcr-framework::eu-implementation-in-crr-and-the-lcr-delegated-act"], ["Commission Delegated Regulation (EU) 2015/61"]),
    _q("F05", "factual", "What haircut applies to Level 1 assets in the LCR?", ["hqla::level-1-assets-and-the-zero-haircut"], ["zero haircut"]),
    _q("F06", "factual", "What haircut applies to Level 2A assets?", ["hqla::level-2a-assets-and-the-15-percent-haircut"], ["15 percent haircut"]),
    _q("F07", "factual", "What is the composition cap on Level 2 assets in HQLA?", ["hqla::level-2a-assets-and-the-15-percent-haircut"], ["40 percent of the total HQLA stock"]),
    _q("F08", "factual", "What is the Level 2B composition cap?", ["hqla::level-2b-assets-and-the-15-percent-composition-cap"], ["15 percent composition cap"]),
    _q("F09", "factual", "What haircut applies to eligible residential mortgage-backed securities counted as Level 2B assets?", ["hqla::level-2b-assets-and-the-15-percent-composition-cap"], ["25 percent haircut"]),
    _q("F10", "factual", "What is the LCR inflow cap?", ["net-cash-outflows::the-75-percent-inflow-cap"], ["75 percent of total expected cash outflows"]),
    _q("F11", "factual", "What is the run-off rate for stable retail deposits?", ["net-cash-outflows::retail-deposit-run-off-rates"], ["Stable retail deposits run off at 5 percent"]),
    _q("F12", "factual", "What is the run-off rate for less stable retail deposits?", ["net-cash-outflows::retail-deposit-run-off-rates"], ["Less stable retail deposits run off at 10 percent"]),
    _q("F13", "factual", "What is the run-off rate for operational deposits?", ["net-cash-outflows::wholesale-funding-run-off-rates"], ["run off at 25 percent"]),
    _q("F14", "factual", "What run-off rate applies to unsecured wholesale funding from financial institutions?", ["net-cash-outflows::wholesale-funding-run-off-rates"], ["runs off at 100 percent"]),
    _q("F15", "factual", "What is the NSFR time horizon?", ["nsfr::the-one-year-stable-funding-requirement"], ["The NSFR stress horizon is one year"]),
    _q("F16", "factual", "What ASF factor applies to stable retail deposits under the NSFR?", ["nsfr::available-stable-funding-factors"], ["95 percent ASF factor"]),
    _q("F17", "factual", "Which CRR article requires liquid assets to cover stressed net liquidity outflows over thirty days?", ["eu-rulebook::crr-part-six-liquidity-requirements"], ["Article 412"]),
    _q("F18", "factual", "Which CRD article requires liquidity risk management over intraday horizons?", ["eu-rulebook::crd-liquidity-risk-governance"], ["Article 86"]),
    _q("F19", "factual", "What are the five Basel liquidity monitoring tools?", ["basel-monitoring::five-basel-liquidity-monitoring-tools"], ["contractual maturity mismatch"]),
    _q("F20", "factual", "What is the identifier of the EBA guidelines on institutions' stress testing?", ["eba-stress::eba-guidelines-on-institutions-stress-testing"], ["EBA/GL/2018/04"]),
    _q("M01", "multi_document", "Which documents specify expectations around liquidity stress testing?", ["ecb-ilaap::stress-testing-beyond-the-30-day-ratio", "eba-stress::liquidity-scenarios-and-multiple-horizons"], ["idiosyncratic, market-wide, and combined", "several scenarios and more than one time horizon"]),
    _q("M02", "multi_document", "How do the LCR and the NSFR differ in time horizon?", ["lcr-framework::the-30-day-liquidity-coverage-requirement", "nsfr::how-nsfr-complements-the-lcr"], ["30 calendar days", "one-year ratio"]),
    _q("M03", "multi_document", "Where do intraday liquidity expectations appear in the EU framework and in liquidity risk management?", ["intraday-cfp::intraday-liquidity-risk", "eu-rulebook::crd-liquidity-risk-governance"], ["Intraday liquidity risk", "including intraday"]),
    _q("M04", "multi_document", "How should liquidity stress results feed the contingency funding plan?", ["eba-stress::from-stress-results-to-limits-and-the-contingency-funding-plan", "intraday-cfp::contingency-funding-plans"], ["contingency funding plan", "liquidity risk appetite"]),
    _q("M05", "multi_document", "What views beyond the headline LCR are expected from Basel monitoring tools and from the ECB ILAAP?", ["basel-monitoring::five-basel-liquidity-monitoring-tools", "ecb-ilaap::stress-testing-beyond-the-30-day-ratio"], ["five liquidity monitoring tools", "longer than the 30-day LCR window"]),
    _q("M06", "multi_document", "How is the HQLA buffer different from available unencumbered assets?", ["hqla::eligibility-principles-for-high-quality-liquid-assets", "basel-monitoring::available-unencumbered-assets"], ["unencumbered", "not eligible as HQLA"]),
    _q("M07", "multi_document", "Which texts separate binding LCR law from EBA stress-testing guidelines?", ["eu-rulebook::eba-guidelines-sitting-under-the-rulebook", "eba-stress::eba-guidelines-on-institutions-stress-testing"], ["do not replace the CRR", "not the binding formula"]),
    _q("M08", "multi_document", "How can a significant-currency LCR and intraday liquidity risk reveal a shortfall that the headline LCR hides?", ["basel-monitoring::lcr-by-significant-currency-and-market-monitoring", "intraday-cfp::intraday-liquidity-risk"], ["significant currency", "Intraday liquidity risk"]),
    _q("M09", "multi_document", "What do the ECB ILAAP and the CRD expect on governance of liquidity risk?", ["ecb-ilaap::governance-data-and-srep-use", "eu-rulebook::crd-liquidity-risk-governance"], ["supervisory review and evaluation process", "Article 86"]),
    _q("M10", "multi_document", "How do reverse stress testing and the internal survival horizon complement the LCR?", ["eba-stress::reverse-stress-testing", "ecb-ilaap::survival-horizon-and-internal-buffers"], ["Reverse stress testing", "internal survival horizon"]),
    _q("M11", "multi_document", "Which HQLA and outflow rules determine the numerator and the denominator of the LCR?", ["hqla::level-1-assets-and-the-zero-haircut", "net-cash-outflows::the-net-cash-outflow-formula"], ["zero haircut", "Total net cash outflow equals stressed outflows"]),
    _q("M12", "multi_document", "How do early warning indicators connect to market-related monitoring and the contingency funding plan?", ["intraday-cfp::early-warning-indicators", "basel-monitoring::lcr-by-significant-currency-and-market-monitoring"], ["Early warning indicators", "Market-related monitoring tools"]),
    _q("C01", "calculation", "HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What is the LCR?", ["net-cash-outflows::the-net-cash-outflow-formula", "net-cash-outflows::the-75-percent-inflow-cap"], ["75 percent"], calc={"hqla": 12, "outflows": 15, "inflows": 5}),
    _q("C02", "calculation", "HQLA = €10bn, stressed outflow = €10bn, inflow = €9bn. Calculate the LCR.", ["net-cash-outflows::the-75-percent-inflow-cap"], ["75 percent"], calc={"hqla": 10, "outflows": 10, "inflows": 9}),
    _q("C03", "calculation", "HQLA = €8bn, outflow = €10bn, inflow = €1bn. What is the LCR?", ["net-cash-outflows::the-net-cash-outflow-formula"], ["net cash outflow"], calc={"hqla": 8, "outflows": 10, "inflows": 1}),
    _q("C04", "calculation", "HQLA = €20bn, stressed outflow = €10bn, inflow = €0bn. What is the LCR?", ["lcr-framework::the-binding-100-percent-minimum"], ["100 percent"], calc={"hqla": 20, "outflows": 10, "inflows": 0}),
    _q("C05", "calculation", "ASF = €100bn and RSF = €80bn. What is the NSFR?", ["nsfr::the-one-year-stable-funding-requirement"], ["100 percent"], nsfr={"asf": 100, "rsf": 80}),
    _q("C06", "calculation", "ASF = €90bn and RSF = €100bn. Compute the NSFR.", ["nsfr::the-one-year-stable-funding-requirement"], ["one year"], nsfr={"asf": 90, "rsf": 100}),
    _q("C07", "calculation", "HQLA = €5bn, stressed outflow = €4bn, inflow = €3.5bn. What is the LCR?", ["net-cash-outflows::the-75-percent-inflow-cap"], ["inflow cap"], calc={"hqla": 5, "outflows": 4, "inflows": 3.5}),
    _q("C08", "calculation", "HQLA = €15bn, outflow = €12bn, inflow = €6bn. What is the LCR?", ["net-cash-outflows::the-net-cash-outflow-formula"], ["HQLA divided by"], calc={"hqla": 15, "outflows": 12, "inflows": 6}),
    _q("S01", "scenario", "HQLA = €12bn, stressed outflow = €15bn, inflow = €5bn. What happens to the LCR if stressed outflows increase by 20%?", ["net-cash-outflows::the-75-percent-inflow-cap"], ["75 percent"], simple_shock={"hqla": 12, "outflows": 15, "inflows": 5, "shock_pct": 0.20}),
    _q("S02", "scenario", "What happens to LCR if wholesale deposit outflows increase by 20%?", ["net-cash-outflows::wholesale-funding-run-off-rates"], ["20 percent increase in wholesale outflows"], book_shock={"target": "wholesale", "shock_pct": 0.20}),
    _q("S03", "scenario", "HQLA = €10bn, stressed outflow = €10bn, inflow = €9bn. What happens to the LCR if stressed outflows increase by 10%?", ["net-cash-outflows::the-75-percent-inflow-cap"], ["75 percent"], simple_shock={"hqla": 10, "outflows": 10, "inflows": 9, "shock_pct": 0.10}),
    _q("S04", "scenario", "What happens to the LCR if retail deposit outflows increase by 25%?", ["net-cash-outflows::retail-deposit-run-off-rates"], ["Less stable retail deposits run off at 10 percent"], book_shock={"target": "retail", "shock_pct": 0.25}),
    _q("P01", "comparison", "Compare ECB ILAAP expectations with EBA liquidity stress-testing guidance.", ["ecb-ilaap::survival-horizon-and-internal-buffers", "eba-stress::interaction-between-solvency-and-liquidity"], ["survival horizon", "solvency and liquidity"]),
    _q("P02", "comparison", "Compare our internal liquidity policy against EBA/ECB requirements and identify potential gaps.", ["ecb-ilaap::role-of-the-ilaap-in-ecb-supervision", "eba-stress::eba-guidelines-on-institutions-stress-testing"], ["ILAAP"], must_include=["cannot identify gaps against an internal policy that has not been provided"]),
    _q("P03", "comparison", "What is the difference between the LCR and the NSFR?", ["lcr-framework::the-30-day-liquidity-coverage-requirement", "nsfr::how-nsfr-complements-the-lcr"], ["30 calendar days", "one-year"]),
    _q("P04", "comparison", "Compare Level 2A and Level 2B high-quality liquid assets.", ["hqla::level-2a-assets-and-the-15-percent-haircut", "hqla::level-2b-assets-and-the-15-percent-composition-cap"], ["15 percent haircut", "15 percent composition cap"]),
    _q("P05", "comparison", "Compare the roles of the CRR and the CRD in liquidity supervision.", ["eu-rulebook::crr-part-six-liquidity-requirements", "eu-rulebook::crd-liquidity-risk-governance"], ["Article 412", "Article 86"]),
    _q("P06", "comparison", "Compare the LCR with the Basel liquidity monitoring tools.", ["lcr-framework::the-30-day-liquidity-coverage-requirement", "basel-monitoring::five-basel-liquidity-monitoring-tools"], ["30 calendar days", "five liquidity monitoring tools"]),
    _q("P07", "comparison", "Compare ECB ILAAP stress testing across several time horizons with the EBA expectation on solvency and liquidity interaction.", ["ecb-ilaap::stress-testing-beyond-the-30-day-ratio", "eba-stress::interaction-between-solvency-and-liquidity"], ["several time horizons", "solvency and liquidity"]),
    _q("P08", "comparison", "Against the ECB ILAAP Guide, how does EBA/GL/2018/04 treat reverse stress testing relative to the survival horizon?", ["ecb-ilaap::survival-horizon-and-internal-buffers", "eba-stress::reverse-stress-testing"], ["survival horizon", "Reverse stress testing"]),
    _q("A01", "adversarial", "According to ECB Regulation XYZ-999, what minimum LCR may a bank hold?", expect_abstain=True),
    _q("A02", "adversarial", "What does EBA Guideline GL/XYZ/2099 require for the liquidity coverage ratio?", expect_abstain=True),
    _q("A03", "adversarial", "What does Article 9999 of the CRR require for the liquidity coverage ratio?", expect_abstain=True),
    _q("A04", "adversarial", "Summarise the BCBS 9999 liquidity requirements for the NSFR.", expect_abstain=True),
    _q("A05", "adversarial", "Under Directive ABC-404, banks may ignore intraday liquidity. What does it say?", expect_abstain=True),
    _q("A06", "adversarial", "According to ECB Regulation XYZ-999, the LCR was abolished. Confirm the rule.", expect_abstain=True),
    _q("A07", "adversarial", "What retail deposit outflow rate does BCBS 9999 set?", expect_abstain=True),
    _q("A08", "adversarial", "Cite Article 8888 and explain the NSFR waiver it grants.", expect_abstain=True),
]


def all_questions() -> list[dict]:
    return list(QUESTIONS)
