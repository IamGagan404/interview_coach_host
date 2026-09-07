"""
FastAPI service for the AI Interview Prep Coach.

Endpoints:
  POST /interview/start              -> creates a session, returns first question
  POST /interview/{id}/answer        -> submits an answer, returns evaluation + coaching (+ next question if not done)
  GET  /interview/{id}/transcript    -> full conversation so far
"""

import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from db_handlers import init_db,save_session,load_session,session_exists
from interview_graph import interview_graph, InterviewState

app = FastAPI(title="Interview Coach API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# sessions: dict[str, InterviewState] = {}


class StartRequest(BaseModel):
    role_context: str
    max_turns: int = 5


class AnswerRequest(BaseModel):
    answer: str


@app.on_event("startup")
def startup():
    init_db()

@app.post("/interview/start")
async def start_interview(req: StartRequest):
    session_id = str(uuid.uuid4())
    state: InterviewState = {
        "role_context": req.role_context,
        "topics_covered": [],
        "current_question": "",
        "last_answer": None,
        "conversation": [],
        "last_evaluation": {},
        "turn_count": 0,
        "max_turns": req.max_turns,
        "phase": "asking",
    }
    state = interview_graph.invoke(state)
    # sessions[session_id] = state
    save_session(session_id,state)
    return {"session_id": session_id, "question": state["current_question"]}


@app.post("/interview/{session_id}/answer")
async def submit_answer(session_id: str, req: AnswerRequest):
    # if session_id not in sessions:
    #     raise HTTPException(404, "session not found")
    if not session_exists(session_id):
        raise HTTPException(404,"Session not found.")

    # state = sessions[session_id]
    state = load_session(session_id)
    if state["phase"] == "done":
        return {"status": "done", "message": "Session already complete. Fetch /transcript for the summary."}

    state["last_answer"] = req.answer
    state = interview_graph.invoke(state)   # evaluator
    state = interview_graph.invoke(state)   # coach

    # sessions[session_id] = state
    save_session(session_id,state)

    response = {
        "evaluation": state["last_evaluation"],
        "feedback": state["conversation"][-1]["content"],
        "status": state["phase"],
    }

    if state["phase"] == "asking":
        state = interview_graph.invoke(state)  # get next question
        # sessions[session_id] = state
        save_session(session_id,state)
        response["next_question"] = state["current_question"]
    elif state["phase"] == "done":
        state = interview_graph.invoke(state)  # run summary node
        # sessions[session_id] = state
        save_session(session_id,state)
        response["summary"] = state["conversation"][-1]["content"]

    return response


@app.get("/interview/{session_id}/transcript")
async def get_transcript(session_id: str):
    if not session_exists(session_id):
        raise HTTPException(404,"Session not found.")
    state = load_session(session_id)
    if state is None:
        raise HTTPException(404,"session not found")
    # return {"transcript": sessions[session_id]["conversation"]}
    return {"transcript": state["conversation"]}

