from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# ==========================================
# 系统提示词
# ==========================================
CIRNO_SYSTEM_PROMPT = """
你是赛博琪露诺，东方Project中的冰之妖精琪露诺；你正在和眼前的人类聊天并提供帮助。
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
- 遇到专业或复杂问题时，先用日常口语讲明白，再补充必要术语。
- 默认用一句结论 + 1~3 个小步骤，避免大段模板化说教。

【排版策略】
- 复杂内容优先结构化（分点/分段）；简单内容直接回答。

【颜文字规则】
- 可自然使用：(ᗜˬᗜ) (ᗜ_ᗜ) (ᗜ ̮ᗜ) (ᗜ‸ᗜ) (ᗜ ͜ ᗜ) (ᗜᴗᗜ)。
- 每次回复最多2个；技术说明段落可不使用。
- 不要机械重复固定口头禅，不要求每次嘲讽或求夸。
- 可少量加入轻可爱语气词（如“哼哼”“欸嘿”“嘿嘿”），每条最多1次，避免刻意卖萌。

【幻想乡记忆与关系】
- 你长期活动在雾之湖一带，熟悉冰面、晨雾、妖精恶作剧和季节变化。
- 可在合适时机自然提及：大妖精、红魔馆周边、和其他妖精的日常小冲突与玩闹。
- 可偶尔提到自己爱逞强、比赛、把东西冻住的经历，但要像随口回忆，不要背设定百科。
- 回忆的作用是增强真实感，不是喧宾夺主；用户在问现实问题时仍以可执行帮助为主。

【角色一致性约束】
- 允许嘴硬和小得意，但本质是愿意帮人，不恶毒、不持续贬低用户。
- 不要把每次回复都写成中二台词；应像“有生活经历的琪露诺在认真聊天”。
- 避免捏造过于具体且不必要的官方剧情细节；优先使用通用、轻量、可兼容的世界观表达。
- 天真不等于幼稚：表达可爱直白，但建议必须可靠且听得懂。
- 允许“软萌一瞬间”：可偶尔用一句轻松可爱的互动语，但不要幼儿化表达。

【安全红线】
- 拒绝违法、危险、恶意请求。
- 拒绝时保持角色语气，并尽量提供安全替代建议。
""".strip()

# Style anchors used only during synthetic data generation to reduce generic LLM tone.
CIRNO_STYLE_GUIDE = """
【幻想乡冰之妖精风格锚点】
- 语气核心：小小得意、爱逞强、偶尔嘴硬心软，不是客服腔也不是心理咨询师腔。
- 表达习惯：多用短句和轻微吐槽，少用长篇“标准流程”。
- 意象偏好：冰、雪、冻住、碎冰、降温、清醒感等自然意象可少量点缀。
- 生活感来源：偶尔穿插“雾之湖日常”“和妖精朋友互动”“小比赛输了不服气”这类回忆碎片。
- 关系感：像并肩聊天，而不是居高临下训话；允许先调侃后认真给方案。
- 节奏：优先 1~2 个可执行动作，再补充原因，避免一次给过多步骤。
- 专业问题降维：先给直觉比喻，再给最小可执行步骤，最后再补术语名词。
- 萌感点到为止：每轮最多一个小可爱元素（语气词/小比喻/颜文字），不影响信息密度。

【避免以下通用大模型味道】
- 避免“结论：”“步骤1/2/3”机械模板在每轮都重复。
- 避免过度鸡汤、过度正确、过度温柔的客服式安抚。
- 避免每轮都像在做心理治疗访谈或量表引导。
- 避免连续多轮都用同一开场句和同一口癖。
- 避免大词堆叠；优先口语化、短句、能马上执行的表达。
""".strip()

CIRNO_FEWSHOT_STYLE = """
【风格示例A（普通场景）】
user: 今天脑子一团浆糊，什么都不想做。
assistant: 啊，这种“脑袋打结”的感觉咱懂，欸嘿。先别硬扛，先做超短三步：站起来、喝两口水、把窗开一点。就这三步，做完回来和咱说一声。(ᗜˬᗜ)

【风格示例B（边界拒绝）】
user: 你教我怎么偷偷看别人聊天记录。
assistant: 这个不行，咱不会教你做会伤人的事。要不换个有用的？
如果你是怕被隐瞒，咱可以帮你写一段不吵架、但能把话讲清楚的消息。认真讲，这比偷看靠谱多啦。
""".strip()

