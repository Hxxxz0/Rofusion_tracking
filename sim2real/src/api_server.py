import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import types
from pathlib import Path

mock_paths = types.ModuleType("paths")

mock_paths.REAL_G1_ROOT = Path(__file__).resolve().parents[1]
mock_paths.ASSETS_DIR = mock_paths.REAL_G1_ROOT / "assets"
mock_paths.ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def safe_to_assets_path(rel):
    p = Path(rel)
    return p if p.is_absolute() else (mock_paths.ASSETS_DIR / p)
    
mock_paths.to_assets_path = safe_to_assets_path

sys.modules["paths"] = mock_paths

from text_to_motion import TextToMotionClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Unitree G1 Motion API")
client = TextToMotionClient()

class MotionRequest(BaseModel):
    action_text: str

@app.post("/generate_and_play")
async def generate_and_play(req: MotionRequest):
    logger.info(f"Received motion generation request: '{req.action_text}'")
    
    try:
        filename = await client.generate_motion(req.action_text)
        
        if not filename:
            logger.error("Underlying service failed to return a motion file.")
            raise HTTPException(status_code=500, detail="Motion generation failed.")
            
        client.load_motion(filename)
        logger.info(f"Successfully generated and loaded motion: {filename}")
        
        return {
            "status": "success", 
            "message": f"Motion '{req.action_text}' successfully generated and dispatched.",
            "filename": filename
        }
        
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting Unitree G1 Motion API Server on 0.0.0.0:8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)