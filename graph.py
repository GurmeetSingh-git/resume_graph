import json
import itertools
import mimetypes
import sys
import threading
import time
from pathlib import Path
from typing import TypedDict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

try:
    from langsmith.wrappers import wrap_gemini
except ImportError:  # pragma: no cover - optional dependency for LangSmith tracing
    wrap_gemini = None

from utils import get_resume_text

url = "https://ganixai.com/about"

load_dotenv()


def _build_gemini_client():
    """Return a Gemini client wrapped for LangSmith tracing when available."""
    client = genai.Client()
    if wrap_gemini is not None:
        return wrap_gemini(client)
    return client


client = _build_gemini_client()
MODEL_CONFIG = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
)

MAX_ITERATIONS = 3
KEYWORD_MATCH_THRESHOLD = 0.85  # 85% of JD keywords must appear in resume


class Agentstate(TypedDict):
    company_url: str
    company_summary: Optional[str]
    company_jd: Optional[str]
    jd_keywords: Optional[list]
    matched_keywords: Optional[list]
    missing_keywords: Optional[list]
    match_score: Optional[float]
    master_resume: Optional[str]
    generated_resume: Optional[str]
    human_feedback: Optional[str]
    eligibility_status: Optional[str]
    eligibility_reason: Optional[str]
    iterations: int
    format_reference_text: Optional[str]
    format_reference_file_path: Optional[str]


# NODE 0: Ask human for the JD first (pauses graph at the very start)
def get_jd_from_human(state: Agentstate):
    """
    LangGraph Node:
    Pauses at the start and asks the human to paste the job description.
    """
    jd = interrupt({"message": "Paste the company's job description (JD) to tailor the resume against."})
    return {"company_jd": jd}


# NODE 1: Extract keywords from the JD
def extract_jd_keywords(state: Agentstate):
    """
    LangGraph Node:
    Extracts core hard-skill / tool / qualification keywords from the JD.
    """
    prompt = f"""Extract the key hard skills, tools, technologies, and qualifications from this job description.

Job description:
{state.get("company_jd", "")}

Return ONLY a JSON array of short keyword strings, nothing else. Example: ["Python", "AWS", "5+ years experience", "REST APIs"]"""

    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it", contents=prompt, config=MODEL_CONFIG
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        keywords = json.loads(text)
    except Exception:
        keywords = [k.strip() for k in text.split(",") if k.strip()]

    return {"jd_keywords": keywords}


# NODE 2: Get master resume text
def get_master_resume(state: Agentstate):
    """
    LangGraph Node:
    1. Reads master resume docx file of candidate.
    2. Returns the master resume text.
    """
    return {"master_resume": get_resume_text()}


def _build_llm_contents(prompt: str, state: Agentstate):
    """Attach uploaded format files as direct multimodal inputs to the LLM prompt."""
    parts = [prompt]
    file_path = state.get("format_reference_file_path")
    file_text = state.get("format_reference_text")

    if file_path:
        path = Path(file_path)
        if path.exists():
            mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            try:
                data = path.read_bytes()
                if data:
                    parts.append(types.Part.from_bytes(data=data, mime_type=mime_type, filename=path.name))
            except Exception:
                pass

    if file_text and not file_path:
        parts.append(file_text)

    return parts


# NODE 3: Generate tailored resume in LaTeX
def generate_resume_latex(state: Agentstate):
    """
    LangGraph Node:
     1. Tailors the master resume to the JD.
     2. Incorporates human feedback and/or missing JD keywords on retries.
     3. Returns the tailored resume in LaTeX format.
    """
    feedback_note = state.get("human_feedback") or ""
    missing = state.get("missing_keywords") or []

    feedback_block = ""
    if feedback_note:
        feedback_block += f"\n\nHuman feedback to incorporate:\n{feedback_note}"
    if missing:
        feedback_block += f"\n\nThese JD keywords are missing or underrepresented — weave in truthfully wherever applicable:\n{', '.join(missing)}"

    prompt = f"""You are a resume tailoring agent. Tailor the master resume to the job description below.

Job description:
{state.get("company_jd", "")}

Master resume:
{state.get("master_resume", "")}
{feedback_block}

Return only complete compilable LaTeX source code. Do not wrap it in Markdown fences or add commentary.
Preserve truthful experience and skills; do not invent qualifications."""

    contents = _build_llm_contents(prompt, state)
    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it", contents=contents, config=MODEL_CONFIG
    )

    latex = response.text.strip()
    if latex.startswith("```") and latex.endswith("```"):
        latex = latex.split("\n", 1)[1].rsplit("\n", 1)[0].strip()

    from pathlib import Path
    Path("generated_resume.tex").write_text(latex, encoding="utf-8")

    return {"generated_resume": latex}


# NODE 4: Evaluate resume vs JD via keyword overlap
def evaluate_match(state: Agentstate):
    """
    LangGraph Node:
    Checks how many JD keywords actually appear in the generated resume.
    """
    keywords = state.get("jd_keywords") or []
    resume_text = (state.get("generated_resume") or "").lower()

    matched, missing = [], []
    for kw in keywords:
        if kw.lower() in resume_text:
            matched.append(kw)
        else:
            missing.append(kw)

    score = len(matched) / len(keywords) if keywords else 0.0

    return {
        "matched_keywords": matched,
        "missing_keywords": missing,
        "match_score": score,
        "iterations": state.get("iterations", 0) + 1,
    }


