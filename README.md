# Cirno Chat (CLI)

来和琪露诺聊天吧（CLI 版本）。
支持长期本地记忆（SQLite）、会话恢复、记忆治理和 SFT 数据采样。

## 功能

- 琪露诺角色聊天（带轻量风格控制）
- 本地长期记忆（事实、摘要、最近对话）
- 记忆治理：版本化、过期降权、手动编辑、撤销
- 自动恢复最近会话
- 训练数据采样与反馈记录（JSONL）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

把 `.env.template` 的文件名改成 `.env`，然后根据你要用的服务填写 `OPENAI_BASE_URL`、`OPENAI_MODEL`，`OPENAI_API_KEY` 。
```md
**下面是常见的DEEPSEEK的环境变量配置**
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

如果你用 Ollama，推荐这样填：
```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=qwen2.5:3b-instruct
```


### 3. 启动

运行app.py：
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
│  ├─ memory.py
│  └─ dataset.py
├─ data/
├─ sft/
│  ├─ scripts/
│  │  └─ generate_sft_data.py
│  ├─ docs/
│  │  └─ SFT_TRAINING_PLAN.md
│  └─ data/
├─ .env.template
└─ requirements.txt
```

## 数据文件说明

程序运行后会在 `DATA_DIR`（默认 `data`）下生成：

- `memory.db`：SQLite 记忆库
- `chat_samples.jsonl`：对话样本
- `feedback_events.jsonl`：反馈样本

## 常见问题

- 启动报 API Key 错误：
  检查 `.env` 是否存在、`OPENAI_API_KEY` 是否填写。
- Ollama 连接失败：
  确认 Ollama 已启动，且 `OPENAI_BASE_URL=http://127.0.0.1:11434/v1`。

## SFT 数据生成

批量生成高质量训练数据（默认输出到 `sft/data`）：

```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2
```

进阶参数：

- `--samples-per-request`：单次生成请求返回的样本条数（默认2，建议2~4）
- `--mode`：`lite|balanced|strict`（默认 `lite`）
- `--critic-sample-rate`：质检抽样比例（默认0.35）
- `--refusal-ratio`：拒绝场景比例（默认0.15）
- `--llm-retries`：LLM调用失败重试次数（默认2）
- `--llm-backoff-base`：重试退避基础秒数（默认0.8）
- `--resume`：断点续跑（保留已有输出并继续到目标count）
- `--save-rejected`：保存未通过样本到 `sft/data/rejected_raw.jsonl`

## SFT 训练与部署

当前推荐只走 LLaMA-Factory 的主流流程，不再依赖自定义训练脚本。

### 1. 训练

```bash
llamafactory-cli train sft/llamafactory/qwen2_5_3b_lora_sft.yaml
```

### 2. 直连测试

先用 LoRA adapter 直接测试，不要先急着合并：

```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora/checkpoint-350 --template qwen --infer_dtype bfloat16 --default_system "你是赛博琪露诺，东方Project中的冰之妖精琪露诺；你正在和眼前的人类聊天并提供帮助。你的核心目标：在安全前提下，给出准确、可执行、好懂的帮助。"
```

### 3. 合并与导出

先合并出一个完整模型，再单独导出 int4 版本：

```bash
llamafactory-cli export sft/llamafactory/qwen2_5_3b_merge.yaml
llamafactory-cli export sft/llamafactory/qwen2_5_3b_int4.yaml
```

### 4. Ollama 部署

如果你要用 Ollama，本地最稳的流程是先把合并后的模型导成 Ollama 模型，再让本项目通过 OpenAI 兼容地址调用。

```bash
cd sft/checkpoints/lf_qwen2_5_3b_merged
ollama create cirno -f Modelfile
ollama run cirno
```

然后把 `.env` 改成：

```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=cirno
```

如果你只想先验证本地 Ollama 是否可用，可以直接执行：

```bash
curl http://127.0.0.1:11434/v1/models
```

统一说明文档：`sft/docs/SFT_TRAINING_PLAN.md`
