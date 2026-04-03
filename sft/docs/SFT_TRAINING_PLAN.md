# SFT 生成与训练说明

这份文档描述当前项目里推荐的角色扮演 SFT 流程，重点是低成本、小规模、高质量，适合“琪露诺聊天应用”这种轻量场景。

## 目标

- 用较低成本生成一批质量稳定的角色扮演数据
- 让 Qwen2.5-3B 学出“鲜活但不过火”的琪露诺风格
- 保持技术类回答、建议类回答和拒答边界的基本可用性

## 当前推荐入口

推荐脚本：`sft/scripts/generate_sft_data_light.py`

原因：

- 比旧版脚本更轻
- 更适合角色扮演聊天项目
- 支持并发
- 有失败熔断
- 自带轻量本地质检
- 输出格式直接兼容当前 LLaMA-Factory 配置

## 输出文件

默认输出到 `sft/data`：

- `accepted_raw.jsonl`：通过样本，带评分、问题、hash、主题等信息
- `rejected_raw.jsonl`：未通过样本，仅在 `--save-rejected` 时生成
- `train_messages.jsonl`：训练集
- `val_messages.jsonl`：验证集

训练与验证文件格式为：

```json
{"conversations":[{"from":"system","value":"..."},{"from":"human","value":"..."},{"from":"gpt","value":"..."}]}
```

## 轻量脚本参数

常用参数：

- `--count`：目标通过样本数
- `--model`：生成模型
- `--critic-model`：审查模型，默认与生成模型相同
- `--output-dir`：输出目录，默认 `sft/data`
- `--samples-per-request`：每次请求返回几条候选
- `--min-score`：最低通过分
- `--min-turns`：最少 user/assistant 轮数
- `--max-turns`：最多 user/assistant 轮数
- `--refusal-ratio`：拒答场景比例
- `--identity-ratio`：身份稳定场景比例
- `--skip-critic`：跳过 LLM 审查，只用本地规则
- `--max-retries`：低分样本的重写次数
- `--workers`：并发 worker 数
- `--max-batches`：最大批次数，防止无限生成
- `--max-consecutive-failures`：连续失败熔断阈值
- `--resume`：断点续跑
- `--save-rejected`：保存未通过样本

## 推荐用法

### 1. 快速试风格

```bash
python sft/scripts/generate_sft_data_light.py --count 300 --workers 6 --samples-per-request 3 --skip-critic --min-score 76
```

适合场景：

- 先看“琪露诺味”对不对
- 先看 prompt 风格是否自然
- 不想一开始就花太多钱做 critic

### 2. 正式生成

```bash
python sft/scripts/generate_sft_data_light.py --count 800 --workers 4 --samples-per-request 3 --min-score 80 --max-retries 1 --save-rejected
```

适合场景：

- 做正式训练集
- 保留 rejected 方便回头看问题
- 希望质量比速度更稳一点

### 3. 使用 DeepSeek

`.env` 例如：

```text
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

命令例如：

```bash
python sft/scripts/generate_sft_data_light.py --model deepseek-chat --critic-model deepseek-chat --count 500 --workers 4 --samples-per-request 3 --min-score 80
```

## 并发建议

这版轻量脚本已经支持并发，但不建议一开始把并发开太高。

推荐起步：

- 同模型同时做生成和审查：`workers=3` 或 `4`
- 跳过 critic 只试风格：`workers=4` 到 `6`
- `samples-per-request` 先用 `2` 或 `3`

不建议盲目拉高到 `8+`，否则更容易遇到：

- 限流
- 超时
- 返回格式变差
- 审查质量下降

## 质量控制逻辑

轻量脚本的设计目标不是“超严格对齐”，而是“用少量规则挡掉最脏的样本”。

当前主要做这些检查：

- `messages` 结构是否合法
- 是否只有一条 `system`
- 是否严格 `user/assistant` 交替
- 是否泄露 prompt、memory、summary、session 等元信息
- 是否角色口头禅过多
- 是否感叹号、meme 过多
- 最后一轮助手是否真的回应了用户任务
- 低分样本是否能通过 rewrite 修回来

## 为什么推荐轻量脚本

旧版 `generate_sft_data.py` 更像一套重型流水线，逻辑很多，但对你这种项目并不一定更划算。

轻量脚本更适合现在的目标：

- 角色要鲜活，但不要演过头
- 要能聊天，也要能给出基本有用的回答
- 不需要为了边角收益引入太重的规则和成本

## 数据集建议

对于 3B 角色模型，建议优先追求“小而干净”，不要一开始就堆很大规模。

建议节奏：

1. 先做 `300` 到 `500` 条快速试风格
2. 人工抽查至少 `50` 到 `100` 条
3. 风格方向对了，再做 `800` 到 `1500` 条正式集
4. 用固定题目对比 base / 旧 SFT / 新 SFT

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

对话测试：

```bash
llamafactory-cli chat --model_name_or_path Qwen/Qwen2.5-3B-Instruct --adapter_name_or_path sft/checkpoints/lf_qwen2_5_3b_lora/checkpoint-350 --template qwen --infer_dtype bfloat16 --default_system "你是琪露诺，东方Project中的冰之妖精，现在正在和眼前的人类聊天并提供帮助。你的核心目标是在安全前提下给出准确、可执行、好懂的帮助。"
```

导出：

```bash
llamafactory-cli export sft/llamafactory/qwen2_5_3b_merge.yaml
llamafactory-cli export sft/llamafactory/qwen2_5_3b_int4.yaml
```

## 建议的训练侧取舍

如果数据还没稳定，不建议先靠多训几轮去“压出风格”。

更推荐：

- 先修数据
- 再训 2 到 3 个 epoch 看趋势
- 用人工对话评估，而不是只看 loss

## 现阶段建议

如果你现在的目标是尽快做出一个“比较鲜活的琪露诺”，建议直接按这条线走：

1. 用轻量脚本先生成 300 到 500 条快速数据
2. 抽查并调整风格
3. 再生成 800 到 1500 条正式数据
4. 用 LLaMA-Factory 跑 LoRA
5. 先聊天验证，再决定是否导出和量化
