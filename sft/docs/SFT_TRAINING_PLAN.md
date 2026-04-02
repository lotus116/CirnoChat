# SFT 生成与训练一体化说明（角色扮演项目）

本文档合并了原 `explain.md` 与 `SFT_TRAINING_PLAN.md`，作为当前唯一权威说明。

## 1. 目标与推荐方案

- 目标：低成本、快速迭代“琪露诺角色扮演”小模型。
- 基座模型：`Qwen2.5-3B-Instruct`
- 微调方法：`QLoRA (4bit)`
- 训练框架：`LLaMA-Factory`
- 推理接口：`OpenAI 兼容 API`（推荐 `Ollama` / 本地网关 / OpenAI）

这个组合在中文角色对话场景下兼顾质量、速度和显存成本。

## 2. 生成脚本入口

- 脚本：`sft/scripts/generate_sft_data.py`
- 默认输出目录：`sft/data`

基础命令（推荐从轻量模式开始）：

```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2
```

默认会优先读取 `OPENAI_*` 环境变量；如果你还在用旧变量，`DEEPSEEK_*` 也会继续兼容。若使用 Ollama，本地默认地址是 `http://127.0.0.1:11434/v1`。

## 3. 输出文件说明

运行后生成：

- `sft/data/accepted_raw.jsonl`
  - 通过样本，包含 `score/issues/retries/hash/topic/conversations` 等元信息
- `sft/data/train_messages.jsonl`
  - 训练集，严格格式：`{"conversations": [{"from": "human|gpt|system", "value": "..."}, ...]}`
- `sft/data/val_messages.jsonl`
  - 验证集，严格格式：`{"conversations": [{"from": "human|gpt|system", "value": "..."}, ...]}`
- `sft/data/rejected_raw.jsonl`
  - 仅在 `--save-rejected` 时生成

## 4. 当前脚本完整参数

`generate_sft_data.py` 支持参数如下：

- `--count`：目标通过样本数，默认 `200`
- `--model`：生成模型，默认 `deepseek-chat`
- `--critic-model`：质检模型，默认 `deepseek-chat`
- `--min-score`：最小通过分，默认 `70`
- `--max-retries`：重写最大次数，默认 `1`
- `--min-turns`：最少 user/assistant 成对轮数，默认 `3`
- `--max-turns`：最多 user/assistant 成对轮数，默认 `6`
- `--train-ratio`：训练集比例，默认 `0.90`
- `--seed`：随机种子，默认 `42`
- `--output-dir`：输出目录，默认 `sft/data`
- `--save-rejected`：保存拒绝样本（布尔开关）
- `--samples-per-request`：单次生成请求返回样本数，默认 `2`，上限 `8`
- `--mode`：`lite|balanced|strict`，默认 `lite`
- `--skip-critic`：跳过质检模型（仅做规则校验）
- `--critic-sample-rate`：抽样质检比例，默认 `0.35`
- `--refusal-ratio`：拒绝场景采样比例，默认 `0.10`
- `--llm-retries`：单次 LLM 请求失败后重试次数，默认 `2`
- `--llm-backoff-base`：重试退避基础秒数，默认 `0.8`
- `--llm-timeout`：单次 LLM 请求超时秒数，默认 `90`
- `--drift-topic-ratio`：在非拒绝样本中，漂移专项主题采样比例，默认 `0.20`
- `--topic-profile`：普通主题集合，`focused|full`，默认 `focused`
- `--resume`：断点续跑，不清空已有输出文件并从已有 accepted 进度继续

## 5. 三种模式差异

- `lite`（默认）：
  - 低成本优先
  - 默认阈值较宽，质检抽样执行
  - 适合快速积累角色语料
- `balanced`：
  - 质量与成本平衡
  - 最低分提高到至少 `75`
  - 质检抽样比例提高到至少 `0.6`
- `strict`：
  - 质量优先
  - 最低分提高到至少 `80`
  - 重写次数至少 `2`，质检抽样比例 `1.0`

