_EXCLUDED_STATUSES = {"NOT_APPLICABLE", "ERROR"}

_STATUS_WEIGHTS = {
    "PASS": 1.0,
    "WARNING": 0.5,
    "UNCERTAIN": 0.75,
    "FAIL": 0.0,
}

_RISK_BANDS = [
    (80, "Low"),
    (60, "Medium"),
    (40, "High"),
    (0, "Critical"),
]


async def scorer_node(state: dict) -> dict:
    rule_results: list[dict] = state.get("rule_results", [])
    active_rules: list[dict] = state.get("active_rules", [])

    weight_map = {r["id"]: r.get("weight", 1.0) for r in active_rules}

    total_weight = 0.0
    weighted_score = 0.0

    for result in rule_results:
        status = result.get("status", "")

        if status in _EXCLUDED_STATUSES:
            continue

        w = weight_map.get(result["rule_id"], 1.0)

        fp_risk = result.get("evaluation", {}).get("false_positive_risk", "")
        if fp_risk == "high":
            w *= 0.5

        s = _STATUS_WEIGHTS.get(status, 0.0)
        weighted_score += w * s
        total_weight += w

    overall_score = round((weighted_score / total_weight) * 100, 1) if total_weight else 0.0

    risk_level = "Critical"
    for threshold, label in _RISK_BANDS:
        if overall_score >= threshold:
            risk_level = label
            break

    return {"overall_score": overall_score, "risk_level": risk_level}
