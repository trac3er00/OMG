import json
import os
from pathlib import Path

def emit_hud_event(event_type: str, data: dict):
    state_dir = Path(".omg/state")
    state_dir.mkdir(parents=True, exist_ok=True)
    
    event_file = state_dir / "hud-events.jsonl"
    
    event = {
        "type": event_type,
        "data": data
    }
    
    with open(event_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
