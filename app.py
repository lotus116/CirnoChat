from __future__ import annotations

import sys
from uuid import uuid4

from cirno_app.brain import OpenAICompatibleService
from cirno_app.config import AppSettings
from cirno_app.dataset import DatasetLogger
from cirno_app.memory import MemoryStore

COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_RESET = "\033[0m"


def _print_banner(user_name: str) -> None:
    print(f"{COLOR_CYAN}=============================================={COLOR_RESET}")
    print(f"{COLOR_CYAN}❄️ 琪露诺 CLI（长期记忆 + 数据采样）{COLOR_RESET}")
    print(f"{COLOR_CYAN}用户: {user_name} | 输入 /help 查看命令{COLOR_RESET}")
    print(f"{COLOR_CYAN}=============================================={COLOR_RESET}")


def _print_help() -> None:
    print("可用命令:")
    print("  /help                      显示帮助")
    print("  /exit                      退出")
    print("  /clear                     新建会话")
    print("  /session new               新建会话")
    print("  /session list              查看会话")
    print("  /session switch <id>       切换会话")
    print("  /memory                    查看摘要和活跃记忆")
    print("  /facts list [all]          查看事实（all包含非active）")
    print("  /facts add <k>=<v>         手动新增事实")
    print("  /facts edit <id> <v>       手动编辑事实值")
    print("  /facts supersede <id> <v>  以新值替换旧事实（保留版本）")
    print("  /facts expire <id>         标记事实过期")
    print("  /facts delete <id>         软删除事实")
    print("  /facts undo                回滚最近一次手动治理动作")
    print("  /fb up|down [修订文本]      反馈上一轮样本")


def _print_facts(memory: MemoryStore, session_id: str, include_inactive: bool = False) -> None:
    facts = memory.list_facts(session_id=session_id, limit=30, include_inactive=include_inactive)
    if not facts:
        print("(暂无事实记忆)")
        return
    for item in facts:
        print(
            f"[{item.id}] {item.key} = {item.value} "
            f"(conf={item.confidence:.2f}, decay={item.decay_score:.2f}, status={item.status})"
        )


