import asyncio
import re

from sentence_transformers import SentenceTransformer
from sentence_transformers import util as st_util


# ── Helpers ───────────────────────────────────────────────────────────────────

def _joined(clauses: list[dict]) -> str:
    return " ".join(c.get("text", "") for c in clauses)



def _excerpt(raw: str, keyword: str, window: int = 200) -> str:
    idx = raw.lower().find(keyword.lower())
    if idx == -1:
        return "N/A"
    start = max(0, idx - 40)
    return raw[start: start + window].strip()


# ── Employment analyzers ──────────────────────────────────────────────────────

def _check_working_time(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    # Match "52 hours/week", "52 hours per week", "52-hour week"
    per_week = re.findall(r"(\d+)[\s\-]hours?(?:\s*/\s*|\s+per\s+)week", full)
    hour_week = re.findall(r"(\d+)[\s\-]hour[s]?\s+(?:working\s+)?week", full)
    hours = sorted(set(int(h) for h in per_week + hour_week if 0 < int(h) < 120))

    if not hours:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Maximum weekly working hours not explicitly stated in the contract.",
            "excerpt": "N/A",
            "recommendation": "Explicitly cap working hours at 48 per week per Directive 2003/88/EC.",
        }

    max_h = max(hours)
    if max_h > 48:
        return {
            "status": "FAIL", "severity": "High",
            "finding": f"Contract permits up to {max_h} hours/week, exceeding the EU 48-hour cap under Directive 2003/88/EC.",
            "excerpt": _excerpt(raw, str(max_h)),
            "recommendation": "Reduce maximum to 48 hours/week or add a compliant Article 22 opt-out clause.",
        }

    return {
        "status": "PASS", "severity": "Low",
        "finding": f"Working hours of {max_h} hrs/week comply with the EU 48-hour maximum.",
        "excerpt": _excerpt(raw, str(max_h)),
        "recommendation": "No action required.",
    }


def _check_transparent_terms(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    m = re.search(r"probation\w*[^.\n]{0,40}?(\d+)\s*(month|week)", full)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        months = n if unit.startswith("month") else n / 4.3
        if months > 6:
            return {
                "status": "WARNING", "severity": "Medium",
                "finding": f"Probation period of {n} {unit}(s) exceeds the EU 6-month cap under Directive 2019/1152.",
                "excerpt": _excerpt(raw, "probation"),
                "recommendation": "Reduce probation to ≤6 months per Article 8 of Directive 2019/1152.",
            }
        return {
            "status": "PASS", "severity": "Low",
            "finding": f"Probation of {n} {unit}(s) is within the EU 6-month limit.",
            "excerpt": _excerpt(raw, "probation"),
            "recommendation": "No action required.",
        }

    if "probation" in full:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Probation period is mentioned but duration is not clearly stated.",
            "excerpt": _excerpt(raw, "probation"),
            "recommendation": "State duration explicitly; it must not exceed 6 months per Directive 2019/1152.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "Required transparent terms (probation period, working schedule) are not clearly specified.",
        "excerpt": "N/A",
        "recommendation": "Include all required terms per Article 4 of Directive 2019/1152.",
    }


def _check_gdpr_employee(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    strong = [
        "lawful basis", "legitimate interest", "data subject rights",
        "right to erasure", "data minimisation", "data minimization",
        "retention period", "sub-processor", "data subject",
    ]
    weak = ["gdpr", "personal data", "data protection", "process", "privacy"]

    strong_hits = [k for k in strong if k in full]
    weak_hits = [k for k in weak if k in full]

    if len(strong_hits) >= 2:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "GDPR clauses are present including lawful basis, data subject rights, and processing controls.",
            "excerpt": _excerpt(raw, strong_hits[0]),
            "recommendation": "No action required.",
        }

    if strong_hits or len(weak_hits) >= 2:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Data protection clause is present but incomplete — lawful basis, retention limits, and data subject rights are not fully addressed.",
            "excerpt": _excerpt(raw, (strong_hits + weak_hits)[0]),
            "recommendation": "Expand the clause to cover lawful basis, retention period, and data subject rights per GDPR Article 13.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No adequate GDPR clause found. Contract lacks lawful basis, retention limits, and data subject rights.",
        "excerpt": "N/A",
        "recommendation": "Add a complete GDPR Article 13 disclosure covering lawful basis, retention period, and employee rights.",
    }