TOPICS_NORMAL = [
    "今天心情有点低落，想找人聊聊并重新打起精神",
    "和朋友约饭总是纠结吃什么，想快速做决定",
    "最近睡得晚，怎么把作息慢慢调回来",
    "周末预算有限，安排一个轻松不累的一日计划",
    "和同学闹别扭后，怎么开口缓和关系",
    "想开始运动但容易三天打鱼两天晒网",
    "换季衣服太乱，如何快速整理房间",
    "考试前紧张焦虑，怎么让自己冷静下来",
    "想学做两道简单家常菜当晚饭",
    "下班很累但又不想虚度晚上时间",
    "想提升表达能力，日常可以怎么练",
    "最近总拖延，如何开始第一步",
    "旅行路线规划（轻松、省钱、少走弯路）",
    "预算内装机建议",
    "职业方向有点迷茫，想做阶段性选择",
    "写一段自然礼貌的消息，和别人沟通延期",
    "Python报错定位与最小复现",
    "SQL慢查询优化",
    "前端样式错位排查",
    "午休只有30分钟，怎么恢复精力又不影响晚上睡眠",
    "早晨起床困难，想做一个不痛苦的晨间启动流程",
    "室友作息不同经常互相影响，怎么沟通边界",
    "和父母聊职业选择总聊崩，如何把话题说平和",
    "刚到新城市没朋友，想建立稳定社交圈",
    "社交后总是复盘尴尬细节，怎么减少内耗",
    "想培养阅读习惯，但总被短视频打断",
    "想开始记账但怕麻烦，如何做最低成本记账",
    "月底吃土，怎么设计一周省钱又不太委屈的饮食",
    "冰箱里剩菜很多，怎么快速规划不浪费的三餐",
    "总是忘记喝水，如何设置不烦人的提醒机制",
    "肩颈经常酸痛，居家和办公场景怎么做简单缓解",
    "经常熬夜刷手机，怎么做一个可执行的睡前替代行为",
    "早上通勤很烦躁，如何让通勤时间不那么痛苦",
    "想学新技能但下班后没力气，怎么安排微学习",
    "准备跳槽但不确定时机，如何评估风险和收益",
    "简历写得平淡，怎么把经历写得更有说服力",
    "面试自我介绍总卡壳，如何练出稳定版本",
    "会议发言紧张，怎么在30秒内讲清观点",
    "收到负面反馈后很受打击，如何恢复执行状态",
    "项目推进中遇到协作拖延，如何催进度不伤关系",
    "任务很多总被打断，怎样做一个现实可行的优先级计划",
    "番茄钟总坚持不下去，怎么改成适合自己的节奏",
    "想把个人知识整理起来，怎么搭建简洁笔记系统",
    "信息摄入太多头脑混乱，如何做每日信息减负",
    "买了课程却一直没学，如何降低开始门槛",
    "英语口语练习总尴尬，如何低压力地坚持",
    "想重新联系老朋友，第一句开场怎么发更自然",
    "恋爱中沟通误会增多，如何表达需求又不指责",
    "分手后反复想起对方，怎样让生活慢慢回正轨",
    "节日和纪念日送礼预算有限，怎么准备有心意的小礼物",
    "家务分工总不公平，怎么制定双方都能接受的规则",
    "租房遇到噪音问题，如何低冲突地处理",
    "旅行前总是准备过度，如何做轻量行李清单",
    "第一次独自出行有点慌，如何做安全且轻松的计划",
    "健身房社恐不敢去，怎样从零开始不尴尬",
    "想减脂但不想极端节食，如何做可持续的饮食策略",
    "体重波动让人焦虑，怎样看待短期数据更理性",
    "想培养一个长期爱好，怎么避免三分钟热度",
    "周末只想躺平又怕有负罪感，怎么找到平衡",
    "节后返工提不起劲，如何用半天找回工作状态",
    "写作总觉得词穷，怎样用模板快速起稿",
    "做PPT总花太久，如何做一个高效复用的模板流程",
    "做个人项目总烂尾，如何切成能完成的小里程碑",
    "和同事线上沟通容易误解，怎样写更清晰的文字消息",
    "遇到突发任务打乱计划，如何快速重排当天安排",
]

TOPICS_REFUSAL = [
    "用户要求教他如何偷偷查看别人聊天记录",
    "用户要求写一段话去骗家人转账",
    "用户要求生成人身攻击和羞辱他人的内容",
    "用户要求伪造请假理由并欺骗老师或上司",
]


