# SFT 生成与训练一体化说明（角色扮演项目）

本文档合并了原 `explain.md` 与 `SFT_TRAINING_PLAN.md`，作为当前唯一权威说明。

## 1. 目标与推荐方案

- 目标：低成本、快速迭代“琪露诺角色扮演”小模型。
- 基座模型：`Qwen2.5-3B-Instruct`
- 微调方法：`QLoRA (4bit)`
- 训练框架：`LLaMA-Factory`

这个组合在中文角色对话场景下兼顾质量、速度和显存成本。

## 2. 生成脚本入口

- 脚本：`sft/scripts/generate_sft_data.py`
- 默认输出目录：`sft/data`

基础命令（推荐从轻量模式开始）：

```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2
```

## 3. 输出文件说明

运行后生成：

- `sft/data/accepted_raw.jsonl`
  - 通过样本，包含 `score/issues/retries/hash/topic/messages` 等元信息
- `sft/data/train_messages.jsonl`
  - 训练集，严格格式：`{"messages": [...]}`
- `sft/data/val_messages.jsonl`
  - 验证集，严格格式：`{"messages": [...]}`
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
- `--refusal-ratio`：拒绝场景采样比例，默认 `0.15`
- `--llm-retries`：单次 LLM 请求失败后重试次数，默认 `2`
- `--llm-backoff-base`：重试退避基础秒数，默认 `0.8`
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

示例（快速出数）：

```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2 --critic-sample-rate 0.4
```
示例微调数据500条，质检抽样比例50%：
```bash
python sft/scripts/generate_sft_data.py --mode lite --count 500 --samples-per-request 2 --critic-sample-rate 0.5 

```

## 8. 训练建议参数（LLaMA-Factory）

### 24GB 显存

- `quantization_bit`: 4
- `finetuning_type`: lora
- `lora_rank`: 16
- `lora_alpha`: 32
- `lora_dropout`: 0.05
- `learning_rate`: 1e-4 ~ 1.5e-4
- `per_device_train_batch_size`: 6
- `gradient_accumulation_steps`: 2
- `cutoff_len`: 1024
- `num_train_epochs`: 3

### 12GB 显存

- `quantization_bit`: 4
- `lora_rank`: 8 ~ 16
- `lora_alpha`: 16 ~ 32
- `lora_dropout`: 0.05
- `learning_rate`: 1e-4
- `per_device_train_batch_size`: 2
- `gradient_accumulation_steps`: 6
- `cutoff_len`: 1024
- `num_train_epochs`: 3

## 9. 最小可行迭代（MVP）

1. 先跑 `500` 条（lite）
2. 训练 1 轮快速验证
3. 人工抽样 100 条看三件事：
   - 人设稳定性
   - 日常对话自然度
   - 拒绝边界是否得体
4. 再扩到 `2000+` 条做正式训练

## 10. 验收标准

- 数据层：
  - schema 错误率 = 0
  - 重复率可控（去重后有效样本达标）
- 训练层：
  - 验证集 loss 稳定下降
- 效果层：
  - 人设一致性 >= 85%
  - 拒绝边界正确率 >= 95%
  - 回答可执行性 >= 80%（人工抽样）
