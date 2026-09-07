"""
AI Interview Prep Coach — LangGraph skeleton
Supervisor routes each turn to Question Generator, Answer Evaluator, or
Feedback Coach based on session phase. Loops per user turn until session ends.
"""

from typing import TypedDict, List, Literal, Optional
from langgraph.graph import StateGraph, END
# from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import os, streamlit as st
from dotenv import load_dotenv
load_dotenv()



# ---------- 1. State ----------
class InterviewState(TypedDict):
    role_context: str              # JD or CV excerpt, tailors the questions
    topics_covered: List[str]
    current_question: str
    last_answer: Optional[str]     # set by the API when the user responds
    conversation: List[dict]       # full transcript: [{"role": ..., "content": ...}]
    last_evaluation: dict          # {"scores": {...}, "weaknesses": [...]}
    turn_count: int
    max_turns: int
    phase: Literal["asking", "evaluating", "coaching", "done"]


# llm = ChatOllama(model="llama3.1", temperature=0.4)


def get_gemini_api_key():
    if "GEMINI_API_KEY" in st.secrets:
        return st.secrets["GEMINI_API_KEY"]
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return key

llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=get_gemini_api_key(),
    temperature=0.4,
)

def extract_text(response) -> str:
    """Normalize LLM response content to a plain string, handling both
    plain-string and list-of-blocks formats (Gemini sometimes returns the latter)."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "".join(parts).strip()
    return str(content).strip()

# ---------- 2. Agent nodes ----------
def question_generator_node(state: InterviewState) -> InterviewState:
    prompt = f"""You are interviewing a candidate for this role/background:
{state['role_context']}

Topics already covered: {state['topics_covered'] or 'none yet'}

Ask ONE new interview question that has not been covered. Return only the question."""
    response = llm.invoke([HumanMessage(content=prompt)])
    question = extract_text(response)

    conversation = state["conversation"] + [{"role": "interviewer", "content": question}]
    return {
        **state,
        "current_question": question,
        "conversation": conversation,
        "phase": "evaluating",
    }



def answer_evaluator_node(state: InterviewState) -> InterviewState:
    prompt = f"""Question: {state['current_question']}
Candidate's answer: {state['last_answer']}
 
Score the answer 1-5 on: structure, specificity, technical_accuracy, impact.
List 1-3 concrete weaknesses. Respond as JSON:
{{"scores": {{"structure": n, "specificity": n, "technical_accuracy": n, "impact": n}}, "weaknesses": ["..."]}}"""
    response = llm.invoke([HumanMessage(content=prompt)])
 
    import json
 
    def extract_json_object(text: str) -> str:
        """Find the first balanced {...} block, ignoring any prose before/after."""
        start = text.find("{")
        if start == -1:
            return text
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]  # unbalanced — let json.loads raise and hit the fallback
 
    raw = extract_text(response)
    candidate = extract_json_object(raw)
    try:
        evaluation = json.loads(candidate)
    except json.JSONDecodeError:
        evaluation = {"scores": {}, "weaknesses": ["Could not parse evaluation"], "raw_response": raw}
 
    return {
        **state,
        "last_evaluation": evaluation,
        "topics_covered": state["topics_covered"] + [state["current_question"]],
        "conversation": state["conversation"] + [{"role": "candidate", "content": state["last_answer"]}],
        "phase": "coaching",
    }
 


def feedback_coach_node(state: InterviewState) -> InterviewState:
    prompt = f"""The candidate answered: {state['last_answer']}
Evaluation: {state['last_evaluation']}

Give 2-3 sentences of specific, encouraging coaching feedback. Be concrete —
reference what they actually said, not generic advice."""
    response = llm.invoke([HumanMessage(content=prompt)])
    feedback = extract_text(response)

    conversation = state["conversation"] + [{"role": "coach", "content": feedback}]
    turn_count = state["turn_count"] + 1
    next_phase = "done" if turn_count >= state["max_turns"] else "asking"

    return {
        **state,
        "conversation": conversation,
        "turn_count": turn_count,
        "last_answer": None,       
        "phase": next_phase,
    }


def summary_node(state: InterviewState) -> InterviewState:
    prompt = f"""Review this full interview transcript and summarize patterns
across all answers — recurring strengths and recurring weaknesses.

Transcript: {state['conversation']}"""
    response = llm.invoke([HumanMessage(content=prompt)])
    conversation = state["conversation"] + [{"role": "summary", "content": extract_text(response)}]
    return {**state, "conversation": conversation}


# ---------- 3. Supervisor routing ----------
def route_supervisor(state: InterviewState) -> Literal["question_generator", "answer_evaluator", "feedback_coach", "summary"]:
    if state["phase"] == "done":
        return "summary"
    if state["phase"] == "coaching":
        return "feedback_coach"
    if state["phase"] == "evaluating":
        return "answer_evaluator"
    return "question_generator"


# ---------- 4. Build the graph ----------
def build_graph():
    graph = StateGraph(InterviewState)

    graph.add_node("question_generator", question_generator_node)
    graph.add_node("answer_evaluator", answer_evaluator_node)
    graph.add_node("feedback_coach", feedback_coach_node)
    graph.add_node("summary", summary_node)

    # Supervisor is a routing function, not a node with its own logic —
    # each agent node returns to a conditional check on `phase`.
    graph.set_conditional_entry_point(route_supervisor, {
        "question_generator": "question_generator",
        "answer_evaluator": "answer_evaluator",
        "feedback_coach": "feedback_coach",
        "summary": "summary",
    })

    graph.add_edge("question_generator", END)
    graph.add_edge("answer_evaluator", END)
    graph.add_edge("feedback_coach", END)
    graph.add_edge("summary", END)

    return graph.compile()


interview_graph = build_graph()

if __name__ == "__main__":
    state: InterviewState = {
        "role_context": "Backend engineer, 4 yrs Python/Django/FastAPI, K8s + monitoring experience",
        "topics_covered": [],
        "current_question": "",
        "last_answer": None,
        "conversation": [],
        "last_evaluation": {},
        "turn_count": 0,
        "max_turns": 3,
        "phase": "asking",
    }

    state = interview_graph.invoke(state)
    print(state["current_question"])

    
    state["last_answer"] = "I optimized a Python pipeline using multiprocessing, cut runtime by 50%."
    state = interview_graph.invoke(state)
    state = interview_graph.invoke(state)  # coaching pass
    print(state["conversation"][-1]["content"])
