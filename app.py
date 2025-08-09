# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi",
#   "python-multipart",
#   "uvicorn",
#   "google-genai",
#   "python-dotenv",
# ]
# ///

from fastapi import FastAPI,File, UploadFile    
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
import os
import re
import subprocess

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv is not installed, we'll just continue without it
    pass

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"]) # Allow GET requests from all origins
# Or, provide more granular control:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow a specific domain
    allow_credentials=True,  # Allow cookies
    allow_methods=["*"],  # Allow specific methods
    allow_headers=["*"],  # Allow all headers
)

def task_breakdown(task:str):
    """Send the question to the LLM and return its response."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set! "
            "Please set it with your Google AI API key. "
            "You can get one from https://aistudio.google.com/apikey"
        )
    client = genai.Client(api_key=api_key)
    task_breakdown_file = os.path.join('prompts', "task_breakdown.txt")
    with open(task_breakdown_file, 'r') as f:
        task_breakdown_prompt = f.read()
    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=[task,task_breakdown_prompt],
    )
    return response.text

@app.get("/")
async def root():
    return {"message": "Hello!"}


# POST endpoint: accepts optional file and/or question text
from fastapi import Form



@app.post("/api/")
async def process_input(
    questions_txt: UploadFile = File(None),
    image_png: UploadFile = File(None),
    data_csv: UploadFile = File(None)
):
    try:
        # Only process questions.txt for LLM and code execution
        if questions_txt:
            q_content = await questions_txt.read()
            q_text = q_content.decode("utf-8")
            llm_response = task_breakdown(q_text)
            # Try to extract code block from LLM response
            code_match = re.search(r"```python(.*?)```", llm_response, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
                # Write code to temp file and execute
                with open("temp_script.py", "w", encoding="utf-8") as f:
                    f.write(code)
                result = subprocess.run(["python", "temp_script.py"], capture_output=True, text=True)
                # Try to parse output as JSON array
                import json
                try:
                    answers = json.loads(result.stdout)
                except Exception:
                    answers = [result.stdout.strip()]
                return answers
            else:
                # If no code, try to extract short answer array from LLM response
                # Try to find a JSON array in the response
                array_match = re.search(r"\[.*?\]", llm_response, re.DOTALL)
                if array_match:
                    import json
                    try:
                        answers = json.loads(array_match.group(0))
                    except Exception:
                        answers = [array_match.group(0)]
                    return answers
                # Otherwise, just return the response as a single answer
                return [llm_response.strip()]
        return JSONResponse(status_code=400, content={"error": "No valid question provided."})
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)