def _check_equal_treatment(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    keywords = [
        "discriminat", "equal treatment", "religion", "disability",
        "sexual orientation", "race", "gender", "protected characteristic",
    ]
    hits = [k for k in keywords if k in full]

    if len(hits) >= 3:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Non-discrimination clause covers the required protected characteristics.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "No action required.",
        }

    if hits:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Partial non-discrimination language present but does not cover all protected characteristics under Directive 2000/78/EC.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "Expand to explicitly cover religion, disability, age, and sexual orientation per Directive 2000/78/EC.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No non-discrimination clause found. The contract must prohibit discrimination on all grounds in Directive 2000/78/EC.",
        "excerpt": "N/A",
        "recommendation": "Add a non-discrimination clause covering religion, disability, age, and sexual orientation.",
    }


def _check_minimum_wage(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    annual = re.findall(r"€\s*([\d,]+)\s*(?:annually|per year|p\.a\.)", full)
    monthly = re.findall(r"€\s*([\d,]+)\s*(?:per month|monthly|/month)", full)

    if annual:
        amt = int(annual[0].replace(",", ""))
        if amt < 15_000:
            return {
                "status": "FAIL", "severity": "High",
                "finding": f"Annual salary of €{amt:,} appears below EU minimum wage thresholds.",
                "excerpt": _excerpt(raw, "annually"),
                "recommendation": "Verify salary meets the applicable national minimum wage per Directive 2022/2041.",
            }
        return {
            "status": "PASS", "severity": "Low",
            "finding": f"Annual salary of €{amt:,} is above EU minimum wage thresholds.",
            "excerpt": _excerpt(raw, "annually"),
            "recommendation": "No action required.",
        }

    if monthly:
        amt = int(monthly[0].replace(",", ""))
        annual_equiv = amt * 12
        status = "PASS" if annual_equiv >= 15_000 else "WARNING"
        return {
            "status": status, "severity": "Low" if status == "PASS" else "Medium",
            "finding": f"Monthly salary of €{amt:,} (≈€{annual_equiv:,}/year) {'is above' if status == 'PASS' else 'should be verified against'} EU minimum wage thresholds.",
            "excerpt": _excerpt(raw, "month"),
            "recommendation": "No action required." if status == "PASS" else "Verify against applicable national minimum wage per Directive 2022/2041.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "Salary amount not detected. Cannot verify minimum wage compliance.",
        "excerpt": "N/A",
        "recommendation": "Clearly state the salary and verify it meets the national minimum wage per Directive 2022/2041.",
    }


def _check_termination_notice(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    m = re.search(r"notice\s+period[^.\n]{0,40}?(\d+)\s*(week|month)", full)
    if not m:
        m = re.search(r"(\d+)\s*(week|month)[^.\n]{0,40}?notice", full)

    if m:
        n, unit = int(m.group(1)), m.group(2)
        weeks = n if unit.startswith("week") else n * 4

        if weeks < 4:
            return {
                "status": "FAIL", "severity": "High",
                "finding": f"Notice period of {n} {unit}(s) is very short and may not satisfy collective redundancy obligations.",
                "excerpt": _excerpt(raw, "notice"),
                "recommendation": "Review notice period against national law implementing Directive 98/59/EC.",
            }
        if weeks <= 6:
            return {
                "status": "WARNING", "severity": "Medium",
                "finding": f"Notice period of {n} {unit}(s) is short. Verify it meets national requirements for the employee's seniority and tenure.",
                "excerpt": _excerpt(raw, "notice"),
                "recommendation": "Consider longer notice for senior or longer-serving employees per Directive 98/59/EC.",
            }
        return {
            "status": "PASS", "severity": "Low",
            "finding": f"Notice period of {n} {unit}(s) appears compliant.",
            "excerpt": _excerpt(raw, "notice"),
            "recommendation": "No action required.",
        }

    if "terminat" in full or "notice" in full:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Termination clause present but notice period duration not clearly specified.",
            "excerpt": _excerpt(raw, "notice") or _excerpt(raw, "terminat"),
            "recommendation": "Specify notice period explicitly to comply with Directive 98/59/EC.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No termination or notice period clause found.",
        "excerpt": "N/A",
        "recommendation": "Add a termination clause with explicit notice periods per Directive 98/59/EC.",
    }


# ── Vendor analyzers ──────────────────────────────────────────────────────────

def _check_late_payment(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    matches = re.findall(r"(\d+)\s*days?\s*(?:net|payment|payable|after)", full)
    if not matches:
        matches = re.findall(r"(?:within|payable in)\s*(\d+)\s*days?", full)

    days = [int(d) for d in matches if 0 < int(d) < 365]
    if not days:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Payment terms not clearly stated.",
            "excerpt": "N/A",
            "recommendation": "Specify payment terms. Commercial transactions must be ≤60 days per Directive 2011/7/EU.",
        }

    max_d = max(days)
    if max_d > 60:
        return {
            "status": "FAIL", "severity": "High",
            "finding": f"Payment terms of {max_d} days exceed the 60-day commercial maximum under Directive 2011/7/EU.",
            "excerpt": _excerpt(raw, f"{max_d} day"),
            "recommendation": "Reduce to ≤60 days (commercial) or ≤30 days (public sector) per Directive 2011/7/EU.",
        }

    return {
        "status": "PASS", "severity": "Low",
        "finding": f"Payment terms of {max_d} days comply with Directive 2011/7/EU (≤60 days for commercial transactions).",
        "excerpt": _excerpt(raw, "days"),
        "recommendation": "No action required.",
    }


def _check_gdpr_vendor(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    strong = [
        "data processing agreement", "dpa", "standard contractual clause", "scc",
        "sub-processor", "data minimisation", "data minimization",
        "purpose limitation", "data subject",
    ]
    weak = ["gdpr", "personal data", "data protection", "privacy"]

    strong_hits = [k for k in strong if k in full]
    weak_hits = [k for k in weak if k in full]

    if len(strong_hits) >= 3:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Comprehensive DPA clauses present including sub-processor controls, SCCs, and purpose limitation.",
            "excerpt": _excerpt(raw, strong_hits[0]),
            "recommendation": "No action required.",
        }

    if strong_hits or len(weak_hits) >= 2:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Partial GDPR/DPA language present but may not cover all GDPR Article 28 requirements.",
            "excerpt": _excerpt(raw, (strong_hits + weak_hits)[0]),
            "recommendation": "Ensure DPA covers sub-processor controls, SCCs, data subject rights, and incident notification per GDPR Article 28.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No Data Processing Agreement (DPA) clause found. GDPR Article 28 requires one for all data processors.",
        "excerpt": "N/A",
        "recommendation": "Add a full DPA covering lawful basis, sub-processors, SCCs, and data subject rights.",
    }


