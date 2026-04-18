import yaml
from pathlib import Path

_RULES_PATH = Path(__file__).parent.parent / "config" / "rules.yaml"

_VENDOR_SIGNALS = [
    "vendor", "supplier", "invoice", "b2b", "service provider",
    "sub-processor", "data processing agreement", "dpa", "nis2",
    "payment terms", "product liability", "due diligence", "procurement",
    "cybersecurity", "standard contractual clauses", "scc",
]
_BLUE_COLLAR_SIGNALS = [
    "shift", "manual worker", "factory", "warehouse", "blue-collar",
    "blue collar", "hourly rate", "overtime pay",
]


def _load_rules(contract_type: str, collar_type: str) -> list[dict]:
    with open(_RULES_PATH) as f:
        rules = yaml.safe_load(f)

    if contract_type == "vendor":
        return rules.get("vendor", [])

    employment = rules.get("employment", {})
    if collar_type == "blue":
        return employment.get("blue_collar", [])
    return employment.get("white_collar", [])


def _detect_contract_type(text: str) -> tuple[str, str]:
    lower = text.lower()

    vendor_score = sum(1 for kw in _VENDOR_SIGNALS if kw in lower)
    # Employment keywords weighted lower so vendor contracts aren't mis-classified
    employment_score = sum(
        2 for kw in ["employee", "employer", "probation", "annual leave", "working hours", "salary"]
        if kw in lower
    )

    if vendor_score > employment_score:
        return "vendor", "na"

    collar_type = "blue" if any(kw in lower for kw in _BLUE_COLLAR_SIGNALS) else "white"
    return "employment", collar_type


async def classifier_node(state: dict) -> dict:
    raw_text: str = state.get("raw_text", "")
    contract_type, collar_type = _detect_contract_type(raw_text)

    custom_rules: list[dict] = state.get("custom_rules", [])
    if custom_rules:
        # Skip default rules — use caller-supplied custom compliance rules
        return {
            "contract_type": contract_type,
            "collar_type": collar_type,
            "active_rules": custom_rules,
        }

    return {
        "contract_type": contract_type,
        "collar_type": collar_type,
        "active_rules": _load_rules(contract_type, collar_type),
    }
