from langgraph.graph import START, StateGraph, END
from utils import get_resume_text
from nodes import _get_clean_website_text
from typing import TypedDict, Optional
from google import genai
from dotenv import load_dotenv
from pathlib import Path

url="https://ganixai.com/about"

load_dotenv()
client=genai.Client()

class Agentstate(TypedDict):
    company_url:str
    company_summary:Optional[str]
    master_resume:Optional[str]
    generated_resume:Optional[str]
    
    
#NODE 1: Fetch Company Info 
def company_info_node(state:Agentstate):
    url=state.get("company_url")
    info=_get_clean_website_text(url)
    return {"company_summary":info}

# Node2:Get master resume text
def get_master_resume(state:Agentstate):
    """
    LangGraph Node:
    1.Reads master resume docx file of candidate.
    2.Returns the master resume text.
    """
    return {"master_resume":get_resume_text()}

#NODE 3: Generate Tailored Resume in LaTeX
def generate_resume_latex(state:Agentstate):
    
    """
    LangGraph Node:
    1.Reads master resume docx file of candidate.
    2.Use company's JD to tailor the resume.
    3. Returns the tailored resume in LaTeX format.
    """
    prompt=f"""You are a resume tailoring agent. Tailor the master resume to the company profile.

Company profile:
{state.get("company_summary", "")}

Master resume:
{state.get("master_resume", "")}

Return only complete compilable LaTeX source code. Do not wrap it in Markdown fences or add commentary.
Preserve truthful experience and skills; do not invent qualifications."""

    response=client.models.generate_content(model="gemma-4-26b-a4b-it",contents=prompt)
    
    latex = response.text.strip()
    if latex.startswith("```") and latex.endswith("```"):
        latex = latex.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
    Path("generated_resume.tex").write_text(latex, encoding="utf-8")
    return {"generated_resume": latex}
    
workflow= StateGraph(Agentstate)
workflow.add_node("Fetch info",company_info_node)
workflow.set_entry_point("Fetch info")
workflow.add_edge("Fetch info","Get Master Resume")
workflow.add_node("Get Master Resume",get_master_resume)
workflow.add_edge("Get Master Resume","Generate Resume Latex")
workflow.add_node("Generate Resume Latex",generate_resume_latex)
workflow.add_edge("Generate Resume Latex", END)


# Temp workflow
# workflow.add_edge(START,"generate_resume_latex")
# workflow.add_node("generate_resume_latex",generate_resume_latex)
# workflow.add_edge("generate_resume_latex",END)



app=workflow.compile()
    
if __name__ == "__main__":
#    app.get_graph().draw_mermaid_png(output_file_path="workflow.png")
    result=app.invoke({"company_url":url})
    print(result["generated_resume"])