def _check_nis2(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    has_72hr = "72 hour" in full or "72-hour" in full
    has_cyber = any(k in full for k in [
        "cybersecurity", "cyber security", "nis2",
        "security incident", "technical and organizational", "technical and organisational",
    ])

    if has_72hr and has_cyber:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "NIS2-aligned cybersecurity obligations and 72-hour incident reporting timeline are present.",
            "excerpt": _excerpt(raw, "72 hour") or _excerpt(raw, "security incident"),
            "recommendation": "No action required.",
        }

    if has_cyber:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Cybersecurity obligations referenced but the mandatory 72-hour incident reporting timeline is not explicitly stated.",
            "excerpt": _excerpt(raw, "cybersecurity") or _excerpt(raw, "security"),
            "recommendation": "Explicitly include the 72-hour initial incident reporting requirement per NIS2 Article 23.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No cybersecurity obligations or incident reporting requirements found, as mandated by NIS2 Directive (EU 2022/2555).",
        "excerpt": "N/A",
        "recommendation": "Add cybersecurity obligations and 72-hour incident reporting clause per NIS2 Article 23.",
    }


def _check_product_liability(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    has_cap = "liability" in full and bool(re.search(r"cap(?:ped)?|limit(?:ed)?|maximum", full))
    has_exclusion = any(k in full for k in ["willful misconduct", "gross negligence", "fraud"])
    has_defect = "defect" in full

    if has_cap and has_exclusion and has_defect:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Liability cap, misconduct exclusions, and defect definitions are all present.",
            "excerpt": _excerpt(raw, "liability"),
            "recommendation": "No action required.",
        }

    if has_cap and has_exclusion:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Liability cap and misconduct exclusions present, but explicit defect definitions are absent — required under the updated 2024 Product Liability Directive for digital services.",
            "excerpt": _excerpt(raw, "liability"),
            "recommendation": "Add defect definitions per Directive 85/374/EEC as updated in 2024, particularly for software deliverables.",
        }

    if has_cap:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Liability cap is present but lacks carve-outs for willful misconduct or gross negligence.",
            "excerpt": _excerpt(raw, "liability"),
            "recommendation": "Add exclusions for willful misconduct and gross negligence per Directive 85/374/EEC.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "Liability terms not clearly defined in a manner consistent with Directive 85/374/EEC.",
        "excerpt": _excerpt(raw, "liability") or "N/A",
        "recommendation": "Define liability cap, defect definitions, and carve-outs per Directive 85/374/EEC.",
    }