def _handle_command(
    command: str,
    memory: MemoryStore,
    session_id: str,
    last_sample_id: str,
    dataset: DatasetLogger | None,
) -> tuple[str, str, bool]:
    # Centralized command router keeps the chat loop simple and easy to read.
    parts = command.split()
    if not parts:
        return session_id, last_sample_id, True

    if parts[0] == "/help":
        _print_help()
        return session_id, last_sample_id, True

    if parts[0] == "/exit":
        return session_id, last_sample_id, False

    if parts[0] == "/clear":
        session_id = uuid4().hex
        memory.create_session(session_id)
        print(f"{COLOR_GREEN}已创建新会话: {session_id}{COLOR_RESET}")
        return session_id, "", True

    if parts[0] == "/session" and len(parts) >= 2:
        if parts[1] == "new":
            session_id = uuid4().hex
            memory.create_session(session_id)
            print(f"{COLOR_GREEN}已创建新会话: {session_id}{COLOR_RESET}")
            return session_id, "", True
        if parts[1] == "list":
            for s in memory.list_sessions(limit=20):
                print(f"{s.session_id}  messages={s.message_count}  created={s.created_at}")
            return session_id, last_sample_id, True
        if parts[1] == "switch" and len(parts) == 3:
            session_id = parts[2].strip()
            memory.create_session(session_id)
            print(f"{COLOR_GREEN}已切换会话: {session_id}{COLOR_RESET}")
            return session_id, "", True

    if parts[0] == "/memory":
        print("--- summary ---")
        print(memory.get_latest_summary(session_id) or "(暂无摘要)")
        print("--- facts ---")
        _print_facts(memory, session_id=session_id, include_inactive=False)
        return session_id, last_sample_id, True

    if parts[0] == "/facts" and len(parts) >= 2:
        action = parts[1]
        if action == "list":
            _print_facts(
                memory,
                session_id=session_id,
                include_inactive=(len(parts) >= 3 and parts[2] == "all"),
            )
            return session_id, last_sample_id, True
        if action == "add" and "=" in command:
            payload = command.split("add", 1)[1].strip()
            key, value = payload.split("=", 1)
            ok = memory.add_fact_manual(
                session_id=session_id,
                key=key.strip(),
                value=value.strip(),
                confidence=0.9,
            )
            print(f"{COLOR_GREEN if ok else COLOR_RED}{'已写入事实' if ok else '写入失败'}{COLOR_RESET}")
            return session_id, last_sample_id, True
        if action == "edit" and len(parts) >= 4:
            try:
                fact_id = int(parts[2])
            except ValueError:
                print(f"{COLOR_YELLOW}事实ID必须是整数{COLOR_RESET}")
                return session_id, last_sample_id, True
            value = command.split(parts[2], 1)[1].strip()
            ok = memory.edit_fact(fact_id=fact_id, new_value=value)
            print(f"{COLOR_GREEN if ok else COLOR_RED}{'已编辑' if ok else '事实不存在'}{COLOR_RESET}")
            return session_id, last_sample_id, True
        if action == "supersede" and len(parts) >= 4:
            try:
                fact_id = int(parts[2])
            except ValueError:
                print(f"{COLOR_YELLOW}事实ID必须是整数{COLOR_RESET}")
                return session_id, last_sample_id, True
            value = command.split(parts[2], 1)[1].strip()
            ok = memory.supersede_fact(fact_id=fact_id, new_value=value)
            print(f"{COLOR_GREEN if ok else COLOR_RED}{'已版本替换' if ok else '事实不存在'}{COLOR_RESET}")
            return session_id, last_sample_id, True
        if action == "expire" and len(parts) == 3:
            try:
                fact_id = int(parts[2])
            except ValueError:
                print(f"{COLOR_YELLOW}事实ID必须是整数{COLOR_RESET}")
                return session_id, last_sample_id, True
            ok = memory.expire_fact(fact_id)
            print(f"{COLOR_GREEN if ok else COLOR_RED}{'已过期' if ok else '事实不存在'}{COLOR_RESET}")
            return session_id, last_sample_id, True
        if action == "delete" and len(parts) == 3:
            try:
                fact_id = int(parts[2])
            except ValueError:
                print(f"{COLOR_YELLOW}事实ID必须是整数{COLOR_RESET}")
                return session_id, last_sample_id, True
            ok = memory.delete_fact(fact_id)
            print(f"{COLOR_GREEN if ok else COLOR_RED}{'已删除' if ok else '事实不存在'}{COLOR_RESET}")
            return session_id, last_sample_id, True
        if action == "undo":
            ok = memory.undo_last_fact_action()
            print(f"{COLOR_GREEN if ok else COLOR_YELLOW}{'已回滚最近一次治理动作' if ok else '没有可回滚动作'}{COLOR_RESET}")
            return session_id, last_sample_id, True

    if parts[0] == "/fb" and len(parts) >= 2:
        if dataset is None:
            print(f"{COLOR_YELLOW}当前未启用数据采样，无法记录反馈{COLOR_RESET}")
            return session_id, last_sample_id, True
        if not last_sample_id:
            print(f"{COLOR_YELLOW}还没有可反馈的样本{COLOR_RESET}")
            return session_id, last_sample_id, True
        rating = parts[1].strip().lower()
        revised = ""
        if len(parts) > 2:
            revised = command.split(parts[1], 1)[1].strip()
        if rating not in {"up", "down"}:
            print("反馈只支持 up/down")
            return session_id, last_sample_id, True
        dataset.log_feedback(sample_id=last_sample_id, rating=rating, revised_answer=revised)
        print(f"{COLOR_GREEN}反馈已记录{COLOR_RESET}")
        return session_id, last_sample_id, True

    print(f"{COLOR_YELLOW}未知命令，输入 /help 查看可用命令{COLOR_RESET}")
    return session_id, last_sample_id, True


