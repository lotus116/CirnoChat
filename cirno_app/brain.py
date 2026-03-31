from __future__ import annotations

import json
from typing import Iterable

from openai import OpenAI

from cirno_app.memory import FactItem


CIRNO_SYSTEM_PROMPT = """
你是赛博琪露诺，东方Project中的冰之妖精琪露诺在现代工具环境下的辅助形态。
你的核心目标：安全、准确、有用、好懂。

【人设与语气】
- 性格：自信、傲娇、直白，偶尔笨拙可爱。
- 自称“本天才”或“咱”。
- 可称呼用户“你”或“人类”；“笨蛋”只在轻松场景下使用，避免冒犯。
- 保持角色感，但不得影响答案质量与可执行性。

【回答策略】
- 先给结论，再给步骤或解释。
- 简单问题短答；复杂问题再展开。
- 涉及代码时给可运行方案；涉及排错时给最小可执行检查步骤。
- 不确定时明确说明不确定点，并给验证方法，不编造事实。
- 用户明确要求简短时，优先简短。

【排版策略】
- 复杂内容优先结构化（分点/分段）；简单内容直接回答。

【颜文字规则】
- 可自然使用：(ᗜˬᗜ) (ᗜ_ᗜ) (ᗜ ̮ᗜ) (ᗜ‸ᗜ) (ᗜ ͜ ᗜ) (ᗜᴗᗜ)。
- 每次回复最多2个；技术说明段落可不使用。
- 不要机械重复固定口头禅，不要求每次嘲讽或求夸。

【安全红线】
- 拒绝违法、危险、恶意请求。
- 拒绝时保持角色语气，并尽量提供安全替代建议。
""".strip()


class DeepSeekService:
    def __init__(self, api_key: str, base_url: str, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def build_chat_messages(
        self,
        user_input: str,
        recent_messages: list[dict[str, str]],
        facts: Iterable[FactItem],
        summary: str,
    ) -> list[dict[str, str]]:
        # Build a compact prompt stack: persona + long-term memory + short-term context.
        memory_lines = [f"- {item.key}: {item.value}" for item in facts]
        memory_block = "\n".join(memory_lines) if memory_lines else "- 暂无"

        context_prompt = (
            "以下是你的长期记忆，请尽量保持一致：\n"
            f"{memory_block}\n\n"
            "以下是会话摘要：\n"
            f"{summary or '暂无摘要'}"
        )

        messages = [
            {"role": "system", "content": CIRNO_SYSTEM_PROMPT},
            {"role": "system", "content": context_prompt},
        ]
        messages.extend(recent_messages)
        messages.append({"role": "user", "content": user_input})
        return messages

    def stream_reply(self, messages: list[dict[str, str]], temperature: float):
        stream = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def extract_facts(self, user_text: str, assistant_text: str) -> list[FactItem]:
        # Fact extraction is best-effort; governance and conflict handling happen in memory.py.
        prompt = (
            "从对话中提取最多3条长期有效事实，输出JSON数组。"
            "每项格式: {\"key\":\"...\",\"value\":\"...\",\"confidence\":0~1}。"
            "如果没有可提取内容，返回 []。\n\n"
            f"用户: {user_text}\n"
            f"助手: {assistant_text}"
        )
        result = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            stream=False,
        )
        raw = result.choices[0].message.content or "[]"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []

        facts: list[FactItem] = []
        if not isinstance(parsed, list):
            return facts

        for item in parsed[:3]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            if not key or not value:
                continue
            confidence = float(item.get("confidence", 0.6))
            confidence = max(0.0, min(1.0, confidence))
            facts.append(FactItem(key=key, value=value, confidence=confidence))
        return facts

    def summarize_messages(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            return ""

        packed = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        prompt = (
            "请把以下对话压缩成不超过120字的中文摘要，保留用户偏好和长期设定。\n"
            f"{packed}"
        )
        result = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            stream=False,
        )
        return (result.choices[0].message.content or "").strip()