def _check_csddd(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    keywords = [
        "human rights", "environmental", "due diligence",
        "supply chain", "sustainability", "csddd", "corporate sustainability",
    ]
    hits = [k for k in keywords if k in full]

    if len(hits) >= 2:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Human rights and environmental due diligence commitments are present per CSDDD principles.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "No action required.",
        }

    if hits:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Partial sustainability language present but does not fully address CSDDD supply chain due diligence requirements.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "Expand clause to cover audit rights, remediation obligations, and supply chain transparency per CSDDD 2024/1760.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No supply chain due diligence or human rights/environmental clauses found.",
        "excerpt": "N/A",
        "recommendation": "Add CSDDD-compliant due diligence clauses covering human rights, environment, audit rights, and remediation per Directive 2024/1760.",
    }


# ── Employment — additional directives ───────────────────────────────────────

def _check_posted_workers(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    posting_signals = ["post", "secondment", "cross-border", "host country", "expatriate", "assignment abroad"]
    is_posting = any(k in full for k in posting_signals)

    if not is_posting:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No cross-border posting arrangement identified — Posted Workers Directive does not appear applicable.",
            "excerpt": "N/A",
            "recommendation": "If the employee may be posted abroad, add host-country conditions clause per Directive 96/71/EC.",
        }

    has_host = any(k in full for k in ["host country", "applicable law", "minimum conditions", "local law"])
    if has_host:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Cross-border posting terms include host-country minimum conditions as required by Directive 96/71/EC.",
            "excerpt": _excerpt(raw, "host country") or _excerpt(raw, "post"),
            "recommendation": "No action required.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "Cross-border posting detected but host-country minimum conditions (wage, working time, leave) are not explicitly referenced.",
        "excerpt": _excerpt(raw, "post"),
        "recommendation": "Add host-country minimum conditions clause per Directive 96/71/EC Article 3.",
    }


