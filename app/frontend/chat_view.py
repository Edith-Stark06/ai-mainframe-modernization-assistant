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
from app.frontend.components import stat_row
from app.frontend.design import ui

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
    """An honest, specific status for a failed turn. No answer text is ever
    invented to stand in for it."""
    heading, word = _ERROR_HEADINGS.get(
        error_code or "", ("MODERNIZATION CHAT", "FAILED")
    )
    tone = ui.tone_for(word)
    ui.render(
        ui.callout(
            "warning" if tone == "neutral" else tone,
            f"{heading.capitalize()}: {word.lower()}",
            message,
        )
    )


#: How many earlier messages are sent along with a question.
_HISTORY_TURNS = 6


def _render_answer(chat_res: Dict[str, Any]) -> str:
    answer = chat_res.get("answer") or ""
    st.write(answer)
    context = chat_res.get("context") or []
    if context:
        with st.expander(f"Evidence ({len(context)})"):
            for item in context:
                label = item.get("ref") or item.get("id")
                st.caption(f"[{label}] {item.get('content', '')[:300]}")
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


#: Questions worth asking of any parsed program; each is answered from the
#: file's own analysis, so none of them promises something the backend lacks.
SUGGESTIONS = (
    "Explain what this program does",
    "List the business rules in this program",
    "What are the main risks if we modernize it?",
    "Did the converted Java compile and pass its tests?",
)


def _render_empty_state(
    filename: Optional[str], report: Optional[Dict[str, Any]]
) -> None:
    """The opening screen: a greeting, what the assistant knows, and one-tap
    questions."""
    ui.render(
        '<div class="ds-chat-hello">'
        + ui.brand_mark(40)
        + '<h2 class="ds-chat-hello-title">What would you like to know about '
        + f"{ui.esc(filename or 'this program')}?</h2>"
        + '<p class="ds-chat-hello-sub">Answers come from the parsed program and its '
        "validation results, with numbered sources. If the evidence does not "
        "cover a question, I will say so.</p></div>"
    )
    if report is not None:
        _render_context_stats(report)
    for row in range(0, len(SUGGESTIONS), 2):
        for offset, column in enumerate(st.columns(2)):
            index = row + offset
            with column:
                if st.button(
                    SUGGESTIONS[index],
                    key=f"suggest_{index}",
                    icon=":material/arrow_outward:",
                    width="stretch",
                    disabled=not filename,
                ):
                    st.session_state.chat_pending = SUGGESTIONS[index]
                    st.rerun()


def _render_turn(
    client: BackendClient,
    workspace_id: str,
    filename: Optional[str],
    prompt: str,
    include_context: bool,
) -> None:
    """Send one question and render the user message and the real answer."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # The turns before this question, so "and for type B?" can be understood.
    # Sent only when there are some: a first message goes out exactly as before.
    history = [
        {"role": m["role"], "content": str(m["content"])}
        for m in st.session_state.messages[:-1][-_HISTORY_TURNS:]
    ]
    extra: Dict[str, Any] = {"history": history} if history else {}

    with st.chat_message("assistant"):
        _ensure_indexed(client, workspace_id, filename)
        with st.spinner("Thinking..."):
            try:
                chat_res = client.send_chat_message(
                    workspace_id=workspace_id,
                    query=prompt,
                    filename=filename,
                    include_modernization_context=include_context,
                    **extra,
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


def render_chat(
    client: BackendClient,
    workspace_id: str,
    filename: Optional[str],
    *,
    report: Optional[Dict[str, Any]] = None,
) -> None:
    """The assistant: a centred conversation, one-tap questions, a pinned
    composer. Widget keys (``chat_input``, ``include_modernization_context``)
    are stable."""
    with st.container(key="chat_header"):
        title, context, fresh = st.columns([5, 3, 1.6], vertical_alignment="center")
        with title:
            ui.render(
                '<div class="ds-chat-title">Modernization Chat'
                + (
                    f'<span class="ds-chat-file">{ui.esc(filename)}</span>'
                    if filename
                    else ""
                )
                + "</div>"
            )
        with context:
            include_context = st.checkbox(
                "Include context",
                value=False,
                disabled=not filename,
                key="include_modernization_context",
                help="Include the file's modernization analysis summary with the question.",
            )
        with fresh:
            if st.button(
                "New chat",
                key="new_chat",
                icon=":material/add:",
                width="stretch",
            ):
                st.session_state.messages = []
                st.rerun()

    typed = st.chat_input("Ask about this source file", key="chat_input")
    prompt = typed or st.session_state.pop("chat_pending", None)

    with st.container(key="chat_thread"):
        if not st.session_state.messages and not prompt:
            _render_empty_state(filename, report)
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        if prompt:
            _render_turn(client, workspace_id, filename, prompt, include_context)
