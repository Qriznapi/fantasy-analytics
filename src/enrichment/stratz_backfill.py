from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .opendota_backfill import mark_fetch_error, refresh_backfill_views, upsert_raw_payload
from .stat_source_map import STAT_SOURCE_MAP


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "ewc_2026_fantasy_compact.sqlite"
STRATZ_GRAPHQL_URL = "https://api.stratz.com/graphql"
STRATZ_SUPPORTED_STATS = ["watchers_taken", "lotus"]

# Inference note:
# The endpoint is consistent with the public STRATZ GraphiQL endpoint and third-party
# wrappers that target the official STRATZ GraphQL API at api.stratz.com/graphql.
# Exact player-level fields for watchers/lotus/tormentor still need schema confirmation
# against a real tokened environment, so this first iteration is deliberately marked
# experimental and preflight-oriented.
DEFAULT_STRATZ_MATCH_QUERY = """
query MatchBackfillProbe($matchId: Long!) {
  match(id: $matchId) {
    id
    players {
      steamAccountId
    }
  }
}
""".strip()

DEFAULT_STRATZ_SCHEMA_PROBE = """
query FantasySchemaProbe {
  __schema {
    types {
      name
      fields {
        name
      }
    }
  }
}
""".strip()


def _load_env_if_present() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_stratz_token() -> str | None:
    _load_env_if_present()
    return (
        os.getenv("STRATZ_API_TOKEN")
        or os.getenv("STRATZ_BEARER_TOKEN")
        or os.getenv("STRATZ_TOKEN")
    )


def execute_stratz_graphql(
    *,
    query: str,
    variables: dict[str, Any] | None = None,
    timeout_sec: int = 30,
) -> tuple[dict[str, Any], int]:
    token = get_stratz_token()
    if not token:
        raise RuntimeError(
            "Missing STRATZ token. Set STRATZ_API_TOKEN, STRATZ_BEARER_TOKEN, or STRATZ_TOKEN."
        )

    payload = json.dumps(
        {
            "query": query,
            "variables": variables or {},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        STRATZ_GRAPHQL_URL,
        data=payload,
        headers={
            "User-Agent": "fantasy-analytics-stratz-backfill/0.1",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        body = response.read()
        decoded = json.loads(body.decode("utf-8"))
        return decoded, getattr(response, "status", 200)


def fetch_stratz_match_probe(match_id: int, *, timeout_sec: int = 30) -> tuple[dict[str, Any], int]:
    return execute_stratz_graphql(
        query=DEFAULT_STRATZ_MATCH_QUERY,
        variables={"matchId": int(match_id)},
        timeout_sec=timeout_sec,
    )


def fetch_stratz_schema_probe(*, timeout_sec: int = 60) -> tuple[dict[str, Any], int]:
    return execute_stratz_graphql(
        query=DEFAULT_STRATZ_SCHEMA_PROBE,
        timeout_sec=timeout_sec,
    )


def _extract_schema_keyword_hits(payload: dict[str, Any], keywords: list[str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    types = (((payload.get("data") or {}).get("__schema") or {}).get("types")) or []
    for type_entry in types:
        type_name = str(type_entry.get("name") or "")
        for field in type_entry.get("fields") or []:
            field_name = str(field.get("name") or "")
            lower = f"{type_name}.{field_name}".lower()
            for keyword in keywords:
                if keyword.lower() in lower:
                    hits.append(
                        {
                            "keyword": keyword,
                            "type_name": type_name,
                            "field_name": field_name,
                        }
                    )
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for hit in hits:
        key = (hit["keyword"], hit["type_name"], hit["field_name"])
        if key not in seen:
            seen.add(key)
            deduped.append(hit)
    return deduped


def run_stratz_preflight(
    con: sqlite3.Connection,
    *,
    match_ids: list[int],
    timeout_sec: int = 30,
    write_raw: bool = True,
    schema_probe: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    token_present = bool(get_stratz_token())
    schema_hits: list[dict[str, str]] = []

    if not token_present:
        return {
            "token_present": False,
            "results": [],
            "errors": [
                {
                    "match_id": None,
                    "error": "Missing STRATZ_API_TOKEN / STRATZ_BEARER_TOKEN / STRATZ_TOKEN",
                }
            ],
            "schema_hits": [],
            "supported_stats": STRATZ_SUPPORTED_STATS,
        }

    if schema_probe:
        try:
            payload, http_status = fetch_stratz_schema_probe(timeout_sec=max(timeout_sec, 60))
            schema_hits = _extract_schema_keyword_hits(payload, ["watch", "lotus", "tormentor", "mini"])
            if write_raw:
                upsert_raw_payload(
                    con,
                    source_name="stratz",
                    match_id=0,
                    payload=payload,
                    http_status=http_status,
                    parse_status="schema_probe_ok" if not payload.get("errors") else "schema_probe_graphql_errors",
                    notes="schema_probe",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append({"match_id": 0, "error": f"schema_probe_failed: {exc}"})

    for match_id in match_ids:
        try:
            payload, http_status = fetch_stratz_match_probe(match_id, timeout_sec=timeout_sec)
            graph_errors = payload.get("errors") or []
            parse_status = "graphql_errors" if graph_errors else "ok"
            if write_raw:
                upsert_raw_payload(
                    con,
                    source_name="stratz",
                    match_id=match_id,
                    payload=payload,
                    http_status=http_status,
                    parse_status=parse_status,
                    notes="experimental_stratz_probe",
                )
            results.append(
                {
                    "match_id": match_id,
                    "http_status": http_status,
                    "parse_status": parse_status,
                    "errors_present": bool(graph_errors),
                    "top_level_keys": sorted(payload.keys()),
                }
            )
        except urllib.error.HTTPError as exc:
            error_text = f"HTTP {exc.code}: {exc.reason}"
            errors.append({"match_id": match_id, "error": error_text})
            if write_raw:
                mark_fetch_error(con, source_name="stratz", match_id=match_id, error_text=error_text)
        except Exception as exc:  # noqa: BLE001
            errors.append({"match_id": match_id, "error": str(exc)})
            if write_raw:
                mark_fetch_error(con, source_name="stratz", match_id=match_id, error_text=str(exc))

    for stat_name in STRATZ_SUPPORTED_STATS:
        meta = STAT_SOURCE_MAP[stat_name]
        con.execute(
            """
            UPDATE fantasy_scoring_stat_catalog
            SET preferred_source = ?,
                fallback_source = ?,
                source_field_name = ?,
                coverage_status = ?
            WHERE stat_name = ?
            """,
            (
                meta["preferred_source"],
                meta["fallback_source"],
                meta["source_field_name"],
                "stratz_probe_pending" if token_present else meta["coverage_status"],
                stat_name,
            ),
        )
    con.commit()
    refresh_backfill_views(con)

    return {
        "token_present": True,
        "results": results,
        "errors": errors,
        "schema_hits": schema_hits,
        "supported_stats": STRATZ_SUPPORTED_STATS,
    }
