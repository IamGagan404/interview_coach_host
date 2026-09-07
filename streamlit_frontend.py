"""
Streamlit frontend for the AI Interview Prep Coach.

"""

import requests
import streamlit as st

BACKEND_URL = "http://127.0.0.1:8000"  # change when deployed


def start_interview(role_context: str, max_turns: int) -> dict:
    resp = requests.post(
        f"{BACKEND_URL}/interview/start",
        json={"role_context": role_context, "max_turns": max_turns},
    )
    resp.raise_for_status()
    return resp.json()


def submit_answer(session_id: str, answer: str) -> dict:
    resp = requests.post(f"{BACKEND_URL}/interview/{session_id}/answer", json={"answer": answer})
    resp.raise_for_status()
    return resp.json()


def get_transcript(session_id: str) -> dict:
    resp = requests.get(f"{BACKEND_URL}/interview/{session_id}/transcript")
    resp.raise_for_status()
    return resp.json()


st.set_page_config(page_title="AI Interview Prep Coach", page_icon="🎤")
st.title("🎤 AI Interview Prep Coach")

# ---------------------------------------------------------------------------
# Session bootstrap
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = None
    st.session_state.current_question = None
    st.session_state.done = False
    st.session_state.summary = None
    st.session_state.history = []  # list of {question, answer, evaluation, feedback}

# ---------------------------------------------------------------------------
# Start screen
# ---------------------------------------------------------------------------
if st.session_state.session_id is None:
    st.write("Paste a job description or your background so questions can be tailored.")
    role_context = st.text_area(
        "Role / background",
        placeholder="e.g. Backend engineer, 4 yrs Python/Django/FastAPI, K8s + monitoring experience",
        height=120,
    )
    max_turns = st.slider("Number of questions", min_value=1, max_value=10, value=5)

    if st.button("Start Interview"):
        if not role_context.strip():
            st.warning("Please describe the role or paste a job description first.")
            st.stop()

        with st.spinner("Preparing your first question..."):
            result = start_interview(role_context, max_turns)
        st.session_state.session_id = result["session_id"]
        st.session_state.current_question = result["question"]
        st.rerun()

# ---------------------------------------------------------------------------
# Active interview screen
# ---------------------------------------------------------------------------
elif not st.session_state.done:
    st.subheader(f"Question {len(st.session_state.history) + 1}")
    st.write(st.session_state.current_question)

    answer = st.text_area("Your answer", key=f"answer_{len(st.session_state.history)}")

    if st.button("Submit Answer"):
        if not answer.strip():
            st.warning("Please write an answer before submitting.")
            st.stop()

        with st.spinner("Evaluating your answer..."):
            result = submit_answer(st.session_state.session_id, answer)

        st.session_state.history.append({
            "question": st.session_state.current_question,
            "answer": answer,
            "evaluation": result.get("evaluation"),
            "feedback": result.get("feedback"),
        })

        if result.get("status") == "done":
            st.session_state.done = True
            st.session_state.summary = result.get("summary")
        else:  # status == "asking" -> more questions to go
            st.session_state.current_question = result.get("next_question")

        st.rerun()

    # Show feedback from the most recent turn, if any
    if st.session_state.history:
        last = st.session_state.history[-1]
        with st.expander("Last evaluation & feedback", expanded=True):
            evaluation = last["evaluation"] or {}
            scores = evaluation.get("scores") or {}
            weaknesses = evaluation.get("weaknesses") or []

            if scores:
                st.write("**Scores** (out of 5):")
                cols = st.columns(len(scores))
                for col, (label, value) in zip(cols, scores.items()):
                    col.metric(label.replace("_", " ").title(), value)
            elif evaluation.get("raw_response"):
                # Gemini's JSON didn't parse cleanly — show what we got instead of a raw dict dump
                st.write("**Evaluation (unparsed):**")
                st.text(evaluation["raw_response"])

            if weaknesses:
                st.write("**Areas to improve:**")
                for w in weaknesses:
                    st.markdown(f"- {w}")

            st.write("**Coach feedback:**")
            st.write(last["feedback"])

# ---------------------------------------------------------------------------
# Done screen
# ---------------------------------------------------------------------------
else:
    st.success("Interview complete! 🎉")

    for entry in st.session_state.history:
        st.markdown(f"**Q:** {entry['question']}")
        st.markdown(f"**A:** {entry['answer']}")
        st.markdown(f"*Coach: {entry['feedback']}*")
        st.divider()

    if st.session_state.summary:
        st.markdown(f"### Overall Summary\n{st.session_state.summary}")

    with st.expander("View raw transcript"):
        transcript = get_transcript(st.session_state.session_id)
        st.json(transcript["transcript"])

    if st.button("Start New Interview"):
        for key in ["session_id", "current_question", "done", "summary", "history"]:
            del st.session_state[key]
        st.rerun()