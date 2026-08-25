import docx

def get_resume_text():
    doc_name = "Resume_Master_15_08.docx"
    dir_path = rf"D:\Downloads\{doc_name}"
    doc = docx.Document(dir_path)
    clean_paragraphs = [
        para.text.encode("ascii", "ignore").decode("ascii") 
        for para in doc.paragraphs 
        if para.text.strip()
    ]
    return "\n".join(clean_paragraphs)