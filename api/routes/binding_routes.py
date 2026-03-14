import logging
import json
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from core.device_manager import get_device_manager
from engine.binding_distiller import BindingDistiller
from engine.actions.ui_actions import dumpNodeXml
from engine.models.runtime import ExecutionContext

logger = logging.getLogger(__name__)
router = APIRouter()

class AnalyzeRequest(BaseModel):
    device_id: int
    cloud_id: int = 1
    app_name: str
    known_states: List[str] = []
    xml_filter: Optional[dict] = None

class BindingRecord(BaseModel):
    state_id: str
    features: List[str]
    # We might add more metadata here if needed

class DraftRequest(BaseModel):
    app_name: str
    records: List[BindingRecord]

def get_distiller():
    return BindingDistiller()

@router.post("/analyze")
async def analyze_ui(req: AnalyzeRequest, distiller: BindingDistiller = Depends(get_distiller)):
    device_manager = get_device_manager()
    try:
        info = device_manager.get_device_info(req.device_id)
        # Find the specific cloud machine
        cloud = next((c for c in info.get("cloud_machines", []) if c.get("cloud_id") == req.cloud_id), None)
        if not cloud:
            raise HTTPException(status_code=404, detail=f"Cloud {req.cloud_id} not found for device {req.device_id}")
        
        ctx = ExecutionContext(payload={
            "device_ip": info.get("ip"),
            "rpa_port": cloud.get("rpa_port")
        })
        
        # 1. Capture XML
        result = dumpNodeXml({"dump_all": True}, ctx)
        if not result.ok:
            raise HTTPException(status_code=500, detail=f"Capture failed: {result.message}")
        
        xml = result.data.get("xml", "")
        
        # 2. Analyze with LLM
        analysis = distiller.analyze_ui_state(
            xml=xml,
            app_name=req.app_name,
            known_states=req.known_states,
            xml_filter=req.xml_filter
        )
        
        return {
            "ok": True,
            "xml": xml,
            "analysis": analysis
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to analyze UI state")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/draft")
async def draft_code(req: DraftRequest, distiller: BindingDistiller = Depends(get_distiller)):
    try:
        records_raw = [r.model_dump() for r in req.records]
        code = distiller.generate_binding_code(req.app_name, records_raw)
        return {
            "ok": True,
            "code": code
        }
    except Exception as e:
        logger.exception("Failed to generate binding code")
        raise HTTPException(status_code=500, detail=str(e))
