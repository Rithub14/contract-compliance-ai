"""Smoke tests — verify core modules import and basic logic works without API calls."""
import sys
import types


def _mock_heavy(name: str) -> None:
    """Stub out a module so imports don't fail in CI without the real package."""
    sys.modules.setdefault(name, types.ModuleType(name))


# Stub platform-specific / heavy deps not available in CI
for _mod in ("fitz", "pypdfium2", "ocrmac", "ocrmac.ocrmac", "rapidocr", "PIL", "PIL.Image",
             "fastembed", "numpy"):
    _mock_heavy(_mod)

sys.modules["fastembed"].TextEmbedding = type("TextEmbedding", (), {})
sys.modules["numpy"].ndarray = type("ndarray", (), {})
sys.modules["numpy"].frombuffer = staticmethod(lambda *a, **kw: None)


def test_settings_loads():
    from app.config.settings import settings
    assert hasattr(settings, "openai_api_key")
    assert hasattr(settings, "openai_model")


def test_rules_yaml_loads():
    import yaml
    from pathlib import Path
    rules_path = Path("app/config/rules.yaml")
    assert rules_path.exists()
    data = yaml.safe_load(rules_path.read_text())
    assert "employment" in data
    assert "vendor" in data


def test_employment_rules_have_required_fields():
    import yaml
    from pathlib import Path
    data = yaml.safe_load(Path("app/config/rules.yaml").read_text())
    for rule in data["employment"]["white_collar"]:
        assert "id" in rule
        assert "name" in rule
        assert "directive" in rule
        assert "category" in rule
        assert "prompt" in rule


def test_vendor_rules_have_required_fields():
    import yaml
    from pathlib import Path
    data = yaml.safe_load(Path("app/config/rules.yaml").read_text())
    for rule in data["vendor"]:
        assert "id" in rule
        assert "category" in rule


def test_classifier_detects_employment():
    from app.agents.classifier import _detect_contract_type
    contract_type, collar_type = _detect_contract_type(
        "This employment contract sets out the salary and working hours for the employee."
    )
    assert contract_type == "employment"


def test_classifier_detects_vendor():
    from app.agents.classifier import _detect_contract_type
    contract_type, _ = _detect_contract_type(
        "This vendor agreement covers invoice payment terms and data processing agreement."
    )
    assert contract_type == "vendor"


def test_enforce_evidence_rule_downgrades_fail():
    from app.agents.rule_checker import _enforce_evidence_rule
    result = {
        "status": "FAIL",
        "severity": "High",
        "finding": "Salary below minimum wage.",
        "excerpt": "N/A",
        "justification_type": "none",
    }
    rule = {"category": "MUST_BE_EXPLICIT"}
    out = _enforce_evidence_rule(result, rule)
    assert out["status"] == "UNCERTAIN"


def test_enforce_evidence_rule_downgrades_unsupported_pass():
    from app.agents.rule_checker import _enforce_evidence_rule
    result = {
        "status": "PASS",
        "severity": "Low",
        "finding": "Compliant.",
        "excerpt": "N/A",
        "justification_type": "none",
    }
    rule = {"category": "MUST_BE_EXPLICIT"}
    out = _enforce_evidence_rule(result, rule)
    assert out["status"] == "UNCERTAIN"


def test_enforce_evidence_rule_allows_statutory_pass():
    from app.agents.rule_checker import _enforce_evidence_rule
    result = {
        "status": "PASS",
        "severity": "Low",
        "finding": "Governed by statutory law.",
        "excerpt": "N/A",
        "justification_type": "statutory",
    }
    rule = {"category": "STATUTORY"}
    out = _enforce_evidence_rule(result, rule)
    assert out["status"] == "PASS"