def _check_work_life_balance(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    has_parental = any(k in full for k in ["parental leave", "maternity leave", "paternity leave", "family leave"])
    paternity_match = re.search(r"paternt?\w*\s+leave[^.\n]{0,40}?(\d+)\s*day", full)

    if has_parental and paternity_match:
        days = int(paternity_match.group(1))
        if days >= 10:
            return {
                "status": "PASS", "severity": "Low",
                "finding": f"Paternity leave of {days} days (≥10 required) and parental leave provisions are present per Directive 2019/1158.",
                "excerpt": _excerpt(raw, "paternity"),
                "recommendation": "No action required.",
            }
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": f"Paternity leave of only {days} days found — Directive 2019/1158 requires a minimum of 10 days.",
            "excerpt": _excerpt(raw, "paternity"),
            "recommendation": "Extend paternity leave to at least 10 days and add 4-month parental leave per Directive 2019/1158.",
        }

    if has_parental:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Parental leave is mentioned but paternity leave duration and entitlements are not clearly specified.",
            "excerpt": _excerpt(raw, "parental") or _excerpt(raw, "leave"),
            "recommendation": "Specify at least 10 days paternity leave and 4 months parental leave per Directive 2019/1158.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No parental or paternity leave provisions found. Directive 2019/1158 mandates minimum leave entitlements.",
        "excerpt": "N/A",
        "recommendation": "Add: paternity leave ≥10 days, parental leave 4 months, carer's leave 5 days/year per Directive 2019/1158.",
    }


def _check_whistleblower(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    channel_signals = ["whistleblower", "whistle-blower", "internal reporting", "speak up", "reporting channel", "report misconduct", "report wrongdoing"]
    protection_signals = ["retaliation", "victimisation", "victimization", "protection from", "no reprisal"]

    channel_hits = [k for k in channel_signals if k in full]
    protection_hits = [k for k in protection_signals if k in full]

    if channel_hits and protection_hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Whistleblower reporting channel and anti-retaliation protection clause are present per Directive 2019/1937.",
            "excerpt": _excerpt(raw, channel_hits[0]),
            "recommendation": "No action required.",
        }

    if channel_hits:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Whistleblower reporting mechanism is referenced but explicit anti-retaliation protection is absent.",
            "excerpt": _excerpt(raw, channel_hits[0]),
            "recommendation": "Add explicit anti-retaliation protection per Directive 2019/1937 Article 19.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "No whistleblower protection clause found. Required for organisations with >50 employees under Directive 2019/1937.",
        "excerpt": "N/A",
        "recommendation": "Add an internal reporting channel and anti-retaliation clause per Directive 2019/1937 if the organisation employs >50 people.",
    }


def _check_race_equality(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    race_signals = ["race", "ethnic origin", "racial", "national origin", "colour", "color"]
    race_hits = [k for k in race_signals if k in full]
    has_discrimination_clause = "discriminat" in full

    if race_hits and has_discrimination_clause:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Non-discrimination clause explicitly covers race and ethnic origin per Directive 2000/43/EC.",
            "excerpt": _excerpt(raw, race_hits[0]),
            "recommendation": "No action required.",
        }

    if has_discrimination_clause:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Non-discrimination clause present but does not explicitly cover race and ethnic origin as required by Directive 2000/43/EC.",
            "excerpt": _excerpt(raw, "discriminat"),
            "recommendation": "Add race and ethnic origin to the non-discrimination clause per Directive 2000/43/EC.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "No clause covering racial or ethnic non-discrimination found, as required by Directive 2000/43/EC.",
        "excerpt": "N/A",
        "recommendation": "Add explicit non-discrimination clause covering race and ethnic origin per Directive 2000/43/EC.",
    }