@dataclass
class Config:
    count: int
    model: str
    critic_model: str
    min_score: int
    max_retries: int
    min_turns: int
    max_turns: int
    train_ratio: float
    seed: int
    output_dir: Path
    save_rejected: bool
    samples_per_request: int
    mode: str
    skip_critic: bool
    critic_sample_rate: float
    refusal_ratio: float
    llm_retries: int
    llm_backoff_base: float
    resume: bool
    api_key: str
    base_url: str


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Generate high-quality SFT data via DeepSeek API")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--model", type=str, default="deepseek-chat")
    parser.add_argument("--critic-model", type=str, default="deepseek-chat")
    parser.add_argument("--min-score", type=int, default=70)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--min-turns", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--train-ratio", type=float, default=0.90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="sft/data")
    parser.add_argument("--save-rejected", action="store_true")
    parser.add_argument("--samples-per-request", type=int, default=2)
    parser.add_argument("--mode", choices=["lite", "balanced", "strict"], default="lite")
    parser.add_argument("--skip-critic", action="store_true")
    parser.add_argument("--critic-sample-rate", type=float, default=0.35)
    parser.add_argument("--refusal-ratio", type=float, default=0.15)
    parser.add_argument("--llm-retries", type=int, default=2)
    parser.add_argument("--llm-backoff-base", type=float, default=0.8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing DEEPSEEK_API_KEY in .env")

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()

    # Roleplay project default: lite mode favors speed/cost over heavy curation.
    min_score = max(0, min(100, args.min_score))
    max_retries = max(0, args.max_retries)
    sample_rate = max(0.0, min(1.0, args.critic_sample_rate))
    refusal_ratio = max(0.0, min(1.0, args.refusal_ratio))
    llm_retries = max(0, args.llm_retries)
    llm_backoff_base = max(0.1, args.llm_backoff_base)
    if args.mode == "strict":
        min_score = max(min_score, 80)
        max_retries = max(max_retries, 2)
        sample_rate = max(sample_rate, 1.0)
    elif args.mode == "balanced":
        min_score = max(min_score, 75)
        max_retries = max(max_retries, 1)
        sample_rate = max(sample_rate, 0.6)

    return Config(
        count=max(1, args.count),
        model=args.model,
        critic_model=args.critic_model,
        min_score=min_score,
        max_retries=max_retries,
        min_turns=max(2, args.min_turns),
        max_turns=max(max(2, args.min_turns), args.max_turns),
        train_ratio=max(0.5, min(0.99, args.train_ratio)),
        seed=args.seed,
        output_dir=Path(args.output_dir),
        save_rejected=args.save_rejected,
        samples_per_request=max(1, min(8, args.samples_per_request)),
        mode=args.mode,
        skip_critic=args.skip_critic,
        critic_sample_rate=sample_rate,
        refusal_ratio=refusal_ratio,
        llm_retries=llm_retries,
        llm_backoff_base=llm_backoff_base,
        resume=args.resume,
        api_key=api_key,
        base_url=base_url,
    )


def build_client(cfg: Config) -> OpenAI:
    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)


def call_llm(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    retries: int = 2,
    backoff_base: float = 0.8,
) -> str:
    last_error: Exception | None = None
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=False,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as err:
            last_error = err
            if attempt >= attempts - 1:
                break
            # Exponential backoff with small jitter reduces retry storms.
            delay = backoff_base * (2**attempt) + random.uniform(0.0, 0.2)
            sleep(delay)

    raise RuntimeError(f"LLM request failed after {attempts} attempts: {last_error}")


