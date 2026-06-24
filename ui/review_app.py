"""Streamlit human-in-the-loop review UI.

Shows each escalated item's context, proposed action, reasoning, and relevant
memories, and lets a human apply one of the four approval levels.

Run:  streamlit run ui/review_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `streamlit run ui/review_app.py` without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st  # noqa: E402

from orchestrator.graph import run_task  # noqa: E402
from orchestrator.hitl.audit import AuditChain  # noqa: E402
from orchestrator.hitl.auth import AuthError, auth_enabled, authenticate  # noqa: E402
from orchestrator.hitl.queue import ReviewQueue  # noqa: E402

st.set_page_config(page_title="Agent Review Queue", page_icon="🧠", layout="wide")
st.title("🧠 Multi-Agent Review Queue")
st.caption("Human-in-the-loop approvals · Notify · Approve Action · Approve Plan · Take Over")


def _login_gate():
    """Authenticate the reviewer before any review action (VA-01)."""
    reviewer = st.session_state.get("reviewer")
    if reviewer:
        return reviewer
    with st.form("login"):
        st.subheader("Reviewer sign-in")
        name = st.text_input("Reviewer name")
        token = st.text_input("Token", type="password")
        if st.form_submit_button("Sign in"):
            try:
                reviewer = authenticate(name, token)
                st.session_state["reviewer"] = reviewer.name
                st.rerun()
            except AuthError as exc:
                st.error(f"Sign-in failed: {exc}")
    st.stop()


reviewer_name = _login_gate()
with st.sidebar:
    if auth_enabled():
        st.success(f"Signed in as **{reviewer_name}**")
    else:
        st.warning("⚠️ Auth disabled (local demo). Do not use in production.")
    if st.button("Sign out"):
        st.session_state.pop("reviewer", None)
        st.rerun()

queue = ReviewQueue()

with st.sidebar:
    st.header("Submit a task")
    task = st.text_area("Task", placeholder="Research the top 3 vector DBs and recommend one")
    if st.button("Run", type="primary", disabled=not task):
        with st.spinner("Orchestrating…"):
            result = run_task(task)
        st.success(f"Done · escalated={result.get('escalated')}")
        st.session_state["last_result"] = result

if "last_result" in st.session_state:
    with st.expander("Last run result", expanded=False):
        st.json(st.session_state["last_result"], expanded=False)

st.subheader("Pending reviews")
items = queue.pending()
if not items:
    st.info("No items awaiting review. Submit a task that triggers an escalation.")

for idx, item in enumerate(items):
    with st.container(border=True):
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f"**Task:** {item.task}")
            st.markdown(f"**Reason:** `{item.reason}`  ·  **Level:** `{item.level}`")
            st.markdown("**Proposed action / reasoning:**")
            st.code(item.proposed_action or "(empty)")
            if item.memories:
                st.markdown("**Relevant memories:**")
                for m in item.memories:
                    st.markdown(f"- {m}")
        with cols[1]:
            st.metric("Confidence", f"{item.confidence:.2f}")
            st.metric("Quality", f"{item.quality:.2f}")
            decision = st.radio(
                "Decision",
                ["approve", "reject", "edit", "take_over"],
                key=f"dec-{idx}",
            )
            # edit / take_over need the human's replacement text.
            note = ""
            if decision in ("edit", "take_over"):
                label = "Revised action" if decision == "edit" else "Your answer (final)"
                note = st.text_area(
                    label, key=f"note-{idx}", value=item.proposed_action if decision == "edit" else ""
                )
            if st.button("Resolve", key=f"res-{idx}"):
                try:
                    res = queue.resolve(idx, decision, approver=reviewer_name, note=note)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["last_resolution"] = {
                        "task_id": res.task_id,
                        "decision": res.decision,
                        "approver": res.approver,
                        "timestamp": res.timestamp,
                        "final_result": res.final_result,
                    }
                    st.rerun()

# Show the most recent resolution and the verifiable audit trail.
if "last_resolution" in st.session_state:
    st.subheader("Last resolution")
    st.json(st.session_state["last_resolution"], expanded=False)

with st.expander("Audit trail (tamper-evident)", expanded=False):
    intact, broken_at = AuditChain().verify()
    if intact:
        st.success("✅ Audit chain verified — no tampering detected.")
    else:
        st.error(f"⚠️ Audit chain broken at record #{broken_at}.")
    st.json(queue.audit_log(), expanded=False)