def _check_fixed_term(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    is_fixed = any(k in full for k in ["fixed-term", "fixed term", "temporary contract"])
    is_permanent = any(k in full for k in ["permanent contract", "indefinite", "open-ended", "permanent employment"])

    if is_permanent and not is_fixed:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Contract is permanent / indefinite duration — Fixed-Term Work Directive protections do not apply.",
            "excerpt": _excerpt(raw, "permanent") or _excerpt(raw, "indefinite"),
            "recommendation": "No action required.",
        }

    if is_fixed:
        has_justification = any(k in full for k in ["objective reason", "justified", "project-based", "seasonal", "replacement for"])
        if has_justification:
            return {
                "status": "PASS", "severity": "Low",
                "finding": "Fixed-term contract states an objective justification as required by Directive 1999/70/EC.",
                "excerpt": _excerpt(raw, "fixed"),
                "recommendation": "Ensure successive renewals do not circumvent permanent employment obligations.",
            }
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Fixed-term contract detected but no objective justification is stated, as required by Directive 1999/70/EC to prevent abuse.",
            "excerpt": _excerpt(raw, "fixed") or _excerpt(raw, "temporary"),
            "recommendation": "State the objective reason for the fixed term (project, seasonal, replacement) per Directive 1999/70/EC.",
        }

    return {
        "status": "PASS", "severity": "Low",
        "finding": "No fixed-term provisions detected — assumed permanent employment.",
        "excerpt": "N/A",
        "recommendation": "No action required.",
    }


# ── Vendor — additional directives ────────────────────────────────────────────

def _check_ai_act(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    ai_signals = ["artificial intelligence", "ai system", "machine learning", "automated decision",
                  "algorithm", "generative ai", "large language model", "llm", "ai model"]
    ai_hits = [k for k in ai_signals if k in full]

    if not ai_hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No AI system usage detected in contract scope — EU AI Act obligations do not appear applicable.",
            "excerpt": "N/A",
            "recommendation": "If AI systems are deployed as part of this service, review EU AI Act obligations per Regulation (EU) 2024/1689.",
        }

    compliance_signals = ["transparency", "human oversight", "conformity", "risk assessment",
                          "prohibited", "high-risk", "ai act", "fundamental rights impact"]
    comp_hits = [k for k in compliance_signals if k in full]

    if len(comp_hits) >= 2:
        return {
            "status": "PASS", "severity": "Low",
            "finding": f"AI system usage ({ai_hits[0]}) is identified and EU AI Act compliance obligations are referenced.",
            "excerpt": _excerpt(raw, ai_hits[0]),
            "recommendation": "No action required.",
        }

    if comp_hits:
        return {
            "status": "WARNING", "severity": "High",
            "finding": f"AI system usage detected ({ai_hits[0]}) but EU AI Act obligations are only partially addressed.",
            "excerpt": _excerpt(raw, ai_hits[0]),
            "recommendation": "Add risk classification, transparency obligations, human oversight, and prohibited-practice prohibition per Regulation (EU) 2024/1689.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": f"AI system usage detected ({ai_hits[0]}) but no EU AI Act compliance clauses found.",
        "excerpt": _excerpt(raw, ai_hits[0]),
        "recommendation": "Add EU AI Act clauses: risk assessment, transparency disclosure, human oversight, and prohibited AI practice prohibition per Regulation (EU) 2024/1689.",
    }


def _check_cyber_resilience(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    product_signals = ["software", "hardware", "firmware", "device", "product", "digital element"]
    has_product = any(k in full for k in product_signals)

    if not has_product:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No products with digital elements detected — Cyber Resilience Act obligations do not appear applicable.",
            "excerpt": "N/A",
            "recommendation": "If the vendor supplies software or hardware products, review CRA obligations (effective 2027).",
        }

    cra_signals = ["security update", "vulnerability", "patch", "security support",
                   "end of life", "vulnerability disclosure", "cyber resilience"]
    cra_hits = [k for k in cra_signals if k in full]

    if len(cra_hits) >= 2:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Product security obligations including vulnerability handling and update lifecycle are addressed.",
            "excerpt": _excerpt(raw, cra_hits[0]),
            "recommendation": "No action required.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": "Products with digital elements detected but Cyber Resilience Act obligations (security updates, vulnerability disclosure, support period) are not addressed.",
        "excerpt": _excerpt(raw, product_signals[0]),
        "recommendation": "Add CRA obligations: security update lifecycle, vulnerability disclosure, and support period per Regulation (EU) 2024/2847.",
    }


