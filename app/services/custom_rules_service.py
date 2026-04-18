import io
import re

import pypdf
import yaml


def _extract_text(content: bytes, content_type: str) -> str:
    if "pdf" in content_type:
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return content.decode(errors="replace")


def _name_from_key(key: str) -> str:
    """Convert snake_case YAML key to human-readable rule name."""
    return key.replace("_", " ").title()


def _describe_value(value) -> str:
    """Recursively flatten a YAML value into a readable constraint string."""
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_describe_value(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _parse_yaml_rules(text: str) -> list[dict] | None:
    """
    Try to interpret the document as YAML.
    Handles files where a prose preamble precedes the YAML block by scanning
    for the first 'rules:' section and parsing from there.
    Returns None if no valid rules block is found.
    """
    # Try the whole text first (pure YAML files)
    candidates = [text]

    # Also try extracting just from a 'rules:' line onward (mixed prose + YAML)
    rules_match = re.search(r"(?m)^rules:\s*$", text)
    if rules_match:
        candidates.append(text[rules_match.start():])

    data = None
    for candidate in candidates:
        try:
            parsed = yaml.safe_load(candidate)
            if isinstance(parsed, dict) and "rules" in parsed:
                data = parsed
                break
        except yaml.YAMLError:
            continue

    if data is None:
        return None

    rules_block = data.get("rules")
    if not isinstance(rules_block, dict):
        return None

    items = list(rules_block.items())
    weight = round(1.0 / len(items), 4) if items else 1.0

    rules = []
    for i, (key, value) in enumerate(items):
        name = _name_from_key(key)
        constraint_text = _describe_value(value) if value is not None else ""
        prompt = f"{name}: {constraint_text}" if constraint_text else name
        rules.append({
            "id": f"custom_{i:03d}",
            "name": name,
            "directive": "Custom",
            "weight": weight,
            "prompt": prompt,
            "_custom": True,
        })

    return rules if rules else None


def _split_into_rules(text: str) -> list[str]:
    """Split a free-text compliance document into individual rule chunks."""
    # Try structured markers: Article N, Rule N, Section N, §N, numbered list
    patterns = [
        r"(?=\bArticle\s+\d+)",
        r"(?=\bRule\s+\d+)",
        r"(?=\bSection\s+\d+)",
        r"(?=§\s*\d+)",
        r"(?=^\s*\d+[\.\)]\s)",
    ]
    for pattern in patterns:
        chunks = [c.strip() for c in re.split(pattern, text, flags=re.MULTILINE) if c.strip()]
        if len(chunks) >= 2:
            return [c for c in chunks if len(c) > 30]

    # Fall back to double-newline paragraph splitting
    chunks = [c.strip() for c in re.split(r"\n{2,}", text) if len(c.strip()) > 30]
    return chunks or [text.strip()]


def parse_compliance_doc(content: bytes, content_type: str) -> list[dict]:
    """Parse an uploaded compliance document into rule dicts compatible with the pipeline."""
    text = _extract_text(content, content_type)

    # Try YAML-structured format first (e.g. internal compliance files with a rules: block)
    yaml_rules = _parse_yaml_rules(text)
    if yaml_rules:
        return yaml_rules

    # Fall back to text-based splitting
    chunks = _split_into_rules(text)
    weight = round(1.0 / len(chunks), 4) if chunks else 1.0

    rules = []
    for i, chunk in enumerate(chunks):
        first_line = chunk.split("\n")[0].strip()[:80]
        rules.append({
            "id": f"custom_{i:03d}",
            "name": first_line or f"Custom Rule {i + 1}",
            "directive": "Custom",
            "weight": weight,
            "prompt": chunk[:600],
            "_custom": True,
        })

    return rules
