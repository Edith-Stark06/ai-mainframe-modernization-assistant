"""
Phase 12 -- Modernization Chat view, backed by the real
``POST /api/v1/chat/`` endpoint.

Renders exactly what the backend reported. When ``error_code`` is set,
this shows a specific, honest status (AI provider not configured /
grounded context insufficient / generation failed / ...) instead of
the old, undifferentiated "AI generation failed due to an internal
error." message -- never a fabricated answer, never a canned response
standing in for a real one.

Kept as its own module, independent of ``java_workspace.py``, per the
reviewed component-separation requirement -- both are wired into
``app.py`` but neither imports the other.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from app.frontend.client import BackendAPIError, BackendClient
from app.frontend.components import section_header, stat_row
from app.frontend.theme import status_pill

__all__ = ["render_chat"]

# error_code -> (heading, status word for the pill)
_ERROR_HEADINGS: Dict[str, tuple[str, str]] = {
    "LLM_PROVIDER_NOT_CONFIGURED": ("AI PROVIDER", "NOT AVAILABLE"),
    "LLM_PROVIDER_UNAVAILABLE": ("AI PROVIDER", "UNAVAILABLE"),
    "LLM_GENERATION_FAILED": ("AI GENERATION", "FAILED"),
    "GROUNDED_CONTEXT_UNAVAILABLE": ("GROUNDED CONTEXT", "UNAVAILABLE"),
    "INSUFFICIENT_CONTEXT": ("GROUNDED CONTEXT", "INSUFFICIENT"),
    "INTERNAL_ERROR": ("MODERNIZATION CHAT", "FAILED"),
}


def _render_error(error_code: Optional[str], message: str) -> None:
    heading, word = _ERROR_HEADINGS.get(
        error_code or "", ("MODERNIZATION CHAT", "FAILED")
    )
    st.markdown(
        f'<div class="mf-panel">'
        f'<div class="mf-muted" style="font-size:0.72rem;letter-spacing:0.08em;">{heading}</div>'
        f"{status_pill(word, word)}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(message)


def _render_answer(chat_res: Dict[str, Any]) -> str:
    answer = chat_res.get("answer") or ""
    st.write(answer)
    context = chat_res.get("context") or []
    if context:
        with st.expander(f"Evidence ({len(context)})"):
            for item in context:
                st.caption(f"[{item.get('id')}] {item.get('content', '')[:300]}")
    return answer


def _ensure_indexed(
    client: BackendClient, workspace_id: str, filename: Optional[str]
) -> None:
    """
    Index *filename* for chat retrieval, once per browser session.

    Chat only retrieves content that has been indexed; without this the
    backend searches an empty index and can only answer "not enough
    evidence". A failure is shown as a warning and does not stop the
    question from being asked -- chat then reports the missing evidence
    honestly rather than the UI dying on an indexing problem. A file
    that failed to index is retried on the next question.
    """
    if not filename:
        return
    indexed = st.session_state.setdefault("chat_indexed", set())
    key = (workspace_id, filename)
    if key in indexed:
        return
    with st.spinner("Indexing this file for chat (first question only)..."):
        try:
            client.index_for_chat(workspace_id, filename)
        except BackendAPIError as e:
            st.warning(f"Could not index this file for chat: {e.message}")
            return
    indexed.add(key)


def _render_context_stats(report: Dict[str, Any]) -> None:
    coverage = report.get("coverage")
    stat_row(
        [
            ("Rules", str(len(report.get("business_rules") or []))),
            ("Dependencies", str(len(report.get("dependencies") or []))),
            ("Risks", str(len(report.get("risks") or []))),
            ("Coverage", f"{coverage['overall']:.0%}" if coverage else "—"),
        ]
    )


def render_chat(
    client: BackendClient,
    workspace_id: str,
    filename: Optional[str],
    *,
    report: Optional[Dict[str, Any]] = None,
) -> None:
    section_header(
        "Modernization Chat",
        filename or None,
        eyebrow="AI",
        eyebrow_accent="violet",
    )
    if report is not None:
        _render_context_stats(report)

    include_context = st.checkbox(
        "Include modernization context for this file",
        value=False,
        disabled=not filename,
        key="include_modernization_context",
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("Ask about this source file", key="chat_input")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        _ensure_indexed(client, workspace_id, filename)
        with st.spinner("Thinking..."):
            try:
                chat_res = client.send_chat_message(
                    workspace_id=workspace_id,
                    query=prompt,
                    filename=filename,
                    include_modernization_context=include_context,
                )
            except BackendAPIError as e:
                st.error(e.message)
                return

        error_code = chat_res.get("error_code")
        error = chat_res.get("error")
        if error:
            _render_error(error_code, error)
            # No fabricated AI text is ever added to the transcript for an
            # error -- the transcript only records real answers.
        else:
            answer = _render_answer(chat_res)
            st.session_state.messages.append({"role": "assistant", "content": answer})
