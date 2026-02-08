from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SkillType(str, Enum):
    DAMAGE = "damage"
    APPLY_STATUS = "apply_status"
    ADD_SHIELD = "add_shield"


@dataclass(slots=True)
class Skill:
    key: str
    name: str
    type: SkillType
    cd: int
    weight: int = 0
    damage_min: int = 0
    damage_max: int = 0
    status: Optional[str] = None
    duration: int = 0
    value: int = 0
    chance: float = 1.0
    shield_value: int = 0


@dataclass(slots=True)
class StatusEffect:
    name: str
    duration: int
    value: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "duration": self.duration, "value": self.value}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatusEffect":
        return cls(name=data["name"], duration=int(data["duration"]), value=int(data.get("value", 0)))


@dataclass(slots=True)
class FighterState:
    name: str
    max_hp: int = 1200
    hp: int = 1200
    shield: int = 0
    statuses: List[StatusEffect] = field(default_factory=list)
    cooldowns: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "max_hp": self.max_hp,
            "hp": self.hp,
            "shield": self.shield,
            "statuses": [s.to_dict() for s in self.statuses],
            "cooldowns": self.cooldowns,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FighterState":
        return cls(
            name=data["name"],
            max_hp=int(data["max_hp"]),
            hp=int(data["hp"]),
            shield=int(data.get("shield", 0)),
            statuses=[StatusEffect.from_dict(item) for item in data.get("statuses", [])],
            cooldowns={k: int(v) for k, v in data.get("cooldowns", {}).items()},
        )


@dataclass(slots=True)
class Event:
    type: str
    actor: Optional[str] = None
    target: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BattleLog:
    round_no: int
    events: List[Event] = field(default_factory=list)


@dataclass(slots=True)
class BattleState:
    user_id: int
    player: FighterState
    ai: FighterState
    round_no: int = 0
    is_over: bool = False
    winner: Optional[str] = None
    seed: Optional[int] = None
    rng_state_b64: Optional[str] = None
    debug_mode: bool = False
    player_a_id: Optional[int] = None
    player_b_id: Optional[int] = None
    pending_action: Dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "player": self.player.to_dict(),
            "ai": self.ai.to_dict(),
            "round_no": self.round_no,
            "is_over": self.is_over,
            "winner": self.winner,
            "seed": self.seed,
            "rng_state_b64": self.rng_state_b64,
            "debug_mode": self.debug_mode,
            "player_a_id": self.player_a_id,
            "player_b_id": self.player_b_id,
            "pending_action": {str(k): v for k, v in self.pending_action.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BattleState":
        pending_raw = data.get("pending_action", {})
        pending_action = {int(k): int(v) for k, v in pending_raw.items()}
        return cls(
            user_id=int(data["user_id"]),
            player=FighterState.from_dict(data["player"]),
            ai=FighterState.from_dict(data["ai"]),
            round_no=int(data.get("round_no", 0)),
            is_over=bool(data.get("is_over", False)),
            winner=data.get("winner"),
            seed=data.get("seed"),
            rng_state_b64=data.get("rng_state_b64"),
            debug_mode=bool(data.get("debug_mode", False)),
            player_a_id=data.get("player_a_id"),
            player_b_id=data.get("player_b_id"),
            pending_action=pending_action,
        )
