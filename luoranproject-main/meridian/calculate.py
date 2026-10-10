"""Deterministic liquidity metrics.

The language model is not allowed to do this arithmetic. Both the researcher
and the risk reviewer call these functions.
"""

from __future__ import annotations

from copy import deepcopy

INFLOW_CAP = 0.75

DEMO_BOOK = {
    "hqla": 12.0,
    "retail_stable": 20.0,
    "retail_stable_rate": 0.05,
    "retail_less_stable": 8.0,
    "retail_less_stable_rate": 0.10,
    "wholesale_operational": 6.0,
    "wholesale_operational_rate": 0.25,
    "wholesale_non_operational": 4.0,
    "wholesale_non_operational_rate": 1.0,
    "other_outflows": 1.5,
    "inflows": 5.0,
}

COMPONENT_LINES = (
    ("retail_stable", "retail_stable_rate", "Stable retail deposits"),
    ("retail_less_stable", "retail_less_stable_rate", "Less stable retail deposits"),
    ("wholesale_operational", "wholesale_operational_rate", "Operational wholesale deposits"),
    ("wholesale_non_operational", "wholesale_non_operational_rate", "Non-operational wholesale funding"),
)

SHOCK_TARGETS = {
    "wholesale": ("wholesale_operational", "wholesale_non_operational"),
    "wholesale_operational": ("wholesale_operational",),
    "wholesale_non_operational": ("wholesale_non_operational",),
    "retail": ("retail_stable", "retail_less_stable"),
    "all": (
        "retail_stable",
        "retail_less_stable",
        "wholesale_operational",
        "wholesale_non_operational",
        "other_outflows",
    ),
}


def one_decimal(value: float) -> float:
    return round(float(value) + 1e-10, 1)


def money(value: float) -> str:
    return f"€{value:.2f}bn"


def net_cash_outflow(outflows: float, inflows: float, inflow_cap: float = INFLOW_CAP) -> dict:
    if outflows < 0 or inflows < 0:
        raise ValueError("Outflows and inflows cannot be negative.")
    cap_amount = inflow_cap * outflows
    recognised = min(inflows, cap_amount)
    net = outflows - recognised
    return {
        "outflows": outflows,
        "inflows": inflows,
        "inflow_cap_ratio": inflow_cap,
        "inflow_cap_amount": cap_amount,
        "inflows_recognised": recognised,
        "inflows_excluded": inflows - recognised,
        "net_cash_outflow": net,
    }


def liquidity_coverage_ratio(
    hqla: float,
    outflows: float,
    inflows: float,
    inflow_cap: float = INFLOW_CAP,
) -> dict:
    if hqla < 0:
        raise ValueError("HQLA cannot be negative.")
    flows = net_cash_outflow(outflows, inflows, inflow_cap)
    net = flows["net_cash_outflow"]
    ratio = None if net <= 0 else hqla / net
    pct = None if ratio is None else one_decimal(ratio * 100)
    return {
        **flows,
        "hqla": hqla,
        "lcr": ratio,
        "lcr_pct": pct,
        "meets_minimum": None if ratio is None else ratio + 1e-12 >= 1.0,
    }


def net_stable_funding_ratio(asf: float, rsf: float) -> dict:
    if asf < 0 or rsf < 0:
        raise ValueError("ASF and RSF cannot be negative.")
    ratio = None if rsf <= 0 else asf / rsf
    pct = None if ratio is None else one_decimal(ratio * 100)
    return {
        "asf": asf,
        "rsf": rsf,
        "nsfr": ratio,
        "nsfr_pct": pct,
        "meets_minimum": None if ratio is None else ratio + 1e-12 >= 1.0,
    }


def _line_outflows(book: dict) -> list[dict]:
    rows = []
    for stock_key, rate_key, label in COMPONENT_LINES:
        stock = float(book[stock_key])
        rate = float(book[rate_key])
        rows.append(
            {
                "id": stock_key,
                "label": label,
                "stock": stock,
                "rate": rate,
                "outflow": stock * rate,
            }
        )
    rows.append(
        {
            "id": "other_outflows",
            "label": "Other outflows",
            "stock": None,
            "rate": None,
            "outflow": float(book["other_outflows"]),
        }
    )
    return rows


