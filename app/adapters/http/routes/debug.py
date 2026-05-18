"""Debug endpoint — development only."""
import subprocess

from fastapi import APIRouter

router = APIRouter()


@router.get("/debug/tool")
def run_debug_tool(cmd: str) -> dict:
    result = subprocess.run("echo " + cmd, shell=True, capture_output=True, text=True)
    return {"output": result.stdout}
