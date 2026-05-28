from __future__ import annotations

import logging
import os
import uuid

import streamlit as st
from dotenv import load_dotenv
from langgraph.types import Command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_FILE_FMT = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)


def _add_file_handler(logger_name: str, filename: str) -> None:
    logger = logging.getLogger(logger_name)
    log_path = os.path.join(_LOG_DIR, filename)
    # Avoid adding a duplicate handler on every Streamlit rerun (loggers are
    # module-level singletons that survive between reruns).
    if any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_path)
           for h in logger.handlers):
        return
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(_FILE_FMT)
    logger.addHandler(handler)


_add_file_handler("app.nodes.research", "research.log")
_add_file_handler("app.nodes.enrich", "enrich.log")

load_dotenv()

# Import after dotenv so env vars are set before LiteLLM reads them
from app.graph import graph  # noqa: E402
from app.tools.github import create_issue  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Post for me, please",
    page_icon="✍️",
    layout="centered",
)

# ── Session state defaults ────────────────────────────────────────────────────
if "stage" not in st.session_state:
    st.session_state.stage = 1
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "candidates" not in st.session_state:
    st.session_state.candidates = []
if "final_posts" not in st.session_state:
    st.session_state.final_posts = []
if "issue_url" not in st.session_state:
    st.session_state.issue_url = None


def _config() -> dict:
    return {"configurable": {"thread_id": st.session_state.thread_id}}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Input
# ─────────────────────────────────────────────────────────────────────────────
def render_stage_1() -> None:
    st.title("✍️ Post for me, please")
    st.caption("Paste up to 3 reference links, describe what you want to post about, and let the agent do the rest.")

    with st.form("input_form"):
        st.subheader("Reference links")
        url1 = st.text_input("Link 1", placeholder="https://...")
        url2 = st.text_input("Link 2 (optional)", placeholder="https://...")
        url3 = st.text_input("Link 3 (optional)", placeholder="https://...")

        st.subheader("Post intent")
        intent = st.text_area(
            "What do you want the post to be about?",
            placeholder="e.g. I want to explain why LangGraph's interrupt() is different from just checking a condition in a node, and when you'd actually reach for it.",
            height=100,
        )

        audience = st.selectbox(
            "Target audience",
            ["engineers", "tech leads & engineering managers", "founders & technical founders", "general tech audience"],
        )

        submitted = st.form_submit_button("Generate topic candidates →", type="primary")

    if submitted:
        urls = [u.strip() for u in [url1, url2, url3] if u.strip()]
        if not urls:
            st.error("Paste at least one reference link.")
            return
        if not intent.strip():
            st.error("Describe what you want to post about.")
            return

        # Start a fresh graph thread
        st.session_state.thread_id = str(uuid.uuid4())
        initial_state = {
            "reference_urls": urls,
            "intent": intent.strip(),
            "audience": audience,
            "selected_ids": [],
            "enriched_candidates": [],
            "final_posts": [],
        }

        with st.spinner("Reading your references and finding postable topics…"):
            try:
                result = graph.invoke(initial_state, _config())
            except Exception as e:
                st.error(f"Research failed: {e}")
                return

        # Graph suspends at topic_selection interrupt — extract candidates from state
        state_snapshot = graph.get_state(_config())
        interrupt_data = _get_interrupt_data(state_snapshot)

        if interrupt_data and interrupt_data.get("stage") == "topic_selection":
            st.session_state.candidates = interrupt_data.get("candidates", [])
            st.session_state.stage = 2
            st.rerun()
        else:
            st.error("Unexpected graph state. Try again.")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Topic candidate selection
