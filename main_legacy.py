from dotenv import load_dotenv
import os

# Load env variables FIRST, before importing other modules that might rely on them
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from utils.logger import get_logger

# Import enhanced pipeline (with feature flag to switch between old/new)
from ai_preview_importer.preview_pipeline_v2 import run_preview_pipeline_with_feature_flag

from answer_resolution.answer_pipeline import resolve_answers
import uvicorn

# Initialize Logger
logger = get_logger("main")

app = FastAPI(title="AI PDF Importer Backend")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for now, specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"status": "ok", "service": "pdf-to-test-backend"}

@app.get("/health")
def health_check():
    """
    Health check endpoint for Railway.
    """
    return {"status": "ok"}

@app.post("/parse")
async def parse_document(file: UploadFile = File(...)):
    """
    Parses an uploaded PDF/Image and returns structured questions.
    """
    logger.info(f"Received file: {file.filename}")
    
    try:
        if not file.filename.endswith(('.pdf', '.png', '.jpg', '.jpeg')):
             raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and Images allowed.")

        file_bytes = await file.read()
        logger.info(f"File size: {len(file_bytes)} bytes")
        
        # 1. Run Enhanced Preview Pipeline (with feature flag)
        result = await run_preview_pipeline_with_feature_flag(file_bytes)
        
        # 2. Run Answer Resolution (Phase 2)
        # We enrich the questions in place
        # result["questions"] = resolve_answers(result["questions"], file_bytes)
        
        # Recalculate stats after resolution
        # result["unansweredCount"] = sum(1 for q in result["questions"] if q['needsAnswer'])
        # result["canConfirm"] = result["unansweredCount"] == 0

        logger.info("Parsing complete. Returning response.")
        return result

    except ValueError as ve:
        logger.error(f"Validation Error: {str(ve)}")
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        logger.error(f"Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error during processing")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