def _check_data_act(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    data_signals = ["data sharing", "data access", "data portability", "cloud", "iot",
                    "connected device", "switching provider", "data generated"]
    data_hits = [k for k in data_signals if k in full]

    if not data_hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No data sharing, IoT, or cloud service scope detected — Data Act obligations do not appear applicable.",
            "excerpt": "N/A",
            "recommendation": "If the service involves connected devices or cloud switching, review Data Act obligations (Regulation (EU) 2023/2854).",
        }

    portability_signals = ["data portability", "switching", "interoperability", "data access right"]
    port_hits = [k for k in portability_signals if k in full]

    if port_hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Data access and portability provisions are referenced in the contract.",
            "excerpt": _excerpt(raw, port_hits[0]),
            "recommendation": "No action required.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": f"Data service scope detected ({data_hits[0]}) but data portability and switching rights are not addressed.",
        "excerpt": _excerpt(raw, data_hits[0]),
        "recommendation": "Add data portability, access rights, and cloud switching provisions per Data Act (Regulation (EU) 2023/2854).",
    }


def _check_dsa(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    platform_signals = ["platform", "intermediary service", "hosting service", "marketplace",
                        "online platform", "content moderation", "user generated"]
    hits = [k for k in platform_signals if k in full]

    if not hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No intermediary or platform services detected — Digital Services Act obligations do not appear applicable.",
            "excerpt": "N/A",
            "recommendation": "If the vendor provides online intermediary services, review DSA obligations per Regulation (EU) 2022/2065.",
        }

    dsa_signals = ["transparency", "content moderation", "illegal content",
                   "notice and action", "trusted flagger", "very large online platform"]
    dsa_hits = [k for k in dsa_signals if k in full]

    if dsa_hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Platform/intermediary service detected and DSA compliance obligations are referenced.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "No action required.",
        }

    return {
        "status": "WARNING", "severity": "Medium",
        "finding": f"Platform or intermediary service detected ({hits[0]}) but DSA obligations are not addressed.",
        "excerpt": _excerpt(raw, hits[0]),
        "recommendation": "Add DSA compliance clauses: content moderation, transparency reporting, and user rights per Regulation (EU) 2022/2065.",
    }


def _check_commercial_agents(clauses: list[dict]) -> dict:
    raw = _joined(clauses)
    full = raw.lower()

    agent_signals = ["commercial agent", "sales agent", "agency agreement", "sole agent", "exclusive agent"]
    hits = [k for k in agent_signals if k in full]

    if not hits:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "No commercial agency arrangement detected — Commercial Agents Directive does not apply.",
            "excerpt": "N/A",
            "recommendation": "No action required.",
        }

    has_commission = any(k in full for k in ["commission", "remuneration", "percentage of"])
    has_indemnity = any(k in full for k in ["indemnity", "compensation on termination", "goodwill"])

    if has_commission and has_indemnity:
        return {
            "status": "PASS", "severity": "Low",
            "finding": "Agent commission rights and termination indemnity provisions are present per Directive 86/653/EEC.",
            "excerpt": _excerpt(raw, hits[0]),
            "recommendation": "No action required.",
        }

    if has_commission:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": "Commission structure defined but termination indemnity or goodwill compensation is not specified.",
            "excerpt": _excerpt(raw, "commission"),
            "recommendation": "Add agent termination indemnity/goodwill compensation per Directive 86/653/EEC Article 17.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": "Commercial agency arrangement detected but commission rights and termination indemnity are not defined.",
        "excerpt": _excerpt(raw, hits[0]),
        "recommendation": "Define commission entitlements and termination indemnity per Directive 86/653/EEC Articles 6–12 and 17.",
    }


# ── Dispatch map ──────────────────────────────────────────────────────────────

