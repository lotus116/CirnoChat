# SFT 生成与训练说明

这份文档描述当前项目里推荐的角色扮演 SFT 流程，重点是低成本、小规模、高质量，适合“琪露诺聊天应用”这种轻量场景。

## 目标

- 生成一批风格稳定、不过火的琪露诺对话数据
- 让 Qwen2.5-3B 学出“鲜活但不油腻”的角色感
- 保持技术问答、建议类回答和拒答边界的基本可用性

## 应用侧当前设计

近期已经做了几项关键修复：

- `facts` 记忆改成按 `session_id` 隔离，不再跨会话串线
- 摘要和事实不再直接拼进 `system`，而是作为低优先级参考上下文注入
- 对话采样默认关闭，需要显式设置 `ENABLE_DATASET_LOGGING=true`
- 流式回复失败时会回滚本轮用户消息，减少半回合脏历史

这意味着现在的线上聊天链路比之前更适合继续积累干净数据，但 `data/chat_samples.jsonl` 仍然不建议直接无清洗地拿去 SFT。

## 推荐脚本

推荐使用：`sft/scripts/generate_sft_data_light.py`

原因：

- 比旧版脚本更轻
- 更适合角色扮演聊天项目
- 支持并发
- 有失败熔断
- 带轻量本地质检
- 输出格式直接兼容当前 LLaMA-Factory 配置

## 输出文件

默认输出到 `sft/data`：

- `accepted_raw.jsonl`
- `rejected_raw.jsonl`（仅 `--save-rejected` 时）
- `train_messages.jsonl`
- `val_messages.jsonl`

训练与验证格式为：

```json
{"conversations":[{"from":"system","value":"..."},{"from":"human","value":"..."},{"from":"gpt","value":"..."}]}
```

## 轻量脚本常用参数

- `--count`：目标通过样本数
- `--model`：生成模型，默认 `deepseek-chat`
- `--critic-model`：审查模型，默认与生成模型相同
- `--output-dir`：输出目录，默认 `sft/data`
- `--train-ratio`：训练集比例，默认 `0.9`
- `--seed`：随机种子，默认 `42`
- `--samples-per-request`：每次请求返回多少候选，默认 `2`
- `--min-score`：最低通过分，默认 `78`
- `--min-turns`：最少回合数，默认 `2`
- `--max-turns`：最多回合数，默认 `4`
- `--refusal-ratio`：拒答场景比例，默认 `0.12`
- `--identity-ratio`：身份稳定场景比例，默认 `0.18`
- `--skip-critic`：跳过 LLM 审查，只用本地规则
- `--max-retries`：低分样本重写次数，默认 `1`
- `--llm-timeout`：单次 LLM 调用超时，默认 `90`
- `--llm-retries`：调用重试次数，默认 `2`
- `--llm-backoff-base`：重试退避基数，默认 `0.8`
- `--workers`：并发 worker 数，默认 `4`
- `--max-batches`：最大批次数，不填时自动按 `max(count * 6, workers * 4)` 推导
- `--max-consecutive-failures`：连续失败熔断阈值，默认 `12`
- `--resume`：断点续跑
- `--save-rejected`：保存未通过样本

说明：

- 不加 `--skip-critic` 时，critic 默认全量开启
- 轻量脚本不再区分 `lite / balanced / strict`，改成直接通过参数控制门槛

## 推荐用法

### 1. 快速试风格

```bash
python sft/scripts/generate_sft_data_light.py --count 300 --workers 6 --samples-per-request 3 --skip-critic --min-score 76
```

适合：

- 先看琪露诺味对不对
- 先看风格有没有太淡或太油
- 不想一开始就先付 critic 成本

### 2. 正式生成

```bash
python sft/scripts/generate_sft_data_light.py --count 800 --workers 4 --samples-per-request 3 --min-score 80 --max-retries 1 --save-rejected
```

适合：

- 做正式训练集
- 回头抽查 rejected
- 优先保证质量而不是速度

### 3. 使用 DeepSeek

`.env` 示例：

```text
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

命令示例：

```bash
python sft/scripts/generate_sft_data_light.py --model deepseek-chat --critic-model deepseek-chat --count 500 --workers 4 --samples-per-request 3 --min-score 80
```

## 并发建议

- 生成和审查都用同一个模型时：`workers=3` 或 `4`
- 只试风格、跳过 critic 时：`workers=4` 到 `6`
- `samples-per-request` 先用 `2` 或 `3`

不建议一开始就拉到 `8+`，否则更容易遇到限流、超时和输出格式波动。

## 质量控制重点

当前轻量脚本主要做这些检查：

- `messages` 结构是否合法
- 是否只有一条 `system`
- 是否严格 `user/assistant` 交替
- 是否泄露 prompt、memory、summary、session 等元信息
- 是否角色口头禅过密
- 是否颜文字、感叹号或设定名词堆叠过头
- 是否在技术回答里乱用角色标记
- 最后一轮助手是否真的回应了用户任务
- 低分样本是否能通过 rewrite 修回

## 数据集建议

对于 3B 角色模型，更建议先追求“小而干净”，不要一开始就堆很大规模。

建议节奏：

1. 先做 `300` 到 `500` 条快速试风格
2. 人工抽查至少 `50` 到 `100` 条
3. 风格方向确认后，再做 `800` 到 `1500` 条正式集
4. 用固定题目对比 `base / 旧 SFT / 新 SFT`

抽查重点：

- 会不会每句都在演
- 会不会固定口头禅刷屏
- 技术问题是否明显变差
- 拒答是否自然
- 多轮里身份是否稳定

## LLaMA-Factory 训练

当前项目已接好：

- 数据映射：`sft/llamafactory/dataset_info.json`
- 训练配置：`sft/llamafactory/qwen2_5_3b_lora_sft.yaml`
- 训练数据：`sft/data/train_messages.jsonl`
- 验证数据：`sft/data/val_messages.jsonl`

训练命令：

```bash
llamafactory-cli train sft/llamafactory/qwen2_5_3b_lora_sft.yaml
```

聊天测试：

```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora --template qwen --infer_dtype bfloat16 --default_system "你是琪露诺，东方Project中的冰之妖精。你会带一点天真可爱和小傲娇，但要先把问题答清楚，再带一点角色味。"
```

如果要测试训练过程中的单个 checkpoint，优先用验证集表现最好的那个，而不是默认最后一个。

## 导出与部署

导出：

```bash
llamafactory-cli export sft/llamafactory/qwen2_5_3b_merge.yaml
llamafactory-cli export sft/llamafactory/qwen2_5_3b_int4.yaml
```

Ollama：

```bash
cd sft/checkpoints/lf_qwen2_5_3b_merged
ollama create cirno -f Modelfile
ollama run cirno
```

如果 Ollama 还没启动：

```bash
ollama serve
```

`.env` 示例：

```text
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=cirno
```

## 当前建议

如果你现在的目标是尽快做出一个“比较鲜活的琪露诺”，推荐顺序：

1. 用轻量脚本先生成 300 到 500 条快速数据
2. 抽查并微调风格
3. 再生成 800 到 1500 条正式数据
4. 用 LLaMA-Factory 跑 LoRA
5. 先聊天验收，再决定是否导出和量化
