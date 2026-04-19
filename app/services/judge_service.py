import asyncio


def _evaluate_sync(rule: dict, finding: dict) -> dict:
    """
    Validates rule-checker output quality using deterministic heuristics.
    Mirrors what a real LLM judge prompt would score:
      - accuracy:     is the finding grounded in evidence?
      - completeness: does it cite specific articles/directives?
      - severity_calibration: does severity match status?
      - false_positive_risk: how likely is this a hallucinated finding?
    """
    excerpt = finding.get("excerpt", "N/A")
    status = finding.get("status", "PASS")
    severity = finding.get("severity", "Low")
    finding_text = finding.get("finding", "")
    recommendation = finding.get("recommendation", "")
    combined = (finding_text + " " + recommendation).lower()

    # ── Evidence quality ──────────────────────────────────────────────────────
    has_evidence = excerpt != "N/A" and len(excerpt.strip()) > 20
    # PASS with no excerpt is fine — nothing to quote
    evidence_score = 0.92 if has_evidence else (0.80 if status == "PASS" else 0.30)

    # ── Severity calibration ──────────────────────────────────────────────────
    expected = {"FAIL": {"High", "Critical"}, "WARNING": {"Medium"}, "PASS": {"Low"}}
    severity_ok = severity in expected.get(status, {"Low"})
    severity_calibration = "correct" if severity_ok else "miscalibrated"

    # ── Completeness — directive/article citations ─────────────────────────────
    citation_terms = ["article", "art.", "directive", "regulation", "eu 20", "ec", "§"]
    has_citation = any(t in combined for t in citation_terms)
    completeness_score = round(
        (0.92 if has_citation else 0.55) * (0.97 if has_evidence or status == "PASS" else 0.80),
        2,
    )

    # ── Overall accuracy ──────────────────────────────────────────────────────
    accuracy_score = round(
        evidence_score * (1.0 if severity_ok else 0.78),
        2,
    )

    # ── False-positive risk ───────────────────────────────────────────────────
    if status == "PASS":
        fp_risk = "low"
    elif has_evidence and severity_ok:
        fp_risk = "low"
    elif has_evidence or severity_ok:
        fp_risk = "medium"
    else:
        fp_risk = "high"  # FAIL/WARNING with no excerpt and miscalibrated severity

    # ── Judge notes ───────────────────────────────────────────────────────────
    notes: list[str] = []
    if not has_evidence and status != "PASS":
        notes.append("No supporting excerpt — verify finding against source document.")
    if not severity_ok:
        notes.append(f"Severity '{severity}' does not match expected range for '{status}'.")
    if not has_citation:
        notes.append("Finding lacks specific article or directive references.")
    if not notes:
        notes.append("Finding is well-supported with evidence and directive citations.")

    return {
        "accuracy_score": accuracy_score,
        "completeness_score": completeness_score,
        "severity_calibration": severity_calibration,
        "false_positive_risk": fp_risk,
        "judge_note": " ".join(notes),
    }


class MockJudgeService:
    """
    Simulates an LLM-as-a-judge evaluation.

    Real implementation: replace _evaluate_sync with a GPT-4o call using a
    judge system prompt that receives the directive requirements, the clause
    text, and the rule-checker's finding, then returns structured JSON scores.
    """

    async def evaluate(self, rule: dict, clauses: list[dict], finding: dict) -> dict:
        await asyncio.sleep(0.05)  # Much faster than rule-check — lightweight validation
        return _evaluate_sync(rule, finding)
