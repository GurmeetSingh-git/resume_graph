import os
import re
import json
import mimetypes
from typing import Optional

import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from langsmith.wrappers import wrap_gemini
except ImportError:  # pragma: no cover - optional dependency for LangSmith tracing
    wrap_gemini = None

from utils import extract_uploaded_format_text, get_resume_text, validate_drive_url

load_dotenv()

app = FastAPI(title="Resume Graph API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResumeRequest(BaseModel):
    resume_url: Optional[str] = None
    resume_path: Optional[str] = None
    format_reference: Optional[str] = None
    format_file_name: Optional[str] = None
    job_description: str = Field(..., min_length=1)
    feedback: str = ""
    added_skills: list[str] = []


def _build_gemini_client():
    client = genai.Client()
    if wrap_gemini is not None:
        return wrap_gemini(client)
    return client


client = _build_gemini_client()
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-26b-a4b-it")
SKILLS_EXTRACTION_MODEL = os.getenv("SKILLS_EXTRACTION_MODEL", DEFAULT_MODEL)
RESUME_GENERATION_MODEL = os.getenv("RESUME_GENERATION_MODEL", "gemini-3.8-flash")
HR_EVALUATION_MODEL = os.getenv("HR_EVALUATION_MODEL", DEFAULT_MODEL)
MODEL_CONFIG = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _extract_job_skills(job_description: str):
    prompt = f"""Extract only concise, meaningful skills from this job description.

Include technical skills (languages, frameworks, cloud platforms, databases, tools, methodologies) and non-technical professional skills (communication, leadership, ownership, collaboration).
Do not return sentences, company names, locations, benefits, job titles, experience ranges, or product descriptions.
Use one skill per item, normally 1-4 words. Return ONLY valid JSON in this format:
{{"technical": ["Python"], "non_technical": ["Technical communication"]}}

Job description:
{job_description}"""
    response = client.models.generate_content(
        model=SKILLS_EXTRACTION_MODEL, contents=prompt, config=MODEL_CONFIG
    )
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        extracted = json.loads(text)
    except json.JSONDecodeError:
        extracted = {}
    technical = extracted.get("technical", []) if isinstance(extracted, dict) else []
    non_technical = extracted.get("non_technical", []) if isinstance(extracted, dict) else []
    skills = [str(skill).strip() for skill in [*technical, *non_technical] if str(skill).strip()]
    return list(dict.fromkeys(skills))[:20]


def _get_keyword_match(resume_text: str, job_description: str, added_skills=None, job_skills=None):
    keywords = job_skills or _extract_job_skills(job_description)
    keywords = list(dict.fromkeys(keywords + [skill.strip() for skill in (added_skills or []) if skill.strip()]))[:20]
    resume_lower = resume_text.lower()
    matched = [kw for kw in keywords if kw.lower() in resume_lower]
    missing = [kw for kw in keywords if kw.lower() not in resume_lower]
    match_score = round(len(matched) / len(keywords), 2) if keywords else 0.0
    return keywords, matched, missing, match_score


def _load_resume_source(source: str | None):
    if not source:
        raise HTTPException(status_code=400, detail="Provide a resume URL or resume path.")
    try:
        return get_resume_text(source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read resume: {exc}") from exc


def _evaluate_resume_as_hr(job_description: str, generated_resume: str):
    prompt = f"""Act as a harsh but fair senior HR evaluator for this job application.

Decide whether you would pass this resume to the next hiring stage based only on the job description and resume below. Identify the low-lying areas that would reduce the chance of passing. Distinguish a true missing qualification from a skill that is present but weakly evidenced. Do not request or infer information outside these two inputs.

Return ONLY valid JSON in this format:
{{
  "pass": true,
  "score": 0,
  "verdict": "short decision",
  "low_lying_areas": ["specific weakness"],
  "strengths": ["specific strength"]
}}

Job description:
{job_description}

Resume:
{generated_resume}"""
    def parse_evaluation(response):
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        evaluation = json.loads(text)
        if not isinstance(evaluation, dict):
            raise ValueError("HR evaluation was not an object")
        return {
            "pass": bool(evaluation.get("pass", False)),
            "score": evaluation.get("score"),
            "verdict": str(evaluation.get("verdict", "No verdict provided.")),
            "low_lying_areas": [str(item) for item in evaluation.get("low_lying_areas", [])],
            "strengths": [str(item) for item in evaluation.get("strengths", [])],
        }

    try:
        response = client.models.generate_content(
            model=HR_EVALUATION_MODEL, contents=prompt, config=MODEL_CONFIG
        )
        evaluation = parse_evaluation(response)
        evaluation["model"] = HR_EVALUATION_MODEL
        return evaluation
    except Exception as exc:
        return {
            "pass": False,
            "score": None,
            "verdict": "HR evaluation was unavailable. Check model quota or billing.",
            "low_lying_areas": [str(exc)],
            "strengths": [],
        }


@app.post("/api/analyze-resume")
def analyze_resume(payload: dict):
    source = (payload or {}).get("resume_url") or (payload or {}).get("resume_path") or os.getenv("RESUME_SOURCE")
    resume_text = _load_resume_source(source)
    job_description = ((payload or {}).get("job_description") or "").strip()
    if not job_description:
        raise HTTPException(status_code=400, detail="Job description is required.")

    keywords, matched, missing, match_score = _get_keyword_match(resume_text, job_description)
    return {
        "status": "ok",
        "source": source,
        "keywords": keywords,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "match_score": match_score,
        "resume_preview": resume_text[:2000],
    }


@app.post("/api/validate-drive-url")
def validate_drive_url_endpoint(payload: dict):
    url = (payload or {}).get("resume_url") or (payload or {}).get("url")
    if not url:
        raise HTTPException(status_code=400, detail="A Google Drive URL is required.")

    try:
        result = validate_drive_url(url)
        return {"valid": True, "message": result["message"], "file_id": result["file_id"]}
    except Exception as exc:
        message = str(exc).lower()
        if "401" in message or "403" in message or "access" in message or "not found" in message:
            detail = "This Google Drive/Docs file is private or not shared publicly. Please change the sharing settings to 'Anyone with the link' and try again."
        else:
            detail = f"Invalid Google Drive URL: {exc}"
        raise HTTPException(status_code=400, detail=detail) from exc


@app.post("/api/generate-resume")
async def generate_resume(request: Request):
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        payload = {
            "resume_url": form.get("resume_url"),
            "resume_path": form.get("resume_path"),
            "format_reference": form.get("format_reference"),
            "format_file_name": form.get("format_file_name"),
            "job_description": form.get("job_description"),
            "feedback": form.get("feedback"),
            "added_skills": form.get("added_skills"),
            "job_skills": form.get("job_skills"),
            "hr_feedback": form.get("hr_feedback"),
        }
        uploaded_file = form.get("format_file")
    else:
        payload = await request.json()
        uploaded_file = None

    source = payload.get("resume_url") or payload.get("resume_path") or os.getenv("RESUME_SOURCE")
    resume_text = _load_resume_source(source)

    job_description = (payload.get("job_description") or "").strip()
    if not job_description:
        raise HTTPException(status_code=400, detail="Job description is required.")

    format_reference = payload.get("format_reference")
    format_file_name = payload.get("format_file_name")

    uploaded_file_path = None
    uploaded_file_mime_type = None
    if uploaded_file is not None:
        upload_dir = Path(tempfile.gettempdir()) / "resume_graph_uploads"
        upload_dir.mkdir(exist_ok=True)
        file_name = getattr(uploaded_file, "filename", None) or str(format_file_name or "uploaded_format")
        safe_name = Path(file_name).name
        saved_path = upload_dir / safe_name
        saved_path.write_bytes(await uploaded_file.read())
        uploaded_file_path = str(saved_path)
        uploaded_file_mime_type = mimetypes.guess_type(str(saved_path))[0]
        if not format_file_name:
            format_file_name = safe_name

        extracted_format_text = extract_uploaded_format_text(saved_path)
        if extracted_format_text:
            format_reference = extracted_format_text
        elif not format_reference:
            format_reference = f"Uploaded format reference file: {safe_name}"

    feedback = (payload.get("feedback") or "").strip()
    hr_feedback = (payload.get("hr_feedback") or "").strip()
    added_skills = payload.get("added_skills") or []
    if isinstance(added_skills, str):
        try:
            added_skills = json.loads(added_skills)
        except json.JSONDecodeError:
            added_skills = [added_skills]
    job_skills = payload.get("job_skills") or []
    if isinstance(job_skills, str):
        try:
            job_skills = json.loads(job_skills)
        except json.JSONDecodeError:
            job_skills = []
    keywords, matched, missing, match_score = _get_keyword_match(
        resume_text, job_description, added_skills, job_skills
    )
    prompt = f"""Tailor the candidate's resume to the job description.

Job description:
{job_description}

Identified job keywords:
{", ".join(keywords)}

Candidate's master resume:
{resume_text}

Additional feedback:
{feedback}

Previous HR evaluation to address during this iteration:
{hr_feedback or "None"}

Skills the candidate explicitly selected as skills they have and want included:
{", ".join(added_skills) or "None"}

Format reference:
{format_reference or "None provided"}

Return only complete compilable LaTeX source code. Do not use Markdown fences or commentary.
Preserve and include all substantive sections from the master resume, especially Education, Certifications, Skills, Professional Experience, Projects, and any clearly labeled additional sections. Never omit Education or another existing section merely because it is less relevant to the job; you may reorder sections and tailor their wording while preserving truthful content.
Include every selected skill in an appropriate skills or experience section when it can be stated truthfully based on the candidate's confirmation. Do not invent employers, dates, achievements, or experience.
Create or rewrite project bullet points only from projects and evidence already present in the master resume. Use those project bullets to demonstrate relevant selected skills with concrete actions, technologies, outcomes, or responsibilities when the source supports them. Do not invent projects, tools, metrics, responsibilities, outcomes, or technical claims; if the master resume does not provide evidence for a skill, do not manufacture a project bullet for it."""

    content_parts = [types.Part.from_text(text=prompt)]
    if uploaded_file_path and uploaded_file_mime_type and uploaded_file_mime_type.startswith("image/"):
        try:
            content_parts.append(
                types.Part.from_bytes(
                    data=Path(uploaded_file_path).read_bytes(),
                    mime_type=uploaded_file_mime_type,
                )
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read format image: {exc}") from exc

    contents = [types.Content(role="user", parts=content_parts)]

    try:
        response = client.models.generate_content(
            model=RESUME_GENERATION_MODEL, contents=contents, config=MODEL_CONFIG
        )
        generated_resume = (response.text or "").strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resume generation failed: {exc}") from exc

    if not generated_resume:
        raise HTTPException(status_code=502, detail="Resume generation returned no content.")

    if generated_resume.startswith("```"):
        generated_resume = generated_resume.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    keywords, matched, missing, match_score = _get_keyword_match(
        generated_resume, job_description, added_skills, job_skills
    )
    hr_evaluation = _evaluate_resume_as_hr(job_description, generated_resume)

    return {
        "status": "ok",
        "generated_resume": generated_resume,
        "match_score": match_score,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "hr_evaluation": hr_evaluation,
        "resume_preview": resume_text[:2000],
        "source": source,
        "format_reference": format_reference,
        "format_file_name": format_file_name,
        "format_reference_file_path": uploaded_file_path,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
