# Cirno Chat (CLI)

一个基于 DeepSeek API 的琪露诺聊天小项目（CLI 版本）。
支持长期本地记忆（SQLite）、会话恢复、记忆治理和SFT数据采样。

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

把 `.env.template` 的文件名改成 `.env`，然后至少填写 `DEEPSEEK_API_KEY`。这个keyy 是 DeepSeek API 的密钥，用于访问 DeepSeek API 服务。
参考网址：https://platform.deepseek.com/api_keys


### 3. 启动

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
  检查 `.env` 是否存在、`DEEPSEEK_API_KEY` 是否为真实值。
