"""
models.py — strutture dati tipizzate per i risultati dello scraping.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class TeamStanding:
    """Una riga di classifica."""
    position: Optional[int]
    team: str
    played: Optional[int]
    won: Optional[int]
    drawn: Optional[int]
    lost: Optional[int]
    goals_for: Optional[int]
    goals_against: Optional[int]
    goal_diff: Optional[int]
    points: Optional[int]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StatRow:
    """Una riga di statistica di una partita (label + valore casa/trasferta)."""
    label: str
    home: str
    away: str

    def to_dict(self) -> dict:
        return asdict(self)
