from mud_battle_bot.engine import BASIC_ATTACK_KEY, BattleEngine, load_skills
from mud_battle_bot.models import StatusEffect


def _engine() -> BattleEngine:
    return BattleEngine(load_skills("config/skills.json"))


def test_silence_forces_basic_attack() -> None:
    engine = _engine()
    battle = engine.create_new_battle(1, seed=42)
    battle.player.statuses.append(StatusEffect(name="silence", duration=2))

    log = engine.advance_round(battle)

    forced = [event for event in log.events if event.type == "forced_basic_attack" and event.actor == "玩家"]
    assert forced
    skill_use = [event for event in log.events if event.type == "skill_use" and event.actor == "玩家"][0]
    assert skill_use.detail["skill_key"] == BASIC_ATTACK_KEY


def test_shield_absorbs_before_hp() -> None:
    engine = _engine()
    battle = engine.create_new_battle(1, seed=7)
    battle.player.shield = 100
    battle.player.statuses.append(StatusEffect(name="shield", duration=2))

    hp_before = battle.player.hp
    hp_loss, absorbed = engine._apply_damage(battle.player, 130)

    assert absorbed == 100
    assert hp_loss == 30
    assert battle.player.hp == hp_before - 30
    assert battle.player.shield == 0


def test_poison_dot_on_turn_end() -> None:
    engine = _engine()
    battle = engine.create_new_battle(1, seed=1)
    battle.ai.statuses.append(StatusEffect(name="poison", duration=2, value=45))
    hp_before = battle.ai.hp

    log = engine.advance_round(battle)

    dot_events = [event for event in log.events if event.type == "dot" and event.actor == "AI"]
    assert dot_events
    assert dot_events[0].detail["dot"] == 45
    # DOT在回合末结算，可能被护盾吸收，因此检查HP或护盾至少发生变化
    assert battle.ai.hp < hp_before or dot_events[0].detail["shield_absorb"] > 0


def test_cooldown_decrements_once_at_turn_start() -> None:
    engine = _engine()
    battle = engine.create_new_battle(1, seed=3)
    battle.player.cooldowns["heavy_strike"] = 2
    battle.player.statuses.append(StatusEffect(name="silence", duration=2))

    engine.advance_round(battle)

    # 回合开始减1，且沉默强制普攻不会重置重击CD
    assert battle.player.cooldowns["heavy_strike"] == 1
