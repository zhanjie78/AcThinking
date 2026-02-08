from __future__ import annotations

import base64
import json
import pickle
import random
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mud_battle_bot.models import BattleLog, BattleState, Event, FighterState, Skill, SkillType, StatusEffect

BASIC_ATTACK_KEY = "basic_attack"


class SkillConfigError(RuntimeError):
    pass


def load_skills(config_path: str = "config/skills.json") -> Dict[str, Skill]:
    try:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillConfigError(f"技能配置文件不存在: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SkillConfigError(f"技能配置文件格式错误: {exc}") from exc

    if not isinstance(payload, dict):
        raise SkillConfigError("技能配置必须是对象字典")

    skills: Dict[str, Skill] = {}
    for key, item in payload.items():
        skills[key] = Skill(
            key=key,
            name=item["name"],
            type=SkillType(item["type"]),
            cd=int(item["cd"]),
            weight=int(item.get("weight", 0)),
            damage_min=int(item.get("damage_min", 0)),
            damage_max=int(item.get("damage_max", 0)),
            status=item.get("status"),
            duration=int(item.get("duration", 0)),
            value=int(item.get("value", 0)),
            chance=float(item.get("chance", 1.0)),
            shield_value=int(item.get("shield_value", 0)),
        )
    if BASIC_ATTACK_KEY not in skills:
        raise SkillConfigError("技能配置缺少 basic_attack")
    return skills


class StatusHandler:
    def on_turn_start(self, fighter: FighterState, status: StatusEffect, events: List[Event]) -> bool:
        return True

    def on_before_action(self, fighter: FighterState, status: StatusEffect) -> Optional[str]:
        return None

    def on_damage_taken(self, fighter: FighterState, incoming_damage: int, status: StatusEffect) -> int:
        return incoming_damage

    def on_turn_end(self, fighter: FighterState, status: StatusEffect) -> int:
        return 0


class PoisonHandler(StatusHandler):
    def on_turn_end(self, fighter: FighterState, status: StatusEffect) -> int:
        return status.value


class SilenceHandler(StatusHandler):
    def on_before_action(self, fighter: FighterState, status: StatusEffect) -> Optional[str]:
        return BASIC_ATTACK_KEY


class ShieldHandler(StatusHandler):
    def on_turn_start(self, fighter: FighterState, status: StatusEffect, events: List[Event]) -> bool:
        if status.duration <= 0:
            if fighter.shield > 0:
                fighter.shield = 0
                events.append(Event(type="shield_expire", actor=fighter.name))
            return False
        return True

    def on_damage_taken(self, fighter: FighterState, incoming_damage: int, status: StatusEffect) -> int:
        absorbed = min(fighter.shield, incoming_damage)
        fighter.shield -= absorbed
        return incoming_damage - absorbed


STATUS_HANDLERS: Dict[str, StatusHandler] = {
    "poison": PoisonHandler(),
    "silence": SilenceHandler(),
    "shield": ShieldHandler(),
}


class BattleEngine:
    def __init__(self, skills: Dict[str, Skill]) -> None:
        self.skills = skills
        self.skill_order = list(skills.keys())

    def create_new_battle(self, user_id: int, seed: Optional[int] = None) -> BattleState:
        player = FighterState(name="玩家")
        ai = FighterState(name="AI")
        for fighter in (player, ai):
            for skill_key in self.skills:
                fighter.cooldowns[skill_key] = 0
        battle = BattleState(user_id=user_id, player=player, ai=ai, seed=seed)
        self._sync_rng_state(battle, random.Random(seed))
        return battle

    def set_seed(self, battle: BattleState, seed: int) -> None:
        battle.seed = seed
        self._sync_rng_state(battle, random.Random(seed))

    def skill_key_to_number(self, skill_key: str) -> int:
        return self.skill_order.index(skill_key) + 1

    def skill_number_to_key(self, skill_no: int) -> str:
        if skill_no < 1 or skill_no > len(self.skill_order):
            raise ValueError("invalid skill number")
        return self.skill_order[skill_no - 1]

    def pick_locked_skill_number(self, battle: BattleState, fighter: FighterState) -> int:
        rng = self.get_rng(battle)
        chosen = self._choose_skill(fighter, rng)
        self._sync_rng_state(battle, rng)
        return self.skill_key_to_number(chosen.key)

    def get_rng(self, battle: BattleState) -> random.Random:
        if battle.rng_state_b64:
            rng = random.Random()
            state = pickle.loads(base64.b64decode(battle.rng_state_b64.encode("ascii")))
            rng.setstate(state)
            return rng
        rng = random.Random(battle.seed)
        self._sync_rng_state(battle, rng)
        return rng

    def advance_round(
        self,
        battle: BattleState,
        forced_skill_player: Optional[str] = None,
        forced_skill_ai: Optional[str] = None,
    ) -> BattleLog:
        log = BattleLog(round_no=battle.round_no)
        if battle.is_over:
            log.events.append(Event(type="already_over"))
            return log

        rng = self.get_rng(battle)
        battle.round_no += 1
        log.round_no = battle.round_no
        log.events.append(Event(type="round_start", detail={"round": battle.round_no}))

        self._on_turn_start(battle.player, log.events)
        self._on_turn_start(battle.ai, log.events)

        self._take_action(battle.player, battle.ai, rng, log.events, forced_skill_key=forced_skill_player)
        if self._check_winner(battle, log.events):
            self._sync_rng_state(battle, rng)
            return log

        self._take_action(battle.ai, battle.player, rng, log.events, forced_skill_key=forced_skill_ai)
        if self._check_winner(battle, log.events):
            self._sync_rng_state(battle, rng)
            return log

        self._on_turn_end_dot(battle.player, log.events)
        self._on_turn_end_dot(battle.ai, log.events)
        self._check_winner(battle, log.events)
        self._sync_rng_state(battle, rng)
        return log

    def _on_turn_start(self, fighter: FighterState, events: List[Event]) -> None:
        for key, cd in fighter.cooldowns.items():
            if cd > 0:
                fighter.cooldowns[key] = cd - 1

        updated_statuses: List[StatusEffect] = []
        for status in fighter.statuses:
            dec_status = replace(status, duration=status.duration - 1)
            handler = STATUS_HANDLERS.get(dec_status.name, StatusHandler())
            keep = handler.on_turn_start(fighter, dec_status, events)
            if keep and dec_status.duration > 0:
                updated_statuses.append(dec_status)
        fighter.statuses = updated_statuses

    def _take_action(
        self,
        attacker: FighterState,
        defender: FighterState,
        rng: random.Random,
        events: List[Event],
        forced_skill_key: Optional[str] = None,
    ) -> None:
        selected_key = forced_skill_key
        for status in attacker.statuses:
            handler = STATUS_HANDLERS.get(status.name, StatusHandler())
            candidate = handler.on_before_action(attacker, status)
            if candidate:
                selected_key = candidate
                events.append(Event(type="forced_basic_attack", actor=attacker.name, detail={"reason": status.name}))
                break

        if selected_key and selected_key in self.skills and attacker.cooldowns.get(selected_key, 0) == 0:
            skill = self.skills[selected_key]
        elif selected_key == BASIC_ATTACK_KEY:
            skill = self.skills[BASIC_ATTACK_KEY]
        else:
            skill = self._choose_skill(attacker, rng)

        events.append(Event(type="skill_use", actor=attacker.name, detail={"skill_key": skill.key, "skill_name": skill.name}))
        self._execute_skill(attacker, defender, skill, rng, events)
        if skill.cd > 0 and skill.key != BASIC_ATTACK_KEY:
            attacker.cooldowns[skill.key] = skill.cd

    def _choose_skill(self, fighter: FighterState, rng: random.Random) -> Skill:
        candidates: List[Skill] = []
        weights: List[int] = []
        for key, skill in self.skills.items():
            if key == BASIC_ATTACK_KEY:
                continue
            if fighter.cooldowns.get(key, 0) == 0:
                candidates.append(skill)
                weights.append(skill.weight)
        if not candidates:
            return self.skills[BASIC_ATTACK_KEY]
        return rng.choices(candidates, weights=weights, k=1)[0]

    def _execute_skill(
        self,
        attacker: FighterState,
        defender: FighterState,
        skill: Skill,
        rng: random.Random,
        events: List[Event],
    ) -> None:
        if skill.type == SkillType.DAMAGE:
            damage = rng.randint(skill.damage_min, skill.damage_max)
            hp_loss, absorbed = self._apply_damage(defender, damage)
            events.append(
                Event(
                    type="damage",
                    actor=attacker.name,
                    target=defender.name,
                    detail={"damage": damage, "hp_loss": hp_loss, "shield_absorb": absorbed},
                )
            )
            return

        if skill.type == SkillType.APPLY_STATUS:
            if rng.random() <= skill.chance:
                assert skill.status is not None
                self._apply_status(defender, skill.status, skill.duration, skill.value)
                events.append(
                    Event(
                        type="status_apply",
                        actor=attacker.name,
                        target=defender.name,
                        detail={"status": skill.status, "duration": skill.duration, "value": skill.value},
                    )
                )
            else:
                events.append(Event(type="miss", actor=attacker.name, target=defender.name))
            return

        if skill.type == SkillType.ADD_SHIELD:
            attacker.shield += skill.shield_value
            self._apply_status(attacker, "shield", skill.duration, 0)
            events.append(
                Event(
                    type="shield_gain",
                    actor=attacker.name,
                    detail={"shield_value": skill.shield_value, "duration": skill.duration},
                )
            )

    def _apply_status(self, fighter: FighterState, name: str, duration: int, value: int) -> None:
        for idx, status in enumerate(fighter.statuses):
            if status.name == name:
                fighter.statuses[idx] = StatusEffect(name=name, duration=duration, value=value)
                return
        fighter.statuses.append(StatusEffect(name=name, duration=duration, value=value))

    def _apply_damage(self, fighter: FighterState, damage: int) -> Tuple[int, int]:
        remaining = damage
        before_shield = fighter.shield
        for status in fighter.statuses:
            handler = STATUS_HANDLERS.get(status.name)
            if handler is None:
                continue
            remaining = handler.on_damage_taken(fighter, remaining, status)
        absorbed = before_shield - fighter.shield
        hp_loss = max(0, remaining)
        fighter.hp = max(0, fighter.hp - hp_loss)
        return hp_loss, absorbed

    def _on_turn_end_dot(self, fighter: FighterState, events: List[Event]) -> None:
        dot_total = 0
        for status in fighter.statuses:
            handler = STATUS_HANDLERS.get(status.name)
            if handler is None:
                continue
            dot_total += handler.on_turn_end(fighter, status)
        if dot_total <= 0:
            return
        hp_loss, absorbed = self._apply_damage(fighter, dot_total)
        events.append(
            Event(
                type="dot",
                actor=fighter.name,
                detail={"dot": dot_total, "hp_loss": hp_loss, "shield_absorb": absorbed},
            )
        )

    def _check_winner(self, battle: BattleState, events: List[Event]) -> bool:
        p_dead = battle.player.hp <= 0
        a_dead = battle.ai.hp <= 0
        if not p_dead and not a_dead:
            return False
        battle.is_over = True
        if p_dead and a_dead:
            battle.winner = "平局"
        elif a_dead:
            battle.winner = "玩家"
        else:
            battle.winner = "AI"
        events.append(Event(type="battle_over", detail={"winner": battle.winner}))
        return True

    def _sync_rng_state(self, battle: BattleState, rng: random.Random) -> None:
        battle.rng_state_b64 = base64.b64encode(pickle.dumps(rng.getstate())).decode("ascii")


def get_status_text(battle: BattleState, skills: Dict[str, Skill]) -> str:
    lines = [f"当前回合：{battle.round_no}"]
    lines.append(format_fighter_line(True, battle.player))
    lines.append(format_fighter_line(False, battle.ai))
    lines.append(f"玩家A: {battle.player_a_id if battle.player_a_id is not None else '未加入'}")
    lines.append(f"玩家B: {battle.player_b_id if battle.player_b_id is not None else '未加入'}")
    if battle.pending_action:
        lines.append("本回合已提交动作：")
        for uid, skill_no in battle.pending_action.items():
            lines.append(f"- {uid}: {skill_no}")
    lines.append("你的技能CD：")
    lines.extend(_format_cd_lines(battle.player, skills))
    lines.append("对方技能CD：")
    lines.extend(_format_cd_lines(battle.ai, skills))
    if battle.seed is not None:
        lines.append(f"当前seed：{battle.seed}")
    if battle.is_over:
        lines.append(f"本局已结束，胜者：{battle.winner}")
    return "\n".join(lines)


def format_fighter_line(is_player: bool, fighter: FighterState) -> str:
    prefix = "你的狗命剩余" if is_player else "对方狗命剩余"
    extras: List[str] = []
    if fighter.shield > 0:
        extras.append(f"护盾{fighter.shield}")
    for status in fighter.statuses:
        if status.name == "poison":
            extras.append(f"中毒{status.duration}回合")
        elif status.name == "silence":
            extras.append(f"沉默{status.duration}回合")
        elif status.name == "shield":
            extras.append(f"盾效{status.duration}回合")
    if extras:
        return f"{prefix}：{fighter.hp}/{fighter.max_hp}（{'，'.join(extras)}）"
    return f"{prefix}：{fighter.hp}/{fighter.max_hp}"


def _format_cd_lines(fighter: FighterState, skills: Dict[str, Skill]) -> List[str]:
    out: List[str] = []
    for key, skill in skills.items():
        if key == BASIC_ATTACK_KEY:
            continue
        out.append(f"- {skill.name}: {fighter.cooldowns.get(key, 0)}")
    return out
