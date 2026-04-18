async def report_writer_node(state: dict) -> dict:
    """Synthesises an executive summary from all rule results (mock implementation)."""
    rule_results: list[dict] = state.get("rule_results", [])
    overall_score: float = state.get("overall_score", 0.0)
    risk_level: str = state.get("risk_level", "Unknown")

    failed = [r for r in rule_results if r["status"] == "FAIL"]
    warned = [r for r in rule_results if r["status"] == "WARNING"]
    passed = [r for r in rule_results if r["status"] == "PASS"]

    summary_lines = [
        f"Compliance score: {overall_score}/100 — {risk_level} Risk.",
        f"{len(failed)} failure(s), {len(warned)} warning(s), {len(passed)} pass(es) across {len(rule_results)} rules checked.",
    ]

    if failed:
        directives = ", ".join(r["directive"] for r in failed)
        summary_lines.append(f"Critical issues found under: {directives}.")

    # ── Judge evaluation summary ──────────────────────────────────────────────
    evals = [r["evaluation"] for r in rule_results if "evaluation" in r]
    judge_summary: dict = {}
    if evals:
        judge_summary = {
            "avg_accuracy_score": round(sum(e["accuracy_score"] for e in evals) / len(evals), 3),
            "avg_completeness_score": round(sum(e["completeness_score"] for e in evals) / len(evals), 3),
            "high_fp_risk_rules": [
                r["rule_id"] for r in rule_results
                if r.get("evaluation", {}).get("false_positive_risk") == "high"
            ],
            "miscalibrated_severity_rules": [
                r["rule_id"] for r in rule_results
                if r.get("evaluation", {}).get("severity_calibration") == "miscalibrated"
            ],
        }

    report = {
        "executive_summary": " ".join(summary_lines),
        "overall_score": overall_score,
        "risk_level": risk_level,
        "detailed_findings": rule_results,
        "recommendations": [
            {"rule_id": r["rule_id"], "recommendation": r["recommendation"]}
            for r in rule_results
            if r["status"] != "PASS"
        ],
        "judge_evaluation_summary": judge_summary,
    }

    return {"report": report}
