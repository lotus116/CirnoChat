from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class DatasetLogger:
    def __init__(self, dataset_path: Path, feedback_path: Path) -> None:
        self.dataset_path = dataset_path
        self.feedback_path = feedback_path

    def log_sample(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        metadata: dict,
    ) -> str:
        sample_id = uuid4().hex
        payload = {
            "sample_id": sample_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "messages": messages,
            "meta": metadata,
        }
        with self.dataset_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return sample_id

    def log_feedback(
        self,
        sample_id: str,
        rating: str,
        revised_answer: str = "",
    ) -> None:
        payload = {
            "sample_id": sample_id,
            "rating": rating,
            "revised_answer": revised_answer,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self.feedback_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
