from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEAM_ALIASES = {
    "betboom": "BoomBoys",
    "bet boom": "BoomBoys",
    "betboom team": "BoomBoys",
    "bb": "BoomBoys",
    "falcons": "Team Falcons",
    "liquid": "Team Liquid",
    "spirit": "Team Spirit",
    "pvision": "PVISION",
    "parivision": "PVISION",
    "xtreme": "Xtreme Gaming",
    "virtus": "Virtus.pro",
    "vp": "Virtus.pro",
    "yandex": "Team Yandex",
    "vici": "Vici Gaming",
    "gl": "GamerLegion",
    "team vision": "TEAM VISION",
    "1w team": "Iron Wing TI 2026",
    "iron wing": "Iron Wing TI 2026",
    "iron wing ti 2026": "Iron Wing TI 2026",
}

ROLE_LABELS = {
    1: "carry",
    2: "mid",
    3: "offlane",
    4: "support",
    5: "hard_support",
}

ROLE_GROUPS = {
    1: "core",
    2: "mid",
    3: "core",
    4: "support",
    5: "support",
}


@dataclass(frozen=True)
class RosterPlayer:
    official_name: str
    official_position: int
    role_label: str
    role_group: str


@dataclass(frozen=True)
class RosterTeam:
    team_name: str
    source_team_name: str
    qualification_status: str
    qualification_path: str | None
    region: str | None
    players: list[RosterPlayer]


@dataclass
class ObservedPlayer:
    account_id: int
    name: str | None
    personaname: str | None
    maps_seen: int
    avg_gpm: float
    avg_last_hits: float
    avg_xpm: float
    avg_observers: float
    inferred_position: int


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    lowered = str(value).strip().lower()
    lowered = lowered.replace("ё", "е")
    return re.sub(r"[^a-z0-9]+", "", lowered)


def canonical_team_name(name: str | None) -> str | None:
    if not name:
        return None
    text = str(name).strip()
    lookup = TEAM_ALIASES.get(text.lower())
    return lookup or text


def parse_ti2026_participants_from_raw(raw_text: str) -> tuple[int | None, list[RosterTeam]]:
    league_match = re.search(r"\|leagueid\s*=\s*(\d+)", raw_text)
    league_id = int(league_match.group(1)) if league_match else None
    if "==Participants==" not in raw_text or "==Results==" not in raw_text:
        raise RuntimeError("Could not locate Participants/Results sections in Liquipedia raw text")
    participants_section = raw_text.split("==Participants==", 1)[1].split("==Results==", 1)[0]
    blocks = participants_section.split("|{{Opponent|")[1:]
    teams: list[RosterTeam] = []
    for block in blocks:
        first_line = block.splitlines()[0].strip()
        source_team_name = first_line.rstrip("}")
        team_name = canonical_team_name(source_team_name) or source_team_name

        players: list[RosterPlayer] = []
        for line in block.splitlines():
            line = line.strip()
            if "status=former" in line or "results=false" in line:
                continue
            match = re.search(r"\{\{Person\|role=(\d)\|([^|}]+)", line)
            if not match:
                continue
            position = int(match.group(1))
            if position not in ROLE_LABELS:
                continue
            official_name = match.group(2).strip()
            players.append(
                RosterPlayer(
                    official_name=official_name,
                    official_position=position,
                    role_label=ROLE_LABELS[position],
                    role_group=ROLE_GROUPS[position],
                )
            )
        players.sort(key=lambda row: row.official_position)
        if len(players) != 5:
            continue

        qualification_status = "qualified"
        qualification_path: str | None = None
        region: str | None = None
        q_match = re.search(r"\|qualification=\{\{Qualification\|([^}]*)\}\}", block)
        if q_match:
            inner = q_match.group(1)
            if "method=invite" in inner:
                qualification_status = "invite"
                qualification_path = "invite"
            elif "method=qual" in inner:
                qualification_status = "regional_qualifier"
                text_match = re.search(r"\|text=([^|}]+)", inner)
                placement_match = re.search(r"\|placement=([^|}]+)", inner)
                region = text_match.group(1).strip() if text_match else None
                placement = placement_match.group(1).strip() if placement_match else None
                qualification_path = f"{region} qualifier" if region else "regional qualifier"
                if placement:
                    qualification_path = f"{qualification_path} ({placement})"

        teams.append(
            RosterTeam(
                team_name=team_name,
                source_team_name=source_team_name,
                qualification_status=qualification_status,
                qualification_path=qualification_path,
                region=region,
                players=players,
            )
        )
    return league_id, teams