_ANALYZERS = {
    # Employment — core
    "working_time": _check_working_time,
    "transparent_terms": _check_transparent_terms,
    "gdpr_employee": _check_gdpr_employee,
    "equal_treatment": _check_equal_treatment,
    "minimum_wage": _check_minimum_wage,
    "termination_notice": _check_termination_notice,
    # Employment — additional
    "posted_workers": _check_posted_workers,
    "work_life_balance": _check_work_life_balance,
    "whistleblower": _check_whistleblower,
    "race_equality": _check_race_equality,
    "fixed_term": _check_fixed_term,
    # Vendor — core
    "late_payment": _check_late_payment,
    "gdpr_vendor": _check_gdpr_vendor,
    "nis2": _check_nis2,
    "product_liability": _check_product_liability,
    "csddd": _check_csddd,
    # Vendor — additional
    "ai_act": _check_ai_act,
    "cyber_resilience": _check_cyber_resilience,
    "data_act": _check_data_act,
    "dsa": _check_dsa,
    "commercial_agents": _check_commercial_agents,
}


# ── Semantic similarity custom-rule checker ───────────────────────────────────

_embedding_model: SentenceTransformer | None = None


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        # Downloaded once to ~/.cache/huggingface on first use (~90 MB)
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def _check_with_embeddings(rule: dict, clauses: list[dict]) -> dict:
    """Rank contract clauses against a custom rule using semantic cosine similarity."""
    if not clauses:
        return {
            "status": "FAIL", "severity": "High",
            "finding": "No clauses could be extracted from the contract.",
            "excerpt": "N/A",
            "recommendation": "Ensure the contract file is readable and contains text.",
        }

    model = _get_embedding_model()
    rule_text = rule.get("prompt", rule.get("name", ""))
    clause_texts = [c.get("text", "") for c in clauses]

    rule_emb = model.encode(rule_text, convert_to_tensor=True, show_progress_bar=False)
    clause_embs = model.encode(clause_texts, convert_to_tensor=True, show_progress_bar=False)
    scores = st_util.cos_sim(rule_emb, clause_embs)[0]

    best_idx = int(scores.argmax())
    best_score = float(scores[best_idx])
    best_clause = clauses[best_idx]
    excerpt = best_clause.get("text", "")[:300].strip() or "N/A"
    matched_title = best_clause.get("title", best_clause.get("clause_id", ""))

    if best_score >= 0.45:
        return {
            "status": "PASS", "severity": "Low",
            "finding": (
                f"Contract addresses this requirement — best matching clause: "
                f"'{matched_title}' (similarity: {best_score:.2f})."
            ),
            "excerpt": excerpt,
            "recommendation": "No action required.",
        }

    if best_score >= 0.25:
        return {
            "status": "WARNING", "severity": "Medium",
            "finding": (
                f"Partial coverage found (similarity: {best_score:.2f}). "
                f"Closest clause: '{matched_title}'. "
                "The requirement may not be fully or explicitly addressed."
            ),
            "excerpt": excerpt,
            "recommendation": "Review the identified clause for completeness against this custom requirement.",
        }

    return {
        "status": "FAIL", "severity": "High",
        "finding": (
            f"No semantically relevant clause found for this requirement "
            f"(best similarity: {best_score:.2f}). "
            "The contract does not appear to address this rule."
        ),
        "excerpt": "N/A",
        "recommendation": "Add explicit contractual provisions addressing this custom compliance requirement.",
    }


class MockOpenAIService:
    """Analyses actual clause text with regex heuristics — no Azure OpenAI calls yet."""

    async def check_rule(self, rule: dict, clauses: list[dict]) -> dict:
        await asyncio.sleep(0.4)

        if rule.get("_custom"):
            result = _check_with_embeddings(rule, clauses)
        else:
            analyzer = _ANALYZERS.get(rule["id"])
            result = analyzer(clauses) if analyzer else {
                "status": "PASS", "severity": "Low",
                "finding": "No issues detected.",
                "excerpt": "N/A",
                "recommendation": "No action required.",
            }

        return {"rule_id": rule["id"], "rule_name": rule["name"], "directive": rule["directive"], **result}
