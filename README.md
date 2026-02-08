# Telegram 回合制对战机器人（双人同步出招）

基于 `python-telegram-bot v20+` 的异步机器人示例，支持 `/start` `/new` `/fight` `/status` `/seed` `/help`。

## 快速开始

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 设置 Token：

```bash
export TELEGRAM_BOT_TOKEN="<your_token>"
```

3. 启动：

```bash
python main.py
```

## 对战流程（群聊）

- 双方玩家在同一个 chat 中发送 `开始回合.干` 或 `.干`。
- 第一位提交后仅锁定本回合动作，机器人会提示等待对方。
- 第二位提交后才会统一结算一次完整回合。

## 持久化说明

- 默认 SQLite 数据库路径：`data/battles.db`
- BattleState 以 JSON 存储，并维护 `updated_at` 字段
- 机器人重启后，仍可继续之前对局（包括本回合 pending action）

## 技能配置

- 技能参数位于 `config/skills.json`
- 可直接修改伤害、CD、权重、状态参数，无需改代码
