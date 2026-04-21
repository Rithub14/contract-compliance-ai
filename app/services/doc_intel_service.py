import re


class DocIntelService:
    async def extract_clauses(self, content: bytes) -> list[dict]:
        text = content.decode(errors="replace")

        # Split on § section markers (common in EU/German contracts)
        parts = re.split(r'(?=§\d+\s)', text)

        clauses = []
        for i, part in enumerate(parts):
            part = part.strip()
            if len(part) < 15:
                continue
            lines = [ln for ln in part.split("\n") if ln.strip()]
            title = lines[0].strip()[:100] if lines else f"Section {i + 1}"
            clauses.append({
                "clause_id": f"cl_{i:03d}",
                "title": title,
                "text": part[:2500],
                "page": max(1, i // 4 + 1),
            })

        if not clauses:
            paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if len(p.strip()) > 20]
            clauses = [
                {
                    "clause_id": f"cl_{i:03d}",
                    "title": p.split("\n")[0].strip()[:80],
                    "text": p[:2500],
                    "page": max(1, i // 5 + 1),
                }
                for i, p in enumerate(paragraphs)
            ]

        return clauses or [{"clause_id": "cl_000", "title": "Full Document", "text": text[:5000], "page": 1}]
