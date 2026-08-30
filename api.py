import os
import re
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from utils import get_resume_text, validate_drive_url

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
    job_description: str = Field(..., min_length=1)
    feedback: str = ""


@app.get("/health")
def health_check():
    return {"status": "ok"}


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
def generate_resume(request: ResumeRequest):
    source = request.resume_url or request.resume_path or os.getenv("RESUME_SOURCE")
    if not source:
        raise HTTPException(status_code=400, detail="Provide a resume URL or resume path.")

    try:
        resume_text = get_resume_text(source)
    except Exception as exc:  # pragma: no cover - surfaced to API caller
        raise HTTPException(status_code=400, detail=f"Could not read resume: {exc}") from exc

    job_description = request.job_description.strip()
    if not job_description:
        raise HTTPException(status_code=400, detail="Job description is required.")

    keywords = [k.strip() for k in re.split(r"[\n,;]+", job_description) if k.strip()]
    keywords = keywords[:12]
    resume_lower = resume_text.lower()
    matched = [kw for kw in keywords if kw.lower() in resume_lower]
    missing = [kw for kw in keywords if kw.lower() not in resume_lower]
    match_score = round(len(matched) / len(keywords), 2) if keywords else 0.0

    generated_resume = (
        "\\documentclass[11pt]{article}\n"
        "\\usepackage[margin=1in]{geometry}\n"
        "\\usepackage{enumitem}\n"
        "\\begin{document}\n"
        "\\section*{Tailored Profile}\n"
        "This resume has been tailored to the role using the candidate's existing experience and the provided job requirements.\n"
        "\\vspace{0.5em}\n"
        "\\textbf{Target role:} " + job_description[:180].replace("\n", " ") + "\\\n"
        "\\vspace{0.5em}\n"
        "\\textbf{Match score:} " + str(match_score) + "\\\n"
        "\\vspace{0.5em}\n"
        "\\textbf{Candidate highlights:}\\\n"
        + "\\begin{itemize}\n"
        + "\n".join(f"\\item {line.strip()}" for line in resume_text.splitlines()[:8] if line.strip())
        + "\\end{itemize}\n"
        + "\\end{document}\n"
    )

    if request.feedback:
        generated_resume += "\n% Feedback notes: " + request.feedback

    return {
        "status": "ok",
        "generated_resume": generated_resume,
        "match_score": match_score,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "resume_preview": resume_text[:2000],
        "source": source,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
