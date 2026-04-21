import json
import os

import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="German Contract Compliance Checker",
    page_icon="⚖️",
    layout="wide",
)

# Session state init
for key, default in [
    ("history", []),
    ("rule_cards", []),
    ("final_data", {}),
    ("current_job_id", None),
    ("current_filename", None),
    ("show_results", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Custom Compliance Rules")
    compliance_file = st.file_uploader(
        "Upload your compliance rules (PDF or TXT)",
        type=["pdf", "txt"],
        key="compliance_uploader",
        help="Optional. If uploaded, only these rules will be checked instead of the default German ruleset.",
    )
    if compliance_file:
        st.success(f"Custom rules ready: **{compliance_file.name}**")
    else:
        st.caption("No custom rules uploaded — default German compliance rules will be used.")

    st.divider()
    st.header("Review History")
    if st.session_state.history:
        for item in reversed(st.session_state.history):
            st.markdown(
                f"**{item['filename']}**  \n"
                f"`{item['job_id'][:8]}…` — Score: {item.get('score', '—')}"
            )
            if item.get("report"):
                st.download_button(
                    label="Download report",
                    data=json.dumps(item["report"], indent=2),
                    file_name=f"compliance_report_{item['job_id'][:8]}.json",
                    mime="application/json",
                    key=f"dl_{item['job_id']}",
                )
            st.divider()
    else:
        st.caption("No reviews yet this session.")

# ── Main content ─────────────────────────────────────────────────────────────
st.title("German Contract Compliance Checker")
st.caption("Multi-agent AI pipeline • LangGraph • OpenAI")

uploaded_file = st.file_uploader(
    "Upload a contract (PDF, DOCX, or TXT — max 20 MB)",
    type=["pdf", "docx", "txt"],
)


def _render_rule_card(card: dict):
    status = card.get("status", "PASS")
    color = {
        "PASS": "green",
        "FAIL": "red",
        "WARNING": "orange",
        "UNCERTAIN": "blue",
        "NOT_APPLICABLE": "grey",
        "ERROR": "grey",
    }.get(status, "grey")
    severity = card.get("severity", "")
    category = card.get("category", "")

    category_badge = f" &nbsp; _{category}_" if category else ""
    st.markdown(
        f"**:{color}[{status}]** &nbsp; `{card['directive']}` &nbsp; "
        f"**{card['rule_name']}** &nbsp; _{severity} severity_{category_badge}"
    )

    if status == "NOT_APPLICABLE":
        st.caption(f"_{card.get('finding', 'Rule not applicable to this contract.')}_")
        st.divider()
        return

    if status == "ERROR":
        st.caption("_System error — this rule could not be evaluated. It has been excluded from scoring._")
        st.divider()
        return

    st.markdown(f"> {card['finding']}")
    with st.expander("Evidence excerpt, recommendation & evaluation"):
        excerpt = card.get("excerpt", "N/A")
        if excerpt and excerpt.strip() not in ("N/A", ""):
            st.markdown(f"*Excerpt:* `{excerpt}`")
        else:
            st.warning("No supporting excerpt found in contract text.")
        st.markdown(f"*Recommendation:* {card['recommendation']}")

        ev = card.get("evaluation")
        if ev:
            st.divider()
            st.caption("**LLM-as-a-Judge Evaluation**")
            fp_color = {"low": "green", "medium": "orange", "high": "red"}.get(
                ev.get("false_positive_risk", "low"), "grey"
            )
            cal_color = "green" if ev.get("severity_calibration") == "correct" else "orange"
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Accuracy", f"{ev['accuracy_score']:.2f}")
            c2.metric("Completeness", f"{ev['completeness_score']:.2f}")
            c3.markdown(f"FP Risk: **:{fp_color}[{ev.get('false_positive_risk', '—')}]**")
            c4.markdown(f"Severity: **:{cal_color}[{ev.get('severity_calibration', '—')}]**")
            if ev.get("judge_note"):
                st.caption(f"Note: {ev['judge_note']}")
    st.divider()


if not uploaded_file:
    st.session_state.show_results = False

if uploaded_file and st.button("Run Compliance Review", type="primary"):
    # Clear previous results
    st.session_state.rule_cards = []
    st.session_state.final_data = {}
    st.session_state.show_results = False
    st.session_state.current_filename = uploaded_file.name

    # ── Step 1: Upload ────────────────────────────────────────────────────
    with st.spinner("Uploading contract…"):
        try:
            upload_files = {
                "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type),
            }
            if compliance_file:
                upload_files["compliance_file"] = (
                    compliance_file.name, compliance_file.getvalue(), compliance_file.type
                )
            resp = httpx.post(
                f"{API_BASE_URL}/upload",
                files=upload_files,
                timeout=120,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            st.error(f"Upload failed: {exc}")
            st.stop()

    resp_data = resp.json()
    job_id = resp_data["job_id"]
    st.session_state.current_job_id = job_id
    custom_count = resp_data.get("custom_rule_count", 0)
    if custom_count:
        st.success(f"Uploaded — job ID: `{job_id}` — using **{custom_count} custom rules**")
    else:
        st.success(f"Uploaded — job ID: `{job_id}` — using default German compliance rules")

    # ── Step 2: Stream rule results ───────────────────────────────────────
    st.subheader("Live Compliance Results")
    cards_container = st.container()
    score_placeholder = st.empty()

    try:
        with httpx.Client(timeout=120) as client:
            with client.stream("GET", f"{API_BASE_URL}/review/stream/{job_id}") as response:
                event_type = ""
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        raw = line[6:].strip()
                        if not raw or raw == "{}":
                            continue
                        data = json.loads(raw)

                        if event_type == "rule_result":
                            st.session_state.rule_cards.append(data)
                            with cards_container:
                                _render_rule_card(data)

                        elif event_type == "final":
                            st.session_state.final_data = data

                        elif event_type == "error":
                            st.error(f"Pipeline error: {data.get('message')}")

                        elif event_type == "done":
                            break

    except httpx.HTTPError as exc:
        st.error(f"Streaming failed: {exc}")
        st.stop()

    # ── Step 3: Final score ───────────────────────────────────────────────
    final_data = st.session_state.final_data
    if final_data:
        score = final_data.get("overall_score", 0)
        risk = final_data.get("risk_level", "Unknown")
        contract_type = final_data.get("contract_type", "")
        collar_type = final_data.get("collar_type", "")
        label = (
            f"Employment Contract — {collar_type.title()}-Collar"
            if contract_type == "employment"
            else "Vendor Contract"
        )

        with score_placeholder.container():
            st.divider()
            st.info(f"Detected contract type: **{label}**")
            col1, col2 = st.columns(2)
            col1.metric("Compliance Score", f"{score} / 100")
            col2.metric("Risk Level", risk)

            report = final_data.get("report", {})
            if report.get("executive_summary"):
                st.markdown(f"**Summary:** {report['executive_summary']}")

            st.download_button(
                "Download Full Report (JSON)",
                data=json.dumps(final_data, indent=2),
                file_name=f"compliance_report_{job_id[:8]}.json",
                mime="application/json",
            )

        st.session_state.show_results = True
        st.session_state.history.append(
            {
                "job_id": job_id,
                "filename": uploaded_file.name,
                "score": f"{score}/100",
                "report": final_data,
            }
        )

# ── Persist results while file is still selected ──────────────────────────────
elif uploaded_file and st.session_state.show_results and st.session_state.rule_cards:
    st.subheader(f"Last Review — {st.session_state.current_filename or 'contract'}")

    for card in st.session_state.rule_cards:
        _render_rule_card(card)

    final_data = st.session_state.final_data
    if final_data:
        score = final_data.get("overall_score", 0)
        risk = final_data.get("risk_level", "Unknown")
        contract_type = final_data.get("contract_type", "")
        collar_type = final_data.get("collar_type", "")
        label = (
            f"Employment Contract — {collar_type.title()}-Collar"
            if contract_type == "employment"
            else "Vendor Contract"
        )

        st.divider()
        st.info(f"Detected contract type: **{label}**")
        col1, col2 = st.columns(2)
        col1.metric("Compliance Score", f"{score} / 100")
        col2.metric("Risk Level", risk)

        report = final_data.get("report", {})
        if report.get("executive_summary"):
            st.markdown(f"**Summary:** {report['executive_summary']}")

        job_id = st.session_state.current_job_id or "unknown"
        st.download_button(
            "Download Full Report (JSON)",
            data=json.dumps(final_data, indent=2),
            file_name=f"compliance_report_{job_id[:8]}.json",
            mime="application/json",
        )
