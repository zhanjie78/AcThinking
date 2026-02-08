from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mud_battle_bot.engine import BattleEngine
from mud_battle_bot.models import BattleLog, BattleState


@dataclass(slots=True)
class SubmitActionResult:
    message: str
    round_report: Optional[str] = None


class DuelService:
    def __init__(self, engine: BattleEngine) -> None:
        self.engine = engine

    def submit_action(self, battle: BattleState, user_id: int, mention_html: str) -> SubmitActionResult:
        if battle.player_a_id is None:
            battle.player_a_id = user_id
        elif battle.player_a_id != user_id and battle.player_b_id is None:
            battle.player_b_id = user_id
        elif user_id not in (battle.player_a_id, battle.player_b_id):
            return SubmitActionResult("当前房间为双人对局，无法加入")

        if user_id in battle.pending_action:
            return SubmitActionResult("你本回合已出招，等对方")

        fighter = battle.player if user_id == battle.player_a_id else battle.ai
        skill_no = self.engine.pick_locked_skill_number(battle, fighter)
        skill = self.engine.skills[self.engine.skill_number_to_key(skill_no)]
        battle.pending_action[user_id] = skill_no

        ack = "\n".join(
            [
                "回合开始咯，请等待玩家响应~",
                f"本轮{mention_html}要用{skill_no}号{skill.name}",
            ]
        )

        if battle.player_a_id is None or battle.player_b_id is None:
            return SubmitActionResult(ack)
        if battle.player_a_id not in battle.pending_action or battle.player_b_id not in battle.pending_action:
            return SubmitActionResult(ack)

        skill_a = self.engine.skill_number_to_key(battle.pending_action[battle.player_a_id])
        skill_b = self.engine.skill_number_to_key(battle.pending_action[battle.player_b_id])
        log = self.engine.advance_round(battle, forced_skill_player=skill_a, forced_skill_ai=skill_b)
        battle.pending_action = {}
        return SubmitActionResult(ack, round_report=self._render_report(battle, log))

    @staticmethod
    def _render_report(battle: BattleState, log: BattleLog) -> str:
        from mud_battle_bot.render import render_battle_log

        return render_battle_log(battle, log)