def serialize_roster_text(players: list[RosterPlayer]) -> str:
    return ", ".join(f"{player.official_position}:{player.official_name}" for player in sorted(players, key=lambda row: row.official_position))


def load_prior_identities(source_db_path: Path | None) -> dict[str, int]:
    if source_db_path is None or not source_db_path.exists():
        return {}
    con = sqlite3.connect(str(source_db_path))
    try:
        rows = con.execute(
            """
            SELECT official_name, account_id
            FROM player_identity_registry
            GROUP BY official_name, account_id
            """
        ).fetchall()
    finally:
        con.close()
    result: dict[str, int] = {}
    for official_name, account_id in rows:
        if official_name and account_id is not None:
            result[normalize_name(str(official_name))] = int(account_id)
    return result


def infer_positions_from_observed(observed_rows: list[dict[str, Any]]) -> list[ObservedPlayer]:
    rows: list[ObservedPlayer] = []
    for row in observed_rows:
        rows.append(
            ObservedPlayer(
                account_id=int(row["account_id"]),
                name=row.get("name"),
                personaname=row.get("personaname"),
                maps_seen=int(row.get("maps_seen", 0)),
                avg_gpm=float(row.get("avg_gpm", 0.0)),
                avg_last_hits=float(row.get("avg_last_hits", 0.0)),
                avg_xpm=float(row.get("avg_xpm", 0.0)),
                avg_observers=float(row.get("avg_observers", 0.0)),
                inferred_position=0,
            )
        )
    ranking = sorted(
        rows,
        key=lambda row: (
            -row.avg_last_hits,
            -row.avg_gpm,
            -row.avg_xpm,
            row.avg_observers,
            row.account_id,
        ),
    )
    for index, row in enumerate(ranking, start=1):
        row.inferred_position = index
    return rows


def resolve_team_identity(
    roster_team: RosterTeam,
    observed_rows: list[dict[str, Any]],
    prior_identities: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    prior_identities = prior_identities or {}
    observed = infer_positions_from_observed(observed_rows)
    by_account = {row.account_id: row for row in observed}
    unmatched_observed = set(by_account)
    result: list[dict[str, Any]] = []

    def observed_match_key(row: ObservedPlayer) -> set[str]:
        return {normalize_name(row.name), normalize_name(row.personaname)}

    for player in roster_team.players:
        official_key = normalize_name(player.official_name)
        chosen: ObservedPlayer | None = None
        confidence = 0.95
        position_source = "liquipedia_official_role"
        identity_source = "liquipedia_name_match"

        for account_id in list(unmatched_observed):
            row = by_account[account_id]
            if official_key and official_key in observed_match_key(row):
                chosen = row
                break

        if chosen is None and official_key in prior_identities and prior_identities[official_key] in unmatched_observed:
            chosen = by_account[prior_identities[official_key]]
            confidence = 0.85
            identity_source = "liquipedia_name_plus_ewc_prior"

        if chosen is None:
            candidate_pool = [by_account[account_id] for account_id in unmatched_observed]
            candidate_pool.sort(key=lambda row: (abs(row.inferred_position - player.official_position), row.inferred_position))
            if candidate_pool:
                chosen = candidate_pool[0]
                confidence = 0.55
                identity_source = "liquipedia_role_heuristic"
                position_source = "liquipedia_role_heuristic"

        if chosen is None:
            continue

        unmatched_observed.discard(chosen.account_id)
        result.append(
            {
                "account_id": chosen.account_id,
                "team_name": roster_team.team_name,
                "official_name": player.official_name,
                "db_player_name": chosen.name or chosen.personaname or player.official_name,
                "public_personaname": chosen.personaname or chosen.name or player.official_name,
                "official_position": player.official_position,
                "role_label": player.role_label,
                "role_group": player.role_group,
                "position_source": position_source,
                "identity_source": identity_source,
                "confidence_score": confidence,
                "confidence_label": "high" if confidence >= 0.9 else ("medium" if confidence >= 0.75 else "low"),
                "maps_seen": chosen.maps_seen,
                "maps_at_position": chosen.maps_seen,
                "avg_fantasy_score": None,
                "best_map_fantasy_score": None,
                "source_name": "Liquipedia + OpenDota",
                "source_url": None,
                "notes": f"observed_name={chosen.name}; observed_personaname={chosen.personaname}; inferred_position={chosen.inferred_position}",
            }
        )
    result.sort(key=lambda row: row["official_position"])
    return result