def assess_improvement(state: Agentstate):
    """Check hard requirements before deciding whether another generation is useful."""
    prompt = f"""Assess this candidate against the job description.

Job description:
{state.get("company_jd", "")}

Master resume:
{state.get("master_resume", "")}

Missing or unmatched keywords:
{", ".join(state.get("missing_keywords") or [])}

Treat explicit minimum years of experience, mandatory qualifications, and other clearly stated hard requirements as eligibility gates.
Mark not_eligible when the master resume does not show those requirements, even if the technical keyword match is high.
Mark eligible only when all hard requirements are met and any remaining gaps can be represented more clearly using experience already present in the master resume.
Return ONLY valid JSON in this format: {{"eligible": true, "reason": "short explanation"}}"""

    response = client.models.generate_content(
        model="gemma-4-26b-a4b-it", contents=prompt, config=MODEL_CONFIG
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        decision = json.loads(text)
    except json.JSONDecodeError:
        decision = {"eligible": False, "reason": "Eligibility assessment returned invalid data."}

    eligible = decision.get("eligible") is True
    return {
        "eligibility_status": "eligible" if eligible else "not_eligible",
        "eligibility_reason": decision.get("reason", "No reason provided."),
    }


def route_after_match(state: Agentstate):
    return "Assess Improvement"


def route_after_eligibility(state: Agentstate):
    if state.get("eligibility_status") != "eligible":
        return "Not eligible"
    if state.get("match_score", 0) >= KEYWORD_MATCH_THRESHOLD:
        return "Human Review"
    if state.get("iterations", 0) >= MAX_ITERATIONS:
        return "Human Review"
    return "Generate Resume Latex"


# NODE 5: Pause for human review
def human_review(state: Agentstate):
    """
    LangGraph Node:
    Pauses the graph and waits for the human to approve or request tweaks.
    """
    feedback = interrupt({
        "generated_resume": state.get("generated_resume"),
        "match_score": state.get("match_score"),
        "missing_keywords": state.get("missing_keywords"),
        "message": "Review the resume. Reply 'approve' to finish, or describe changes.",
    })
    return {"human_feedback": feedback}


def route_after_human(state: Agentstate):
    feedback = (state.get("human_feedback") or "").strip().lower()
    if feedback in ("approve", "approved", "ok", "looks good"):
        return END
    return "Generate Resume Latex"


# ---- Build the graph ----
workflow = StateGraph(Agentstate)

workflow.add_node("Get JD", get_jd_from_human)
workflow.set_entry_point("Get JD")
workflow.add_edge("Get JD", "Extract JD Keywords")

workflow.add_node("Extract JD Keywords", extract_jd_keywords)
workflow.add_edge("Extract JD Keywords", "Get Master Resume")

workflow.add_node("Get Master Resume", get_master_resume)
workflow.add_edge("Get Master Resume", "Generate Resume Latex")

workflow.add_node("Generate Resume Latex", generate_resume_latex)
workflow.add_edge("Generate Resume Latex", "Evaluate Match")

workflow.add_node("Evaluate Match", evaluate_match)
workflow.add_conditional_edges(
    "Evaluate Match",
    route_after_match,
    {"Human Review": "Human Review", "Assess Improvement": "Assess Improvement"},
)

workflow.add_node("Assess Improvement", assess_improvement)
workflow.add_conditional_edges(
    "Assess Improvement",
    route_after_eligibility,
    {
        "Not eligible": END,
        "Human Review": "Human Review",
        "Generate Resume Latex": "Generate Resume Latex",
    },
)

workflow.add_node("Human Review", human_review)
workflow.add_conditional_edges(
    "Human Review",
    route_after_human,
    {END: END, "Generate Resume Latex": "Generate Resume Latex"},
)

checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer)


def invoke_with_progress(input_value, config):
    completed = threading.Event()

    def show_progress():
        for spinner_character in itertools.cycle("|/-\\"):
            if completed.is_set():
                break
            sys.stdout.write(f"\rProcessing {spinner_character}")
            sys.stdout.flush()
            time.sleep(0.15)

    progress_thread = threading.Thread(target=show_progress, daemon=True)
    progress_thread.start()
    try:
        return app.invoke(input_value, config=config)
    finally:
        completed.set()
        progress_thread.join()
        sys.stdout.write("\rProcessing complete.\n")
        sys.stdout.flush()


def read_job_description():
    print("\nPaste the full JD below. Type END on a new line when finished.")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            return "\n".join(lines).strip()
        lines.append(line)


if __name__ == "__main__":
    # Uncomment to visualize the graph:
    # app.get_graph().draw_mermaid_png(output_file_path="workflow.png")

    config = {"configurable": {"thread_id": "resume-session-1"}}

    result = invoke_with_progress({"company_url": url, "iterations": 0}, config)

    while "__interrupt__" in result:
        info = result["__interrupt__"][0].value
        print("\n" + info["message"])
        if "generated_resume" in info:
            print("\n--- Current resume (preview) ---")
            print(info["generated_resume"][:500])
            print(f"\nMatch score: {info.get('match_score')}")
            print(f"Missing keywords: {info.get('missing_keywords')}")
        if "generated_resume" in info:
            user_input = input("\nYour response: ")
        else:
            user_input = read_job_description()
        result = invoke_with_progress(Command(resume=user_input), config)

    if result.get("eligibility_status") == "not_eligible":
        print("\n--- Not eligible ---")
        print(result.get("eligibility_reason"))
        raise SystemExit

    print("\n--- Final resume ---")
    print(result.get("generated_resume"))
    print("\nMatch score:", result.get("match_score"))
    print("Missing keywords:", result.get("missing_keywords"))