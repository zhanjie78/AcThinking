from mud_battle_bot.duel import DuelService
from mud_battle_bot.engine import BattleEngine, load_skills


def _setup():
    engine = BattleEngine(load_skills("config/skills.json"))
    duel = DuelService(engine)
    battle = engine.create_new_battle(1001, seed=123)
    return engine, duel, battle


def test_first_submit_only_pending_no_settlement() -> None:
    _, duel, battle = _setup()

    result = duel.submit_action(battle, user_id=1, mention_html="@u1")

    assert result.round_report is None
    assert battle.pending_action.get(1) is not None
    assert battle.round_no == 0


def test_second_submit_triggers_once() -> None:
    _, duel, battle = _setup()
    duel.submit_action(battle, user_id=1, mention_html="@u1")

    result = duel.submit_action(battle, user_id=2, mention_html="@u2")

    assert result.round_report is not None
    assert battle.round_no == 1


def test_repeat_submit_same_player_not_override() -> None:
    _, duel, battle = _setup()
    duel.submit_action(battle, user_id=1, mention_html="@u1")
    first_skill = battle.pending_action[1]

    result = duel.submit_action(battle, user_id=1, mention_html="@u1")

    assert result.message == "你本回合已出招，等对方"
    assert battle.pending_action[1] == first_skill


def test_third_player_rejected() -> None:
    _, duel, battle = _setup()
    duel.submit_action(battle, user_id=1, mention_html="@u1")
    duel.submit_action(battle, user_id=2, mention_html="@u2")

    # 新回合后先让两人位固定，再尝试第三人
    result = duel.submit_action(battle, user_id=3, mention_html="@u3")

    assert result.message == "当前房间为双人对局，无法加入"


def test_pending_cleared_after_settlement() -> None:
    _, duel, battle = _setup()
    duel.submit_action(battle, user_id=1, mention_html="@u1")

    result = duel.submit_action(battle, user_id=2, mention_html="@u2")

    assert result.round_report is not None
    assert battle.pending_action == {}
