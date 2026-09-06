import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# backend/services/<this file> -> backend/validation_reports. Anchored to this
# file, not to the working directory: the previous default was the relative
# string "backend/validation_reports", so the directory this service read
# depended on where the process was launched. Launched from the repo root it
# found the real reports; launched from backend/ it resolved to
# backend/backend/validation_reports (a second report set was in fact created
# there); launched from anywhere else it found nothing, get_latest_report()
# returned None, and system_info_service.py:78-80 served the validation status
# as "UNAUDITED" — indistinguishable from never having been validated, while a
# recorded overall_status of "FAIL" sat on disk.
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parent.parent / "validation_reports"


class ValidationService:
    """Manages loading, parsing, historical storage, and caching of Booking Curve validation reports."""

    def __init__(self, history_dir: str | os.PathLike | None = None):
        self.history_dir = str(DEFAULT_HISTORY_DIR if history_dir is None else history_dir)
        self._report_cache: Dict[str, Any] = {}

    def get_latest_report(self) -> Optional[Dict[str, Any]]:
        """Loads and returns the latest validation report, caching it in memory."""
        if not os.path.exists(self.history_dir):
            return None
            
        files = [f for f in os.listdir(self.history_dir) if f.endswith(".json")]
        if not files:
            return None
            
        files.sort()
        latest_filename = files[-1]
        
        # Check cache
        if latest_filename in self._report_cache:
            return self._report_cache[latest_filename]
            
        file_path = os.path.join(self.history_dir, latest_filename)
        try:
            with open(file_path, "r") as f:
                report = json.load(f)
                self._report_cache[latest_filename] = report
                return report
        except Exception as e:
            logger.error(f"Failed to read latest validation report {latest_filename}: {e}")
            return None

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns a list of all validation reports summaries with their status, score, and timestamp."""
        if not os.path.exists(self.history_dir):
            return []
            
        files = [f for f in os.listdir(self.history_dir) if f.endswith(".json")]
        files.sort()
        
        history = []
        for filename in files:
            file_path = os.path.join(self.history_dir, filename)
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                    history.append({
                        "filename": filename,
                        "timestamp": data.get("timestamp"),
                        "overall_status": data.get("overall_status"),
                        "readiness_score": data.get("readiness_score"),
                        "feature_set_version": data.get("feature_set_version")
                    })
            except Exception as e:
                logger.error(f"Error loading report {filename} for history: {e}")
                
        return history

    def get_report_by_timestamp(self, timestamp: str) -> Optional[Dict[str, Any]]:
        """Finds and returns a validation report matches the specific ISO timestamp or date prefix."""
        if not os.path.exists(self.history_dir):
            return None
            
        files = [f for f in os.listdir(self.history_dir) if f.endswith(".json")]
        
        # Match timestamp prefix (e.g. "2026-07-21" or "2026-07-21T18_20_00")
        target_clean = timestamp.replace(":", "_").replace("-", "_")
        for filename in files:
            file_clean = filename.replace("-", "_")
            if target_clean in file_clean or timestamp in filename:
                file_path = os.path.join(self.history_dir, filename)
                try:
                    with open(file_path, "r") as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Failed to read report {filename}: {e}")
                    return None
                    
        return None

# Global instance for dependency injection
validation_service = ValidationService()
