import sys
import types

import docx
import pytest

from utils import extract_drive_file_id, extract_uploaded_format_text


def test_graph_uses_langsmith_gemini_wrapper(monkeypatch):
    import google.genai as google_genai
    import langsmith
    from langsmith import wrappers as langsmith_wrappers

    raw_client = object()
    wrapped_client = object()

    def fake_wrap_gemini(client):
        assert client is raw_client
        return wrapped_client

    monkeypatch.setattr(google_genai, "Client", lambda: raw_client)
    monkeypatch.setattr(langsmith_wrappers, "wrap_gemini", fake_wrap_gemini, raising=False)
    sys.modules.pop("graph", None)

    import graph

    assert graph.client is wrapped_client


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://drive.google.com/file/d/abcd1234/view?usp=sharing", "abcd1234"),
        ("https://drive.google.com/open?id=abcd1234&usp=sharing", "abcd1234"),
        ("https://docs.google.com/document/d/abcd1234/edit", "abcd1234"),
        ("abcd1234", "abcd1234"),
    ],
)
def test_extract_drive_file_id(value, expected):
    assert extract_drive_file_id(value) == expected


def test_extract_uploaded_format_text_tex(tmp_path):
    file_path = tmp_path / "resume.tex"
    file_path.write_text("\\section{Profile}\nSenior Python Engineer\n", encoding="utf-8")

    text = extract_uploaded_format_text(file_path)

    assert "Senior Python Engineer" in text


def test_extract_uploaded_format_text_docx(tmp_path):
    file_path = tmp_path / "resume.docx"
    document = docx.Document()
    document.add_paragraph("Python engineer with FastAPI and PostgreSQL")
    document.save(file_path)

    text = extract_uploaded_format_text(file_path)

    assert "FastAPI" in text
