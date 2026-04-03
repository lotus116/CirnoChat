# Cirno Chat (CLI)

一个以琪露诺为角色核心的命令行聊天小项目，支持本地长期记忆、会话恢复、反馈采样，以及为 Qwen2.5-3B 生成 SFT 数据。

## 功能

- 琪露诺角色聊天
- 本地长期记忆（SQLite）
- 会话恢复与多会话切换
- 事实记忆治理
- 训练数据采样与反馈记录
- 轻量 SFT 数据生成脚本

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

把 `.env.template` 重命名为 `.env`，然后填写你要用的 OpenAI 兼容接口。

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
- `/memory` 查看摘要和活跃记忆
- `/facts list [all]` 查看事实
- `/facts add <k>=<v>` 添加事实
- `/facts edit <id> <v>` 编辑事实
- `/facts supersede <id> <v>` 版本替换
- `/facts expire <id>` 标记过期
- `/facts delete <id>` 软删除
- `/facts undo` 回滚最近一次手动治理
- `/fb up|down [修订文本]` 记录反馈

## 目录结构

```text
.
├─ app.py
├─ cirno_app/
│  ├─ brain.py
│  ├─ config.py
│  ├─ dataset.py
│  └─ memory.py
├─ data/
├─ sft/
│  ├─ data/
│  ├─ docs/
│  │  └─ SFT_TRAINING_PLAN.md
│  ├─ llamafactory/
│  └─ scripts/
│     ├─ generate_sft_data.py
│     └─ generate_sft_data_light.py
├─ .env.template
└─ requirements.txt
```

## 数据文件

程序运行后会在 `data/` 下生成：

- `memory.db`：SQLite 记忆库
- `chat_samples.jsonl`：对话采样
- `feedback_events.jsonl`：反馈记录

## SFT 数据生成

当前更推荐使用轻量脚本 `sft/scripts/generate_sft_data_light.py`，它更适合角色扮演聊天项目，成本更低，也更容易控制风格。

基础用法：

```bash
python sft/scripts/generate_sft_data_light.py --count 500 --workers 4 --samples-per-request 3 --min-score 80 --max-retries 1
```

快速试风格：

```bash
python sft/scripts/generate_sft_data_light.py --count 500 --workers 6 --samples-per-request 3 --skip-critic --min-score 76
```

正式生成：

```bash
python sft/scripts/generate_sft_data_light.py --count 800 --workers 4 --samples-per-request 3 --min-score 80 --max-retries 1 --save-rejected
```

默认输出目录是 `sft/data`，会生成：

- `sft/data/accepted_raw.jsonl`
- `sft/data/rejected_raw.jsonl`（仅 `--save-rejected` 时）
- `sft/data/train_messages.jsonl`
- `sft/data/val_messages.jsonl`

### 推荐参数

- `--workers`：并发生成 worker 数，建议先从 `3` 或 `4` 开始
- `--samples-per-request`：每次请求返回几条候选，建议 `2` 到 `3`
- `--skip-critic`：跳过 LLM 审查，适合快速试风格
- `--max-batches`：总批次数上限，防止长时间空跑
- `--max-consecutive-failures`：连续失败熔断阈值
- `--resume`：断点续跑

## SFT 训练

训练入口：

```bash
llamafactory-cli train sft/llamafactory/qwen2_5_3b_lora_sft.yaml
```

对话测试：

```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora/checkpoint-350 --template qwen --infer_dtype bfloat16 --default_system "你是琪露诺，东方Project中的冰之妖精，现在正在和眼前的人类聊天并提供帮助。你的核心目标是在安全前提下给出准确、可执行、好懂的帮助。"
```

导出模型：

```bash
llamafactory-cli export sft/llamafactory/qwen2_5_3b_merge.yaml
llamafactory-cli export sft/llamafactory/qwen2_5_3b_int4.yaml
```

## Ollama 部署

```bash
cd sft/checkpoints/lf_qwen2_5_3b_merged
ollama create cirno -f Modelfile
ollama run cirno
```

`.env` 示例：

```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=cirno
```

## 文档

更详细的 SFT 生成和训练说明见 `sft/docs/SFT_TRAINING_PLAN.md`。