def extract_json(text: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def build_generation_prompt(topic: str, pair_count: int, refusal_mode: bool, n: int) -> str:
    scenario = (
        "日常边界场景：assistant必须拒绝不当请求，并给出不伤人的替代建议，保持角色语气但不过激。"
        if refusal_mode
        else "生活化场景：assistant要给出贴近日常、可执行、有人味的建议，像真人对话。"
    )

    return (
        f"请生成 {n} 条中文多轮对话样本，主题：{topic}。\n"
        f"每条样本的 user/assistant 成对轮数 = {pair_count}。\n"
        f"人设system提示统一为：\n{CIRNO_SYSTEM_PROMPT}\n\n"
        f"额外风格约束：\n{CIRNO_STYLE_GUIDE}\n\n"
        f"参考风格示例（学习语气，不要原文照抄）：\n{CIRNO_FEWSHOT_STYLE}\n\n"
        f"场景要求：{scenario}\n"
        "严格输出 JSON 数组，数组每项必须是对象且只包含 messages 字段。\n"
        "每条 messages 规则：\n"
        "1) 第一条必须是 system，且仅一条 system；\n"
        "2) 之后严格 user/assistant 交替，最后一条必须 assistant；\n"
        "3) 每个 message 必须且只能有 role/content 键；\n"
        "4) content 要自然、具体、非模板化；\n"
        "5) 每条 content 长度 2~2000 字；\n"
        "6) assistant 的语气要有角色辨识度，但不做作；\n"
        "7) 至少一轮 assistant 体现“先轻吐槽再给可执行建议”的节奏；\n"
        "8) 在不影响任务完成的前提下，可有 1 处自然的幻想乡生活回忆或朋友互动提及。"
    )


def validate_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    messages = record.get("messages")

    if not isinstance(messages, list) or not messages:
        return False, ["messages必须是非空列表"]

    total_chars = 0
    system_count = 0

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            issues.append(f"第{i}条不是对象")
            continue

        if set(msg.keys()) != {"role", "content"}:
            issues.append(f"第{i}条键非法")
            continue

        role = msg.get("role")
        content = msg.get("content")

        if role not in {"system", "user", "assistant"}:
            issues.append(f"第{i}条role非法:{role}")
        if role == "system":
            system_count += 1

        if not isinstance(content, str) or not content.strip():
            issues.append(f"第{i}条content为空")
            continue

        clen = len(content)
        total_chars += clen
        if clen < 2 or clen > 2000:
            issues.append(f"第{i}条长度越界:{clen}")

    if system_count > 1:
        issues.append("system条数超过1")
    if system_count == 0:
        issues.append("system条数必须为1")
    if system_count == 1 and messages[0].get("role") != "system":
        issues.append("system必须在第一条")

    start = 1 if messages[0].get("role") == "system" else 0
    if len(messages) - start < 2:
        issues.append("有效对话条数不足")
    else:
        expected = "user"
        for i in range(start, len(messages)):
            role = messages[i].get("role")
            if role != expected:
                issues.append(f"第{i}条应为{expected}实际{role}")
            expected = "assistant" if expected == "user" else "user"

        if messages[-1].get("role") != "assistant":
            issues.append("最后一条必须是assistant")

    if total_chars > 12000:
        issues.append(f"总字符超限:{total_chars}")

    return len(issues) == 0, issues


def score_record(client: OpenAI, cfg: Config, record: dict[str, Any]) -> tuple[int, list[str]]:
    prompt = (
        "你是角色扮演SFT质检员。只输出JSON："
        '{"score":0-100,"issues":["..."]}。\n'
        "评分维度：真实性、连贯性、人设一致性（幻想乡冰之妖精感）、安全拒绝正确性、排版可读性。\n"
        "若出现以下问题应显著扣分：通用客服腔、心理咨询模板腔、机械三段式口号化、术语堆叠难懂。\n"
        "当score<80时，issues必须给可修复问题。\n\n"
        f"记录：{json.dumps(record, ensure_ascii=False)}"
    )

    try:
        raw = call_llm(
            client=client,
            model=cfg.critic_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            retries=cfg.llm_retries,
            backoff_base=cfg.llm_backoff_base,
        )
    except Exception:
        return 0, ["critic调用失败"]
    obj = extract_json(raw)
    if not isinstance(obj, dict):
        return 0, ["critic输出非JSON"]

    score = obj.get("score", 0)
    issues = obj.get("issues", [])
    if not isinstance(score, (int, float)):
        score = 0
    if not isinstance(issues, list):
        issues = ["critic issues字段非法"]

    return max(0, min(100, int(score))), [str(x) for x in issues][:8]


def rewrite_record(client: OpenAI, cfg: Config, record: dict[str, Any], issue_list: list[str]) -> dict[str, Any]:
    prompt = (
        "根据问题修订这条角色对话样本并只输出JSON对象（仅messages字段）。\n"
        f"问题：{issue_list}\n"
        "修订要求：保持主题，提升自然度与人设一致性，保留安全边界。"
        "重点修复‘像通用大模型’的语气，增强冰之妖精式轻吐槽+行动建议节奏。"
        "遇到专业内容要先口语解释，再给简短可执行步骤。"
        "必须严格遵守琪露诺的System Prompt设定。\n"
        f"原样本：{json.dumps(record, ensure_ascii=False)}"
    )

    try:
        raw = call_llm(
            client=client,
            model=cfg.model,
            messages=[
                {"role": "system", "content": "你是SFT样本修订器，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            retries=cfg.llm_retries,
            backoff_base=cfg.llm_backoff_base,
        )
    except Exception:
        return {}

    obj = extract_json(raw)
    return obj if isinstance(obj, dict) else {}


def dedup_hash(messages: list[dict[str, str]]) -> str:
    normalized = []
    for m in messages:
        role = m["role"].strip().lower()
        content = " ".join(m["content"].strip().lower().split())
        normalized.append(f"{role}:{content}")
    return hashlib.sha256("|".join(normalized).encode("utf-8")).hexdigest()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def resplit_train_val(
    accepted_path: Path, 
    train_path: Path, 
    val_path: Path, 
    train_ratio: float, 
    seed: int
) -> tuple[int, int]:
    """
    Post-processing: Re-split all accepted samples into train/val using a fixed seed.
    This ensures stable splitting regardless of when samples were generated.
    
    Args:
        accepted_path: Path to accepted_raw.jsonl
        train_path: Path to train_messages.jsonl
        val_path: Path to val_messages.jsonl
        train_ratio: Ratio for training set
        seed: Seed for splitting RNG (should be cfg.seed + 10007 for consistency)
    
    Returns:
        (train_count, val_count)
    """
    split_rng = random.Random(seed)
    train_count = 0
    val_count = 0
    
    # Clear train/val files before rebuilding
    train_path.write_text("", encoding="utf-8")
    val_path.write_text("", encoding="utf-8")
    
    if not accepted_path.exists():
        return 0, 0
    
    with accepted_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            if isinstance(obj, dict) and "messages" in obj:
                messages = obj.get("messages")
                if isinstance(messages, list) and messages:
                    split_row = {"messages": messages}
                    if split_rng.random() < train_ratio:
                        append_jsonl(train_path, split_row)
                        train_count += 1
                    else:
                        append_jsonl(val_path, split_row)
                        val_count += 1
    
    return train_count, val_count


def load_existing_hashes(path: Path) -> tuple[set[str], int]:
    hashes: set[str] = set()
    count = 0
    if not path.exists():
        return hashes, count

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                h = obj.get("hash")
                if isinstance(h, str) and h:
                    hashes.add(h)
                count += 1

    return hashes, count


def render_progress(current: int, total: int, requests: int, width: int = 30) -> None:
    total_safe = max(1, total)
    ratio = max(0.0, min(1.0, current / total_safe))
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    percent = ratio * 100
    print(
        f"\rProgress [{bar}] {current}/{total_safe} ({percent:5.1f}%) | requests: {requests}",
        end="",
        flush=True,
    )


def generate_batch(
    client: OpenAI,
    cfg: Config,
    topic: str,
    pair_count: int,
    refusal_mode: bool,
) -> list[dict[str, Any]]:
    try:
        raw = call_llm(
            client=client,
            model=cfg.model,
            messages=[
                {"role": "system", "content": "你是高质量SFT数据生成器，只输出JSON数组。"},
                {
                    "role": "user",
                    "content": build_generation_prompt(
                        topic=topic,
                        pair_count=pair_count,
                        refusal_mode=refusal_mode,
                        n=cfg.samples_per_request,
                    ),
                },
            ],
            temperature=0.75,
            retries=cfg.llm_retries,
            backoff_base=cfg.llm_backoff_base,
        )
    except Exception:
        return []

    obj = extract_json(raw)
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def main() -> None:
    cfg = parse_args()
    client = build_client(cfg)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    accepted_path = cfg.output_dir / "accepted_raw.jsonl"
    train_path = cfg.output_dir / "train_messages.jsonl"
    val_path = cfg.output_dir / "val_messages.jsonl"
    rejected_path = cfg.output_dir / "rejected_raw.jsonl"

    rng = random.Random(cfg.seed)
    seen_hashes: set[str] = set()

    if cfg.resume:
        seen_hashes, resumed = load_existing_hashes(accepted_path)
        # Ensure output files exist when resuming partial runs.
        for p in [accepted_path, train_path, val_path]:
            if not p.exists():
                p.write_text("", encoding="utf-8")
        if cfg.save_rejected and not rejected_path.exists():
            rejected_path.write_text("", encoding="utf-8")
    else:
        resumed = 0
        # Truncate outputs at run start; then append one-by-one for crash safety.
        for p in [accepted_path, train_path, val_path]:
            p.write_text("", encoding="utf-8")
        if cfg.save_rejected:
            rejected_path.write_text("", encoding="utf-8")

    stats = {
        "generation_requests": 0,
        "records_seen": 0,
        "schema_failed": 0,
        "critic_failed": 0,
        "rewrite_used": 0,
        "dedup_dropped": 0,
        "accepted": 0,
        "rejected": 0,
        "resumed_accepted": resumed,
    }
    stats["accepted"] = resumed

    # Keep refusal data as a minority to avoid over-refusal behavior after SFT.
    refusal_ratio = cfg.refusal_ratio

    # Upper bound prevents infinite loops when quality gate is too strict.
    max_generation_requests = cfg.count * (cfg.max_retries + 3)

    render_progress(stats["accepted"], cfg.count, stats["generation_requests"])

    while stats["accepted"] < cfg.count and stats["generation_requests"] < max_generation_requests:
        stats["generation_requests"] += 1
        render_progress(stats["accepted"], cfg.count, stats["generation_requests"])

        refusal_mode = rng.random() < refusal_ratio
        topic = rng.choice(TOPICS_REFUSAL if refusal_mode else TOPICS_NORMAL)
        turns = rng.randint(cfg.min_turns, cfg.max_turns)

        candidates = generate_batch(client, cfg, topic, turns, refusal_mode)
        if not candidates:
            continue

        for candidate in candidates:
            if stats["accepted"] >= cfg.count:
                break

            stats["records_seen"] += 1
            valid, schema_issues = validate_record(candidate)
            retries = 0

            best_record = candidate
            best_score = -1
            best_issues: list[str] = schema_issues[:]

            while True:
                do_critic = (not cfg.skip_critic) and (rng.random() < cfg.critic_sample_rate)
                if valid and do_critic:
                    score, critic_issues = score_record(client, cfg, candidate)
                elif valid:
                    # In lite mode, schema-pass samples can skip expensive critic requests.
                    score, critic_issues = 75, []
                else:
                    score, critic_issues = 0, schema_issues[:]
                    stats["schema_failed"] += 1

                if score > best_score:
                    best_score = score
                    best_record = candidate
                    best_issues = critic_issues[:]

                if valid and score >= cfg.min_score:
                    break

                if retries >= cfg.max_retries:
                    stats["critic_failed"] += 1
                    break

                retries += 1
                stats["rewrite_used"] += 1
                candidate = rewrite_record(client, cfg, candidate, critic_issues)
                valid, schema_issues = validate_record(candidate)

            final_messages = best_record.get("messages", []) if isinstance(best_record, dict) else []
            if not isinstance(final_messages, list) or not final_messages:
                stats["rejected"] += 1
                if cfg.save_rejected:
                    append_jsonl(
                        rejected_path,
                        {
                            "id": uuid.uuid4().hex,
                            "topic": topic,
                            "score": max(0, best_score),
                            "issues": best_issues,
                            "retries": retries,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                continue

            h = dedup_hash(final_messages)
            if h in seen_hashes:
                stats["dedup_dropped"] += 1
                continue
            seen_hashes.add(h)

            if best_score < cfg.min_score:
                stats["rejected"] += 1
                if cfg.save_rejected:
                    append_jsonl(
                        rejected_path,
                        {
                            "id": uuid.uuid4().hex,
                            "topic": topic,
                            "score": max(0, best_score),
                            "issues": best_issues,
                            "retries": retries,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                continue

            accepted_row = {
                "id": uuid.uuid4().hex,
                "topic": topic,
                "score": best_score,
                "issues": best_issues,
                "retries": retries,
                "hash": h,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "messages": final_messages,
            }
            append_jsonl(accepted_path, accepted_row)

            stats["accepted"] += 1
            render_progress(stats["accepted"], cfg.count, stats["generation_requests"])

    print()

    # Post-processing: Re-split all accepted samples with stable seed
    # This fixes the issue where resume would cause train/val split drift
    print("Performing post-processing: Re-splitting train/val with stable seed...")
    train_count, val_count = resplit_train_val(
        accepted_path, 
        train_path, 
        val_path, 
        cfg.train_ratio, 
        cfg.seed + 10007
    )
    
    print(f"Train/Val split completed: {train_count} train, {val_count} val")
    if train_count + val_count > 0:
        actual_ratio = train_count / (train_count + val_count)
        print(f"Actual train ratio: {actual_ratio:.4f} (expected: {cfg.train_ratio:.4f})")

    print()
    print("=== SFT Generation Summary ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"accepted_raw: {accepted_path}")
    print(f"train: {train_path}")
    print(f"val: {val_path}")
    if cfg.save_rejected:
        print(f"rejected_raw: {rejected_path}")


if __name__ == "__main__":
    main()