`--train-ratio` 实践建议（按数据规模）：

- 样本量 `<= 300`：建议 `0.85 ~ 0.90`（保证验证集有足够样本）
- 样本量 `300 ~ 2000`：建议 `0.90 ~ 0.95`
- 样本量 `>= 2000`：`0.95` 通常合理


## 6. 脚本设计流程（逐步）

每批样本按以下流程处理：

1. 主题采样
- 普通生活场景为主，拒绝场景为辅（由 `--refusal-ratio` 控制，默认 `0.15`）
- 非拒绝样本在“普通主题/漂移专项主题”之间混采（由 `--drift-topic-ratio` 控制）
- 普通主题可选 `focused`（默认，聚焦高价值场景）或 `full`（全量覆盖）

2. 批量生成
- 一次请求可生成 `N` 条，`N = --samples-per-request`
- 即：单次API生成调用理论上返回 `N` 条候选样本

3. 结构校验（deterministic）
- `messages` 必须为非空列表
- `role/content` 键严格
- `system` 位置与轮次交替规则
- 长度边界检查

4. 质检评分（可抽样）
- 根据 `--skip-critic` 和 `--critic-sample-rate` 决定是否调用 critic
- 若跳过且规则通过，会赋予默认通过分（脚本中为 75）

4.1 LLM调用稳定性
- 生成/重写/质检请求都使用统一重试与指数退避
- 重试次数由 `--llm-retries` 控制，退避基数由 `--llm-backoff-base` 控制
- 单次调用超时由 `--llm-timeout` 控制（默认 `90s`）

5. 重写修复
- 不达标样本最多重写 `--max-retries` 次

6. 去重
- 基于归一化后的 `sha256` 内容哈希去重

7. 导出
- 保存原始通过样本
- 按 `train_ratio` 切分并导出训练/验证 JSONL
- 采用按条增量写入，运行中断时已生成样本会保留

## 7. 成本与吞吐建议

如果你要省钱提速：

- 优先使用：
  - `--mode lite`
  - `--samples-per-request 2~4`
  - `--critic-sample-rate 0.2~0.4`
- 极限省钱：
  - 加 `--skip-critic`
  - 但建议保留小比例带质检的数据批次做抽查

示例微调数据500条，质检抽样比例50%：
```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2 --critic-sample-rate 0.5 --topic-profile focused --drift-topic-ratio 0.20 --llm-timeout 90

```

示例（在已有 500 条基础上续跑到 1000 条，新增约 500 条）：
存在漂移情况，稍微提高一下比例。
```bash
python sft/scripts/generate_sft_data.py --mode balanced --count 1000 --resume --samples-per-request 2 --critic-sample-rate 0.5 --refusal-ratio 0.10 --drift-topic-ratio 0.35 --topic-profile focused --llm-timeout 90
```

## 8. LLaMA-Factory 使用方法（主流流程）

以下流程只使用 LLaMA-Factory，不依赖任何自定义训练脚本。

### 8.1 已有文件

- 数据映射：`sft/llamafactory/dataset_info.json`
- 训练配置：`sft/llamafactory/qwen2_5_3b_lora_sft.yaml`
- 训练数据：`sft/data/train_messages.jsonl`
- 验证数据：`sft/data/val_messages.jsonl`

这套流程本身只负责训练与导出，不强依赖 DeepSeek；只要你的推理/采样接口是 OpenAI 兼容的就能用。

### 8.2 安装依赖

```bash
pip install -r requirements.txt
```

检查安装：

```bash
llamafactory-cli version
```

### 8.3 启动训练

在项目根目录执行：

```bash
llamafactory-cli train sft/llamafactory/qwen2_5_3b_lora_sft.yaml
```

首次运行会自动下载基础模型 `Qwen/Qwen2.5-3B-Instruct`，请确保网络和磁盘空间充足。

### 8.4 关键参数（当前配置）

