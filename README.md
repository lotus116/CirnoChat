# Cirno Chat (CLI)

一个以琪露诺为核心角色的命令行聊天小项目，支持本地会话记忆、摘要、事实治理，以及为 Qwen2.5-3B 准备 SFT 数据。

## 功能

- 琪露诺角色对话
- SQLite 本地记忆
- 多会话切换与恢复
- 手动事实治理
- 可选的聊天采样与反馈记录
- 轻量 SFT 数据生成脚本

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 `.env`

把 `.env.template` 复制为 `.env`，然后填写 OpenAI 兼容接口。

DeepSeek 示例：

```text
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

Ollama 示例：

```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=qwen2.5:3b-instruct
```

### 3. 启动应用

```bash
python app.py
```

## 常用命令

- `/help` 查看帮助
- `/exit` 退出
- `/session new` 新建会话
- `/session list` 列出会话
- `/session switch <id>` 切换会话
- `/memory` 查看当前会话摘要和事实
- `/facts list [all]` 查看当前会话事实
- `/facts add <k>=<v>` 手动新增事实
- `/facts edit <id> <v>` 编辑事实
- `/facts supersede <id> <v>` 用新值替换旧事实
- `/facts expire <id>` 标记事实过期
- `/facts delete <id>` 软删除事实
- `/facts undo` 回滚最近一次手动治理动作
- `/fb up|down [修订文本]` 记录对最近采样样本的反馈

## 当前实现说明

- `facts` 现在按 `session_id` 隔离，不再跨会话共享。
- 摘要和事实不再直接拼进 `system`，而是作为低优先级参考上下文注入。
- 对话采样默认关闭，只有 `ENABLE_DATASET_LOGGING=true` 时才会落盘。
- 如果流式回复失败，本轮刚写入的用户消息会回滚，避免留下半回合脏历史。

## 数据文件

运行后默认会在 `data/` 下使用：

- `memory.db`
- `chat_samples.jsonl`
- `feedback_events.jsonl`

其中 `chat_samples.jsonl` 和 `feedback_events.jsonl` 只有在启用采样时才会写入。

## 推荐环境变量

- `MAX_RECENT_TURNS=8`
- `MAX_FACTS=8`
- `TEMPERATURE=0.7`
- `SUMMARY_EVERY_MESSAGES=6`
- `HALF_LIFE_DAYS=14`
- `EXPIRE_THRESHOLD=0.25`
- `SHOW_SAMPLE_ID=false`
- `ENABLE_DATASET_LOGGING=false`

## SFT 数据生成

当前推荐使用 `sft/scripts/generate_sft_data_light.py`。

快速试风格：

```bash
python sft/scripts/generate_sft_data_light.py --count 300 --workers 6 --samples-per-request 3 --skip-critic --min-score 76
```

正式生成：

```bash
python sft/scripts/generate_sft_data_light.py --count 800 --workers 4 --samples-per-request 3 --min-score 80 --max-retries 1 --save-rejected
```

输出目录默认是 `sft/data`，会生成：

- `accepted_raw.jsonl`
- `rejected_raw.jsonl`（仅 `--save-rejected` 时）
- `train_messages.jsonl`
- `val_messages.jsonl`

## SFT 训练

训练：

```bash
llamafactory-cli train sft/llamafactory/qwen2_5_3b_lora_sft.yaml
```

聊天测试：

```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora --template qwen --infer_dtype bfloat16 --default_system "你是琪露诺，东方Project中的冰之妖精。你会带一点天真可爱和小傲娇，但要先把问题答清楚，再带一点角色味。"
```

## Ollama 部署

```bash
cd sft/checkpoints/lf_qwen2_5_3b_merged
ollama create cirno -f Modelfile
ollama run cirno
```

## 文档

更详细的 SFT 流程与当前训练建议见 `sft/docs/SFT_TRAINING_PLAN.md`。
