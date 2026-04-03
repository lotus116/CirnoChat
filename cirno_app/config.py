from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _first_env(names: list[str], default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


@dataclass
class AppSettings:
    api_key: str
    base_url: str
    model_name: str
    user_name: str
    data_dir: Path
    db_path: Path
    dataset_path: Path
    feedback_path: Path
    max_recent_turns: int
    max_facts: int
    temperature: float
    summary_every_messages: int
    half_life_days: float
    expire_threshold: float
    show_sample_id: bool
    enable_dataset_logging: bool

    @classmethod
    def from_env(cls) -> "AppSettings":
        # Keep all runtime knobs centralized so CLI behavior is easy to tune.
        load_dotenv()
        api_key = _first_env(["OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_API_KEY"], default="ollama")

        data_dir = Path(os.getenv("DATA_DIR", "data")).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)

        db_path = data_dir / "memory.db"
        dataset_path = data_dir / "chat_samples.jsonl"
        feedback_path = data_dir / "feedback_events.jsonl"

        max_recent_turns = int(os.getenv("MAX_RECENT_TURNS", "8"))
        max_facts = int(os.getenv("MAX_FACTS", "8"))
        temperature = float(os.getenv("TEMPERATURE", "0.7"))
        summary_every_messages = int(os.getenv("SUMMARY_EVERY_MESSAGES", "6"))
        half_life_days = float(os.getenv("HALF_LIFE_DAYS", "14"))
        expire_threshold = float(os.getenv("EXPIRE_THRESHOLD", "0.25"))
        show_sample_id = os.getenv("SHOW_SAMPLE_ID", "false").strip().lower() in {"1", "true", "yes", "on"}
        enable_dataset_logging = os.getenv("ENABLE_DATASET_LOGGING", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if max_recent_turns < 1:
            raise ValueError("MAX_RECENT_TURNS 必须 >= 1")
        if max_facts < 0:
            raise ValueError("MAX_FACTS 必须 >= 0")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("TEMPERATURE 必须在 0.0 到 2.0 之间")
        if summary_every_messages < 2:
            raise ValueError("SUMMARY_EVERY_MESSAGES 必须 >= 2")
        if half_life_days <= 0:
            raise ValueError("HALF_LIFE_DAYS 必须 > 0")
        if not 0.0 <= expire_threshold <= 1.0:
            raise ValueError("EXPIRE_THRESHOLD 必须在 0.0 到 1.0 之间")

        return cls(
            api_key=api_key,
            base_url=_first_env(
                ["OPENAI_BASE_URL", "OLLAMA_BASE_URL", "DEEPSEEK_BASE_URL"],
                default="http://127.0.0.1:11434/v1",
            ),
            model_name=_first_env(
                ["OPENAI_MODEL", "OLLAMA_MODEL", "DEEPSEEK_MODEL"],
                default="qwen2.5:3b-instruct",
            ),
            user_name=os.getenv("USER_NAME", "你").strip(),
            data_dir=data_dir,
            db_path=db_path,
            dataset_path=dataset_path,
            feedback_path=feedback_path,
            max_recent_turns=max_recent_turns,
            max_facts=max_facts,
            temperature=temperature,
            summary_every_messages=summary_every_messages,
            half_life_days=half_life_days,
            expire_threshold=expire_threshold,
            show_sample_id=show_sample_id,
            enable_dataset_logging=enable_dataset_logging,
        )