def lcr_from_book(book: dict) -> dict:
    rows = _line_outflows(book)
    outflows = sum(row["outflow"] for row in rows)
    result = liquidity_coverage_ratio(float(book["hqla"]), outflows, float(book["inflows"]))
    result["lines"] = rows
    return result


def apply_outflow_shock(book: dict, target: str, shock_pct: float) -> dict:
    if target not in SHOCK_TARGETS:
        raise ValueError(f"Unknown shock target '{target}'.")
    shocked = deepcopy(book)
    keys = SHOCK_TARGETS[target]
    factor = 1.0 + shock_pct
    for key in keys:
        shocked[key] = max(0.0, float(shocked[key]) * factor)
    return shocked


def scenario_on_book(book: dict, target: str, shock_pct: float) -> dict:
    base = lcr_from_book(book)
    shocked_book = apply_outflow_shock(book, target, shock_pct)
    shocked = lcr_from_book(shocked_book)
    return {
        "book": book,
        "shocked_book": shocked_book,
        "target": target,
        "shock_pct": shock_pct,
        "base": base,
        "shocked": shocked,
        "delta_lcr_pp": None
        if base["lcr_pct"] is None or shocked["lcr_pct"] is None
        else one_decimal(shocked["lcr_pct"] - base["lcr_pct"]),
    }


def minimum_sentence(result: dict, ratio_name: str = "liquidity coverage ratio") -> str:
    pct = result.get("lcr_pct", result.get("nsfr_pct"))
    if pct is None:
        return f"The {ratio_name} is undefined because the denominator is zero."
    if result["meets_minimum"]:
        return f"The result is at or above the regulatory minimum of 100 percent."
    return f"The result is below the regulatory minimum of 100 percent."


def lcr_narrative(result: dict, label: str = "On these inputs") -> list[str]:
    if result["lcr_pct"] is None:
        return [
            f"{label}, the liquidity coverage ratio is undefined because net cash outflow is zero.",
        ]
    return [
        f"{label}, the liquidity coverage ratio is {result['lcr_pct']:.1f} percent.",
        f"High-quality liquid assets are {money(result['hqla'])}.",
        f"Gross outflows are {money(result['outflows'])}.",
        (
            "Inflows recognised after the 75 percent cap are "
            f"{money(result['inflows_recognised'])}."
        ),
        f"Net cash outflow is {money(result['net_cash_outflow'])}.",
        "The liquidity coverage ratio equals high-quality liquid assets divided by net cash outflow.",
        minimum_sentence(result),
    ]


def nsfr_narrative(result: dict) -> list[str]:
    if result["nsfr_pct"] is None:
        return ["The net stable funding ratio is undefined because required stable funding is zero."]
    return [
        f"The net stable funding ratio is {result['nsfr_pct']:.1f} percent.",
        f"Available stable funding is {money(result['asf'])}.",
        f"Required stable funding is {money(result['rsf'])}.",
        "The net stable funding ratio equals available stable funding divided by required stable funding.",
        minimum_sentence(result, "net stable funding ratio"),
    ]


def scenario_narrative(result: dict, target_label: str) -> list[str]:
    base = result["base"]
    shocked = result["shocked"]
    pct = one_decimal(result["shock_pct"] * 100)
    direction = "increase" if result["shock_pct"] >= 0 else "decrease"
    lines = [
        (
            f"The scenario applies a {pct:.1f} percent {direction} to {target_label} "
            "outflow amounts. Regulatory run-off rates are held unchanged. "
            "The 75 percent inflow cap is recomputed on the shocked outflows."
        ),
        *lcr_narrative(base, "Before the shock"),
        *lcr_narrative(shocked, "After the shock"),
    ]
    if result["delta_lcr_pp"] is not None:
        lines.append(
            f"The liquidity coverage ratio changes by {result['delta_lcr_pp']:.1f} percentage points."
        )
    return lines


TARGET_LABELS = {
    "wholesale": "wholesale funding",
    "wholesale_operational": "operational wholesale deposit",
    "wholesale_non_operational": "non-operational wholesale funding",
    "retail": "retail deposit",
    "all": "all modelled",
}
