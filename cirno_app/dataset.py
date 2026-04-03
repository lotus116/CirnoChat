from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class DatasetLogger:
    def __init__(self, dataset_path: Path, feedback_path: Path) -> None:
        self.dataset_path = dataset_path
        self.feedback_path = feedback_path

    def _normalize_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        expected_role = "user"

        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            if role != expected_role:
                continue
            normalized.append({"role": role, "content": content})
            expected_role = "assistant" if expected_role == "user" else "user"

        if len(normalized) >= 2 and normalized[-1]["role"] == "assistant":
            return normalized
        return []

    def log_sample(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        metadata: dict,
    ) -> str:
        sample_id = uuid4().hex
        clean_messages = self._normalize_messages(messages)
        payload = {
            "sample_id": sample_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "messages": clean_messages,
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
