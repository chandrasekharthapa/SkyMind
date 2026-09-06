"""Structured JSON Report Generator for SkyMind Evaluation Platform."""

import json
from typing import Dict, Any


def generate_json_report(summary: Dict[str, Any], pretty: bool = True) -> str:
    """Generates structured JSON representation of evaluation results."""
    if pretty:
        return json.dumps(summary, indent=2)
    return json.dumps(summary)
