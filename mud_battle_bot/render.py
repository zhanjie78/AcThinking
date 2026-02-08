from __future__ import annotations

from mud_battle_bot.engine import format_fighter_line
from mud_battle_bot.models import BattleLog, BattleState


NAME_TO_ROLE = {
    "玩家": "你",
    "AI": "AI",
}


def render_battle_log(battle: BattleState, log: BattleLog) -> str:
    lines: list[str] = []
    if _has_event(log, "already_over"):
        lines.append("本局已结束，请使用 /new 开启新战斗。")
        lines.extend(_tail_lines(battle))
        return "\n".join(lines)

    lines.append(f"=== 第 {log.round_no} 回合 ===")
    for event in log.events:
        if event.type == "round_start":
            continue
        if event.type == "forced_basic_attack":
            role = NAME_TO_ROLE.get(event.actor or "", event.actor or "")
            lines.append(f"{role}受到沉默影响，只能使用【普攻】。")
        elif event.type == "skill_use":
            role = NAME_TO_ROLE.get(event.actor or "", event.actor or "")
            lines.append(f"{role}使用【{event.detail['skill_name']}】。")
        elif event.type == "damage":
            target = "对方" if event.target == "AI" else "你"
            msg = f"造成 {event.detail['damage']} 伤害"
            if event.detail["shield_absorb"] > 0:
                msg += f"（其中护盾吸收 {event.detail['shield_absorb']}）"
            msg += f"，{target}损失HP {event.detail['hp_loss']}。"
            lines.append(msg)
        elif event.type == "status_apply":
            target = "对方" if event.target == "AI" else "你"
            status = event.detail["status"]
            if status == "poison":
                lines.append(
                    f"{target}进入中毒 {event.detail['duration']} 回合（每回合{event.detail['value']}DOT）。"
                )
            elif status == "silence":
                lines.append(f"{target}被沉默 {event.detail['duration']} 回合。")
        elif event.type == "miss":
            lines.append("技能未命中。")
        elif event.type == "shield_gain":
            role = NAME_TO_ROLE.get(event.actor or "", event.actor or "")
            lines.append(
                f"{role}获得护盾 {event.detail['shield_value']}，持续 {event.detail['duration']} 回合。"
            )
        elif event.type == "shield_expire":
            role = NAME_TO_ROLE.get(event.actor or "", event.actor or "")
            lines.append(f"{role}的护盾持续结束，剩余护盾清零。")

    lines.append("-- 回合结束DOT结算 --")
    dot_events = [event for event in log.events if event.type == "dot"]
    if not dot_events:
        lines.append("本回合无人中毒。")
    else:
        for event in dot_events:
            role = NAME_TO_ROLE.get(event.actor or "", event.actor or "")
            msg = f"{role}受到中毒DOT {event.detail['dot']}"
            if event.detail["shield_absorb"] > 0:
                msg += f"（护盾吸收 {event.detail['shield_absorb']}）"
            msg += f"，损失HP {event.detail['hp_loss']}。"
            lines.append(msg)

    lines.extend(_tail_lines(battle))
    if battle.is_over:
        if battle.winner == "平局":
            lines.append("本局结束：同归于尽，平局！")
        elif battle.winner == "玩家":
            lines.append("本局结束：你赢了，AI被你拿下！")
        else:
            lines.append("本局结束：你倒下了，AI获胜。")
    if battle.debug_mode and battle.seed is not None:
        lines.append(f"[debug] seed={battle.seed}")
    return "\n".join(lines)


def _tail_lines(battle: BattleState) -> list[str]:
    return [format_fighter_line(True, battle.player), format_fighter_line(False, battle.ai)]


def _has_event(log: BattleLog, event_type: str) -> bool:
    return any(item.type == event_type for item in log.events)
