import os
import re
import requests
from dotenv import load_dotenv
from google import genai

# Load environment variables from the .env file
load_dotenv()

# Initialize the Gemini client (it automatically picks up GEMINI_API_KEY from the environment)
client = genai.Client()

def _get_clean_website_text(url):
    """
    Fetches the website using Jina Reader API, then strips out 
    all markdown links and images so only clean plain text remains.
    """
    try:
        # Prepend the Jina Reader prefix to any URL
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "text/markdown"}
        
        response = requests.get(jina_url, headers=headers, timeout=20)
        
        if response.status_code != 200:
            return f"Failed to fetch website. Status code: {response.status_code}"
            
        raw_markdown = response.text
        
        # 1. Remove markdown images entirely: ![alt text](url) -> ""
        clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', raw_markdown)
        
        # 2. Strip link syntax but keep the inner text: [Visible Text](url) -> Visible Text
        clean_text = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', clean_text)
        
        return clean_text
    except Exception as e:
        return f"Error fetching URL: {str(e)}"
