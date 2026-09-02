import os
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import docx
import requests
from PIL import Image
from pypdf import PdfReader


DEFAULT_RESUME_PATH = Path(r"D:\Downloads\Resume_Master_15_08.docx")


def extract_drive_file_id(value: str) -> str:
    """Return the Google Drive file ID from a Drive, Docs, or raw ID string."""
    if value is None:
        raise ValueError("No resume source provided.")

    candidate = str(value).strip()
    if not candidate:
        raise ValueError("No resume source provided.")

    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", candidate):
        return candidate

    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"}:
        if "drive.google.com" in parsed.netloc or "docs.google.com" in parsed.netloc:
            match = re.search(r"/d/([^/]+)", parsed.path)
            if match:
                return match.group(1)

            query_params = parse_qs(parsed.query)
            for key in ("id", "fileId", "resourcekey"):
                values = query_params.get(key)
                if values:
                    return values[0]

    return candidate


def _download_google_drive_file(file_id: str) -> Path:
    """Download a public Google Drive file to a temporary docx file."""
    if not file_id:
        raise ValueError("Google Drive file ID is missing.")

    drive_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(drive_url, timeout=60)
    response.raise_for_status()

    if "confirm=" in response.url:
        token = parse_qs(urlparse(response.url).query).get("confirm", [None])[0]
        if token:
            response = requests.get(
                drive_url,
                params={"confirm": token},
                timeout=60,
            )
            response.raise_for_status()

    output = Path(tempfile.gettempdir()) / f"{file_id}.docx"
    output.write_bytes(response.content)
    return output


def _resolve_resume_path(source: str | None = None) -> Path:
    """Resolve a local path, Google Drive link, or environment-based resume source."""
    candidate = (
        source
        or os.getenv("RESUME_SOURCE")
        or os.getenv("GOOGLE_DRIVE_RESUME_URL")
        or os.getenv("RESUME_URL")
        or os.getenv("RESUME_PATH")
        or str(DEFAULT_RESUME_PATH)
    )

    candidate = str(candidate).strip()
    if not candidate:
        raise ValueError("No resume source is configured.")

    if candidate.startswith(("http://", "https://")):
        file_id = extract_drive_file_id(candidate)
        if "docs.google.com" in candidate:
            export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            response = requests.get(export_url, timeout=60)
            response.raise_for_status()
            output = Path(tempfile.gettempdir()) / f"{file_id}.docx"
            output.write_bytes(response.content)
            return output
        return _download_google_drive_file(file_id)

    resolved = Path(candidate).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"Resume file not found: {resolved}")
    return resolved


def validate_drive_url(source: str) -> dict:
    """Check whether a Google Drive or Google Docs URL is public and downloadable."""
    if not source:
        raise ValueError("No resume source provided.")

    candidate = str(source).strip()
    if not candidate.startswith(("http://", "https://")):
        raise ValueError("A Google Drive URL is required for validation.")

    file_id = extract_drive_file_id(candidate)
    if not file_id:
        raise ValueError("Could not extract a Google Drive file ID.")

    if "docs.google.com" in candidate:
        export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
        response = requests.get(export_url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        return {
            "valid": response.status_code == 200,
            "file_id": file_id,
            "source": candidate,
            "status": "ok",
            "message": "Google Docs URL is valid and downloadable.",
            "content_type": response.headers.get("Content-Type", ""),
        }

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(download_url, timeout=30, allow_redirects=True)
    response.raise_for_status()
    return {
        "valid": response.status_code == 200,
        "file_id": file_id,
        "source": candidate,
        "status": "ok",
        "message": "Google Drive URL is valid and downloadable.",
        "content_type": response.headers.get("Content-Type", ""),
    }


def _normalize_text(value: str) -> str:
    """Normalize extracted text by stripping empty lines and keeping ASCII-safe output."""
    if not value:
        return ""
    lines = [line.strip() for line in str(value).splitlines() if line.strip()]
    return "\n".join(lines)


def extract_uploaded_format_text(source: str | Path) -> str:
    """Extract readable text from a pasted or uploaded format sample file."""
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Format file not found: {path}")

    suffix = path.suffix.lower()

    if suffix in {".tex", ".latex", ".txt"}:
        return _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))

    if suffix == ".docx":
        doc = docx.Document(str(path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return _normalize_text("\n".join(paragraphs))

    if suffix == ".doc":
        return f"Legacy DOC file uploaded: {path.name}. This environment supports DOCX, PDF, LaTeX, and image uploads; legacy DOC text extraction may require an external converter."

    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
        return _normalize_text("\n".join(pages))

    if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
        try:
            with Image.open(path) as image:
                width, height = image.size
                return (
                    f"Image upload: {path.name} | dimensions: {width}x{height}. "
                    "OCR support is not available in this environment, so the image was accepted as a format reference only."
                )
        except Exception as exc:
            return f"Image upload: {path.name}. Could not read image metadata: {exc}"

    try:
        return _normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return f"Format file accepted: {path.name}. This file type was uploaded successfully but cannot be parsed automatically in the current backend setup."


def get_resume_text(source: str | None = None) -> str:
    """Read the candidate resume text from a local file or public Google Drive URL."""
    resume_path = _resolve_resume_path(source)

    doc = docx.Document(str(resume_path))
    clean_paragraphs = [
        para.text.encode("ascii", "ignore").decode("ascii")
        for para in doc.paragraphs
        if para.text.strip()
    ]
    return "\n".join(clean_paragraphs)