def main() -> None:
    try:
        settings = AppSettings.from_env()
    except ValueError as exc:
        print(f"{COLOR_RED}{exc}{COLOR_RESET}")
        sys.exit(1)

    try:
        memory = MemoryStore(settings.db_path)
    except Exception as exc:  # noqa: BLE001
        print(f"{COLOR_RED}初始化记忆库失败: {exc}{COLOR_RESET}")
        sys.exit(1)
    
    try:
        brain = OpenAICompatibleService(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model_name=settings.model_name,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{COLOR_RED}初始化LLM服务失败: {exc}{COLOR_RESET}")
        print(f"{COLOR_YELLOW}请检查 Ollama 是否运行、API 是否可访问{COLOR_RESET}")
        sys.exit(1)
    
    dataset = None
    if settings.enable_dataset_logging:
        dataset = DatasetLogger(
            dataset_path=settings.dataset_path,
            feedback_path=settings.feedback_path,
        )

    # 启动时创建一个默认会话，后续可通过 /session switch 切换。
    # Prefer restoring the most recently active session for continuity.
    latest_session_id = memory.get_latest_session_id()
    if latest_session_id:
        session_id = latest_session_id
        print(f"{COLOR_GREEN}已恢复最近会话: {session_id}{COLOR_RESET}")
    else:
        session_id = uuid4().hex
        memory.create_session(session_id)
        print(f"{COLOR_GREEN}已创建新会话: {session_id}{COLOR_RESET}")
    last_sample_id = ""
    _print_banner(settings.user_name)

    while True:
        try:
            user_input = input(f"{settings.user_name}> ").strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                session_id, last_sample_id, keep_running = _handle_command(
                    command=user_input,
                    memory=memory,
                    session_id=session_id,
                    last_sample_id=last_sample_id,
                    dataset=dataset,
                )
                if not keep_running:
                    print(f"{COLOR_CYAN}下次再来找本天才。{COLOR_RESET}")
                    break
                continue

            user_msg_id = memory.save_message(session_id, "user", user_input)
            memory.apply_decay(
                half_life_days=settings.half_life_days,
                expire_threshold=settings.expire_threshold,
            )

            facts = memory.list_facts(session_id=session_id, limit=settings.max_facts, include_inactive=False)
            summary = memory.get_latest_summary(session_id)
            recent_messages = memory.get_recent_messages(session_id, settings.max_recent_turns)
            if recent_messages and recent_messages[-1]["role"] == "user":
                recent_messages = recent_messages[:-1]
            llm_messages = brain.build_chat_messages(
                user_input=user_input,
                recent_messages=recent_messages,
                facts=facts,
                summary=summary,
            )

            try:
                print(f"{COLOR_CYAN}琪露诺> {COLOR_RESET}", end="", flush=True)
                full_reply = ""
                for token in brain.stream_reply(llm_messages, settings.temperature):
                    print(f"{COLOR_CYAN}{token}{COLOR_RESET}", end="", flush=True)
                    full_reply += token
                print()
            except Exception as exc:  # noqa: BLE001
                print(f"\n{COLOR_RED}LLM 调用失败: {exc}{COLOR_RESET}")
                print(f"{COLOR_YELLOW}跳过本轮对话{COLOR_RESET}")
                memory.delete_message(user_msg_id)
                continue

            memory.save_message(session_id, "assistant", full_reply)

            # 事实提炼是LLM辅助步骤，治理规则在MemoryStore内执行。
            try:
                extracted_facts = brain.extract_facts(user_input, full_reply)
                if extracted_facts:
                    memory.upsert_facts(
                        session_id=session_id,
                        facts=extracted_facts,
                        source_message_id=user_msg_id,
                    )
            except Exception as exc:  # noqa: BLE001
                # 事实提炼失败不应中断对话
                print(f"{COLOR_YELLOW}事实提炼失败（非致命）: {exc}{COLOR_RESET}")

            recent_for_summary = memory.get_recent_messages(session_id, settings.max_recent_turns)
            if len(recent_for_summary) >= settings.summary_every_messages:
                try:
                    summary_text = brain.summarize_messages(
                        recent_for_summary[-settings.summary_every_messages :]
                    )
                    if summary_text:
                        memory.save_summary(session_id, summary_text)
                except Exception as exc:  # noqa: BLE001
                    # 摘要生成失败不应中断对话
                    print(f"{COLOR_YELLOW}摘要生成失败（非致命）: {exc}{COLOR_RESET}")

            last_sample_id = ""
            if dataset is not None:
                last_sample_id = dataset.log_sample(
                    session_id=session_id,
                    messages=recent_for_summary,
                    metadata={
                        "model": settings.model_name,
                        "temperature": settings.temperature,
                        "memory_fact_count": len(facts),
                        "summary": summary,
                        "facts": [{"key": item.key, "value": item.value} for item in facts],
                    },
                )
            # sample_id display is optional; feedback command works either way.
            if settings.show_sample_id and last_sample_id:
                print(f"{COLOR_YELLOW}sample_id={last_sample_id}（可用 /fb up|down 反馈）{COLOR_RESET}")
            else:
                # print(f"{COLOR_YELLOW}可用 /fb up|down 反馈上一轮回答{COLOR_RESET}")
                continue

        except KeyboardInterrupt:
            print(f"\n{COLOR_CYAN}会话已中断，下次再聊。{COLOR_RESET}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"{COLOR_RED}发生异常: {exc}{COLOR_RESET}")
            print(f"{COLOR_YELLOW}会话仍然活跃，请重新输入{COLOR_RESET}")
            continue


if __name__ == "__main__":
    main()