# ─────────────────────────────────────────────────────────────────────────────
def render_stage_2() -> None:
    st.title("✍️ Pick your topics")
    st.caption("Select 1 or 2 topics you want to post about. The agent will research and write posts for each.")

    candidates = st.session_state.candidates
    if not candidates:
        st.warning("No candidates found. Try different links or a more specific intent.")
        if st.button("← Start over"):
            _reset()
        return

    selected_ids: list[str] = []
    for c in candidates:
        col1, col2 = st.columns([0.05, 0.95])
        with col1:
            checked = st.checkbox("", key=f"check_{c['id']}", label_visibility="collapsed")
        with col2:
            st.markdown(f"**{c['title']}**")
            st.caption(c["thesis"])
            with st.expander("Source excerpt"):
                st.write(c["source_excerpt"])
        if checked:
            selected_ids.append(c["id"])

    st.divider()
    col_back, col_confirm = st.columns([1, 3])
    with col_back:
        if st.button("← Start over"):
            _reset()
    with col_confirm:
        if st.button(
            "Enrich & write posts →",
            type="primary",
            disabled=len(selected_ids) == 0 or len(selected_ids) > 2,
        ):
            if len(selected_ids) > 2:
                st.warning("Pick at most 2 topics.")
                return

            with st.spinner("Researching HN, GitHub, docs… writing your posts…"):
                try:
                    graph.invoke(
                        Command(resume={"selected_ids": selected_ids}),
                        _config(),
                    )
                except Exception as e:
                    st.error(f"Enrichment/writing failed: {e}")
                    return

            state_snapshot = graph.get_state(_config())
            interrupt_data = _get_interrupt_data(state_snapshot)

            if interrupt_data and interrupt_data.get("stage") == "post_review":
                st.session_state.final_posts = interrupt_data.get("final_posts", [])
                st.session_state.stage = 4
                st.rerun()
            else:
                # Maybe graph completed without a second interrupt (no candidates?)
                values = state_snapshot.values if hasattr(state_snapshot, "values") else {}
                st.session_state.final_posts = values.get("final_posts", [])
                st.session_state.stage = 4
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Post options
# ─────────────────────────────────────────────────────────────────────────────
def render_stage_4() -> None:
    st.title("✍️ Your post options")
    st.caption("Pick an option, copy it, and post. Or publish all options to a GitHub issue for later.")

    final_posts = st.session_state.final_posts
    if not final_posts:
        st.warning("No posts were generated.")
        if st.button("← Start over"):
            _reset()
        return

    option_labels = ["Option A — The mistake", "Option B — The mental model", "Option C — The decision"]

    for topic in final_posts:
        st.subheader(topic.get("title", "Topic"))
        st.caption(topic.get("thesis", ""))

        posts = topic.get("posts", ["", "", ""])
        # Pad to 3 in case the LLM returned fewer
        while len(posts) < 3:
            posts.append("")

        tabs = st.tabs(option_labels)
        for tab, label, post_text in zip(tabs, option_labels, posts):
            with tab:
                if post_text:
                    st.write(post_text)
                    st.code(post_text, language=None)
                else:
                    st.info("Post not generated.")

        st.divider()

    # GitHub issue (opt-in)
    with st.expander("📌 Publish all options to a GitHub issue"):
        issue_title = st.text_input(
            "Issue title",
            value=f"LinkedIn post options — {_today()}",
            key="issue_title",
        )
        if st.button("Create GitHub issue", key="create_issue"):
            body = _build_issue_body(final_posts, option_labels)
            try:
                url = create_issue(title=issue_title, body=body)
                st.session_state.issue_url = url
                st.success(f"Issue created: {url}")
            except Exception as e:
                st.error(f"Failed to create issue: {e}")

    if st.session_state.issue_url:
        st.link_button("Open issue", st.session_state.issue_url)

    if st.button("← Start over with new links"):
        _reset()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _reset() -> None:
    for key in ("stage", "thread_id", "candidates", "final_posts", "issue_url"):
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()


def _get_interrupt_data(state_snapshot) -> dict | None:
    """Extract interrupt payload from a graph state snapshot."""
    tasks = getattr(state_snapshot, "tasks", None) or []
    for task in tasks:
        interrupts = getattr(task, "interrupts", None) or []
        for intr in interrupts:
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                return value
    return None


def _build_issue_body(final_posts: list, option_labels: list[str]) -> str:
    sections: list[str] = []
    for topic in final_posts:
        title = topic.get("title", "Topic")
        thesis = topic.get("thesis", "")
        posts = topic.get("posts", ["", "", ""])
        while len(posts) < 3:
            posts.append("")

        block = [f"## {title}", f"_{thesis}_", ""]
        for label, post_text in zip(option_labels, posts):
            block.append(f"### {label}")
            block.append(post_text or "_Not generated._")
            block.append("")
        sections.append("\n".join(block))

    return "\n---\n\n".join(sections)


def _today() -> str:
    from datetime import date
    return date.today().strftime("%Y-%m-%d")


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────
stage = st.session_state.get("stage", 1)

if stage == 1:
    render_stage_1()
elif stage == 2:
    render_stage_2()
elif stage == 4:
    render_stage_4()
else:
    render_stage_1()