- `finetuning_type`: `lora`
- `lora_rank`: `8`
- `lora_alpha`: `16`
- `lora_dropout`: `0.05`
- `cutoff_len`: `1024`
- `per_device_train_batch_size`: `1`
- `gradient_accumulation_steps`: `8`
- `learning_rate`: `1e-4`
- `num_train_epochs`: `3`
- `bf16`: `true`

这些参数针对 16GB 显存优先保证可跑通；若显存不足，可先降低 `cutoff_len` 或减少批大小。

### 8.5 输出目录

- 默认输出：`sft/checkpoints/lf_qwen2_5_3b_lora`

训练日志与 checkpoint 会写入该目录。

### 8.6 常见问题

1. 命令能跑但包找不到：确认当前终端激活的是同一个 conda 环境。
2. 首次下载很慢：属于模型权重下载阶段，可重试命令继续。
3. Windows symlink 警告：不影响训练，仅可能增加缓存占用。

### 8.7 先做直连对话测试

训练完成后，建议先不要急着合并模型，而是先用 LoRA adapter 直接做对话测试。
```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora/checkpoint-350 --template qwen --infer_dtype bfloat16 --default_system "你是赛博琪露诺，东方Project中的冰之妖精琪露诺；你正在和眼前的人类聊天并提供帮助。你的核心目标：在安全前提下，给出准确、可执行、好懂的帮助。"
```

如果你要用 Ollama 的 OpenAI 兼容 URL 直连验证，也可以直接指定 `--model_name_or_path` 为本地已导出的合并模型，或者在 `app.py` 里把 `OPENAI_BASE_URL` 设置成 `http://127.0.0.1:11434/v1`。
推荐流程：

1. 保留基座模型 `Qwen/Qwen2.5-3B-Instruct` 不动。
2. 加载最佳 checkpoint `sft/checkpoints/lf_qwen2_5_3b_lora/checkpoint-350`。
3. 先做 20~50 轮人工测试，重点看：
  - 人设稳定性
  - 拒绝边界是否自然
  - 角色口吻是否过度模板化
  - 长对话是否开始跑偏

如果结果可接受，再进入合并与量化步骤。

### 8.8 合并 LoRA 与导出 int4

如果你决定部署，建议按这个顺序处理：

1. 先把 LoRA 合并进基座模型，得到一个完整模型。
2. 再把完整模型导出成 int4 推理版本。
3. 保留一份未量化的合并版，作为后续回滚和再训练基线。

关于 int4 的建议：

- 适合：本地推理、显存有限、想降低部署成本。
- 不适合：后续还要频繁继续训练或做大量实验。
- 实践上更稳的做法是：先保留 bf16 / 合并版，再额外做一个 int4 部署版。

如果你后面要继续训练，尽量不要只留 int4，最好同时保留：

- 基座模型缓存
- LoRA adapter
- 合并后的完整模型
- int4 部署副本

推荐直接使用这两个导出配置：

```bash
llamafactory-cli export sft/llamafactory/qwen2_5_3b_merge.yaml
llamafactory-cli export sft/llamafactory/qwen2_5_3b_int4.yaml
```

### 8.9 Ollama 部署

如果你选择 Ollama，推荐顺序是：先确认合并版能正常对话，再把合并目录导入 Ollama，最后让项目通过 OpenAI 兼容 URL 调用。

1. 确认合并目录存在：`sft/checkpoints/lf_qwen2_5_3b_merged`
2. 用 LLaMA-Factory 生成的 `Modelfile` 创建 Ollama 模型：

```bash
ollama create cirno -f sft/checkpoints/lf_qwen2_5_3b_merged/Modelfile
```

3. 启动或确认 Ollama 服务可用：

```bash
ollama serve
```

4. 验证模型可运行：

```bash
ollama run cirno
```

5. 项目 `.env` 使用这组值：

```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=cirno
```

6. 如果你只是想先确认服务接口是否正常：

```bash
curl http://127.0.0.1:11434/v1/models
```



