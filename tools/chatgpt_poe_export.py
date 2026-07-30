#!/usr/bin/env python3
"""Temporary poe.ninja PoE2 build exporter.

Fetches the filtered build roster from poe.ninja, downloads each character's
Path of Building export, validates the compressed XML, and writes codes sorted
by DPS descending.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import math
import re
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

API_BASE = "https://poe.ninja/poe2/api"
LEAGUE_SLUG = "runesofaldur"
TARGET_COUNT = 100
MAX_SNAPSHOTS = 10
REQUEST_DELAY_SECONDS = 0.65
OUT_DIR = Path("artifacts/poe")
ANNOTATED_PATH = OUT_DIR / "pob_codes_sorted_by_dps.txt"
CODES_ONLY_PATH = OUT_DIR / "pob_codes_only_sorted_by_dps.txt"
STATUS_PATH = OUT_DIR / "status.json"

FILTER_PARAMS: dict[str, str | int] = {
    "class": "Martial Artist",
    "skills": "Whirling Assault,Hollow Form",
    "keypassives": "Chaos Inoculation",
    "min-dps": 250000,
    "sort": "dps",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": f"https://poe.ninja/poe2/builds/{LEAGUE_SLUG}",
}

LOG = logging.getLogger("poe-export")


@dataclass(frozen=True)
class Snapshot:
    version: str
    snapshot_name: str
    league_name: str
    source_label: str


@dataclass
class ExportedBuild:
    dps: float
    account: str
    character: str
    code: str
    snapshot_version: str
    snapshot_name: str
    current_snapshot: bool
    search_rank: int
    skills_seen: tuple[str, ...]
    keystones_seen: tuple[str, ...]


class PoeNinjaClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._last_request = 0.0

    def close(self) -> None:
        self.session.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        remaining = REQUEST_DELAY_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 45.0,
        max_attempts: int = 8,
    ) -> requests.Response:
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            self._throttle()
            try:
                response = self.session.get(url, params=params, timeout=timeout)
                self._last_request = time.monotonic()
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else delay
                    except (TypeError, ValueError):
                        wait = delay
                    wait = min(max(wait, delay), 90.0)
                    LOG.warning(
                        "HTTP 429; attempt %d/%d, sleeping %.1fs",
                        attempt,
                        max_attempts,
                        wait,
                    )
                    time.sleep(wait)
                    delay = min(delay * 2.0, 90.0)
                    continue
                if response.status_code >= 500:
                    LOG.warning(
                        "HTTP %d; attempt %d/%d",
                        response.status_code,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2.0, 60.0)
                    continue
                response.raise_for_status()
                return response
            except (requests.RequestException, TimeoutError) as exc:
                last_error = exc
                LOG.warning(
                    "request failed (%s); attempt %d/%d",
                    exc,
                    attempt,
                    max_attempts,
                )
                time.sleep(delay)
                delay = min(delay * 2.0, 60.0)
        raise RuntimeError(
            f"request failed after {max_attempts} attempts: {url}"
        ) from last_error


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(buf):
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("invalid protobuf varint")
    raise ValueError("protobuf varint overran buffer")


def decode_fields(buf: bytes) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    pos = 0
    while pos < len(buf):
        tag, pos = read_varint(buf, pos)
        field_number = tag >> 3
        wire_type = tag & 7
        if wire_type == 0:
            value, pos = read_varint(buf, pos)
            fields.append({"field": field_number, "wire": 0, "value": value})
        elif wire_type == 1:
            if pos + 8 > len(buf):
                break
            fields.append(
                {"field": field_number, "wire": 1, "data": buf[pos : pos + 8]}
            )
            pos += 8
        elif wire_type == 2:
            length, pos = read_varint(buf, pos)
            end = pos + length
            if end > len(buf):
                raise ValueError("length-delimited protobuf field overran buffer")
            fields.append({"field": field_number, "wire": 2, "data": buf[pos:end]})
            pos = end
        elif wire_type == 5:
            if pos + 4 > len(buf):
                break
            fields.append(
                {"field": field_number, "wire": 5, "data": buf[pos : pos + 4]}
            )
            pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type: {wire_type}")
    return fields


def first_message(fields: list[dict[str, Any]], field_number: int) -> bytes | None:
    for field in fields:
        if field["field"] == field_number and field["wire"] == 2:
            return field["data"]
    return None


def decode_utf8(data: bytes) -> str | None:
    try:
        value = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return value if value else None


def decode_search(payload: bytes) -> tuple[int, dict[str, list[Any]]]:
    outer = decode_fields(payload)
    result_data = first_message(outer, 1)
    if not result_data:
        raise ValueError("search protobuf has no outer result field")
    inner = decode_fields(result_data)

    total = 0
    columns: dict[str, list[Any]] = {}

    for field in inner:
        if field["field"] == 1 and field["wire"] == 0:
            total = int(field["value"])
        elif field["field"] == 5 and field["wire"] == 2:
            column_fields = decode_fields(field["data"])
            name = ""
            values: list[Any] = []
            for column_field in column_fields:
                if column_field["field"] == 1 and column_field["wire"] == 2:
                    name = decode_utf8(column_field["data"]) or ""
                elif column_field["field"] == 2 and column_field["wire"] == 2:
                    value_fields = decode_fields(column_field["data"])
                    for value_field in value_fields:
                        if value_field["field"] != 1:
                            continue
                        if value_field["wire"] == 2:
                            text = decode_utf8(value_field["data"])
                            if text is not None:
                                values.append(text)
                        elif value_field["wire"] == 0:
                            values.append(int(value_field["value"]))
            if name:
                columns[name] = values

    if not columns.get("name") or not columns.get("account"):
        raise ValueError(
            f"search protobuf missing name/account columns; got {sorted(columns)}"
        )
    return total, columns


def row_value(columns: dict[str, list[Any]], key: str, index: int) -> Any:
    values = columns.get(key, [])
    return values[index] if index < len(values) else None


def to_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else 0.0
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return 0.0
    return 0.0


def search_dps(columns: dict[str, list[Any]], index: int) -> float:
    preferred = (
        "dps",
        "totaldps",
        "totalDps",
        "skilldps",
        "skillDps",
        "damage",
    )
    for key in preferred:
        number = to_number(row_value(columns, key, index))
        if number > 0:
            return number
    for key in sorted(columns):
        if "dps" not in key.lower():
            continue
        number = to_number(row_value(columns, key, index))
        if number > 0:
            return number
    return 0.0


def resolve_snapshots(client: PoeNinjaClient) -> list[Snapshot]:
    response = client.get(f"{API_BASE}/data/index-state")
    data = response.json()
    snapshots: list[Snapshot] = []
    for raw in data.get("snapshotVersions", []):
        if raw.get("url") != LEAGUE_SLUG:
            continue
        version = str(raw.get("version") or "")
        snapshot_name = str(raw.get("snapshotName") or "")
        if not version or not snapshot_name:
            continue
        labels = raw.get("timeMachineLabels") or []
        source_label = ",".join(map(str, labels)) if labels else "current"
        snapshots.append(
            Snapshot(
                version=version,
                snapshot_name=snapshot_name,
                league_name=str(raw.get("name") or "Runes of Aldur"),
                source_label=source_label,
            )
        )
    if not snapshots:
        raise RuntimeError(f"no snapshots found for league {LEAGUE_SLUG}")
    return snapshots


def fetch_roster(
    client: PoeNinjaClient,
    snapshot: Snapshot,
) -> tuple[int, list[dict[str, Any]], list[str]]:
    params: dict[str, Any] = {"overview": snapshot.snapshot_name, **FILTER_PARAMS}
    response = client.get(
        f"{API_BASE}/builds/{quote(snapshot.version)}/search",
        params=params,
    )
    total, columns = decode_search(response.content)
    names = columns.get("name", [])
    accounts = columns.get("account", [])
    row_count = min(len(names), len(accounts))
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        rows.append(
            {
                "name": str(names[index]),
                "account": str(accounts[index]),
                "search_dps": search_dps(columns, index),
                "search_rank": index + 1,
            }
        )
    return total, rows, sorted(columns)


def collect_skill_names(character: dict[str, Any]) -> tuple[str, ...]:
    names: set[str] = set()

    def visit(obj: Any, *, parent_key: str = "") -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                lower = key.lower()
                if lower in {"name", "skillname", "displayname"} and isinstance(
                    value, str
                ):
                    if parent_key.lower() in {
                        "skills",
                        "allgems",
                        "gems",
                        "skillgroups",
                        "socketedgems",
                    }:
                        names.add(value)
                visit(value, parent_key=key)
        elif isinstance(obj, list):
            for value in obj:
                visit(value, parent_key=parent_key)

    visit(character.get("skills", []), parent_key="skills")
    return tuple(sorted(names))


def collect_keystone_names(character: dict[str, Any]) -> tuple[str, ...]:
    names: set[str] = set()
    for entry in character.get("keystones", []) or []:
        if isinstance(entry, str):
            names.add(entry)
        elif isinstance(entry, dict):
            value = entry.get("name") or entry.get("displayName")
            if isinstance(value, str):
                names.add(value)
    return tuple(sorted(names))


def character_dps(character: dict[str, Any]) -> float:
    candidates: list[float] = []

    def visit(obj: Any, *, key: str = "") -> None:
        if isinstance(obj, dict):
            for child_key, value in obj.items():
                lower = child_key.lower()
                if lower in {
                    "dps",
                    "totaldps",
                    "totaldotdps",
                    "dotdps",
                    "combineddps",
                    "fulldps",
                }:
                    if isinstance(value, (list, dict)):
                        visit(value, key=child_key)
                    else:
                        number = to_number(value)
                        if number > 0:
                            candidates.append(number)
                else:
                    visit(value, key=child_key)
        elif isinstance(obj, list):
            for value in obj:
                visit(value, key=key)

    visit(character.get("skills", []), key="skills")
    if not candidates:
        visit(character.get("stats", {}), key="stats")
    return max(candidates, default=0.0)


def decode_pob_xml(code: str) -> str:
    normalized = code.strip().replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    raw = base64.b64decode(normalized, validate=False)
    errors: list[Exception] = []
    for decoder in (
        zlib.decompress,
        gzip.decompress,
        lambda data: zlib.decompress(data, -zlib.MAX_WBITS),
    ):
        try:
            xml = decoder(raw).decode("utf-8", errors="strict")
            if "PathOfBuilding" in xml:
                return xml
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    raise ValueError(
        f"invalid PoB export; decoders failed: {errors[-1] if errors else 'unknown'}"
    )


def fetch_character(
    client: PoeNinjaClient,
    snapshot: Snapshot,
    account: str,
    character: str,
) -> dict[str, Any]:
    params = {
        "overview": snapshot.snapshot_name,
        "account": account,
        "name": character,
    }
    response = client.get(
        f"{API_BASE}/builds/{quote(snapshot.version)}/character",
        params=params,
        timeout=60.0,
    )
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("character endpoint returned non-object JSON")
    return data


def format_dps(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def write_outputs(
    builds: list[ExportedBuild],
    *,
    current_snapshot: Snapshot,
    current_total: int,
    snapshots_used: list[str],
    search_columns: list[str],
    failures: list[dict[str, Any]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    header = [
        "# poe.ninja PoE2 Path of Building exports",
        f"# League: {current_snapshot.league_name} ({LEAGUE_SLUG})",
        (
            f"# Current snapshot: {current_snapshot.version} / "
            f"{current_snapshot.snapshot_name}"
        ),
        (
            "# Filters: class=Martial Artist; skills=Whirling Assault,Hollow Form; "
            "keypassives=Chaos Inoculation; min-dps=250000; sort=dps"
        ),
        f"# Current filtered population reported by search: {current_total}",
        f"# Validated unique PoB codes exported: {len(builds)}",
        "# Ordering: DPS descending (character payload, falling back to search DPS)",
        (
            "# Each code was base64url-decoded, decompressed, and checked for "
            "PathOfBuilding XML."
        ),
        "",
    ]

    annotated_lines = list(header)
    code_lines: list[str] = []
    for rank, build in enumerate(builds, 1):
        snapshot_marker = "current" if build.current_snapshot else build.snapshot_version
        annotated_lines.extend(
            [
                (
                    f"### {rank:03d} | DPS={format_dps(build.dps)} | "
                    f"{build.account}/{build.character} | "
                    f"snapshot={snapshot_marker}"
                ),
                build.code,
                "",
            ]
        )
        code_lines.extend([build.code, ""])

    ANNOTATED_PATH.write_text(
        "\n".join(annotated_lines).rstrip() + "\n",
        encoding="utf-8",
    )
    CODES_ONLY_PATH.write_text(
        "\n".join(code_lines).rstrip() + "\n",
        encoding="utf-8",
    )

    status = {
        "ok": len(builds) >= TARGET_COUNT,
        "target_count": TARGET_COUNT,
        "exported_count": len(builds),
        "current_snapshot": {
            "version": current_snapshot.version,
            "snapshot_name": current_snapshot.snapshot_name,
            "filtered_total": current_total,
        },
        "snapshots_used": snapshots_used,
        "search_columns": search_columns,
        "failures": failures,
        "files": {
            "annotated": str(ANNOTATED_PATH),
            "codes_only": str(CODES_ONLY_PATH),
        },
    }
    STATUS_PATH.write_text(
        json.dumps(status, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    client = PoeNinjaClient()
    failures: list[dict[str, Any]] = []
    exported: list[ExportedBuild] = []
    seen_characters: set[tuple[str, str]] = set()
    seen_codes: set[str] = set()
    snapshots_used: list[str] = []
    current_total = 0
    all_search_columns: set[str] = set()

    try:
        snapshots = resolve_snapshots(client)
        current = snapshots[0]
        LOG.info(
            "resolved %d snapshots; current=%s overview=%s",
            len(snapshots),
            current.version,
            current.snapshot_name,
        )

        for snapshot_index, snapshot in enumerate(snapshots[:MAX_SNAPSHOTS]):
            if len(exported) >= TARGET_COUNT:
                break

            total, roster, columns = fetch_roster(client, snapshot)
            all_search_columns.update(columns)
            snapshots_used.append(snapshot.version)
            if snapshot_index == 0:
                current_total = total
            LOG.info(
                "snapshot %s: filtered total=%d, featured rows=%d, columns=%s",
                snapshot.version,
                total,
                len(roster),
                ",".join(columns),
            )

            for row in roster:
                if len(exported) >= TARGET_COUNT:
                    break
                account = row["account"]
                character = row["name"]
                char_key = (account, character)
                if char_key in seen_characters:
                    continue
                seen_characters.add(char_key)

                try:
                    data = fetch_character(client, snapshot, account, character)
                    code = str(data.get("pathOfBuildingExport") or "").strip()
                    if not code:
                        raise ValueError("missing pathOfBuildingExport")
                    decode_pob_xml(code)
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)

                    skills_seen = collect_skill_names(data)
                    keystones_seen = collect_keystone_names(data)
                    payload_dps = character_dps(data)
                    dps = payload_dps or float(row.get("search_dps") or 0.0)
                    exported.append(
                        ExportedBuild(
                            dps=dps,
                            account=account,
                            character=character,
                            code=code,
                            snapshot_version=snapshot.version,
                            snapshot_name=snapshot.snapshot_name,
                            current_snapshot=(snapshot_index == 0),
                            search_rank=int(row.get("search_rank") or 0),
                            skills_seen=skills_seen,
                            keystones_seen=keystones_seen,
                        )
                    )
                    if len(exported) % 10 == 0:
                        LOG.info(
                            "validated %d/%d PoB exports",
                            len(exported),
                            TARGET_COUNT,
                        )
                except Exception as exc:  # noqa: BLE001
                    LOG.warning(
                        "failed %s/%s on %s: %s",
                        account,
                        character,
                        snapshot.version,
                        exc,
                    )
                    failures.append(
                        {
                            "account": account,
                            "character": character,
                            "snapshot": snapshot.version,
                            "error": str(exc),
                        }
                    )

        exported.sort(
            key=lambda item: (
                item.dps,
                item.current_snapshot,
                -item.search_rank,
                item.account,
                item.character,
            ),
            reverse=True,
        )
        write_outputs(
            exported,
            current_snapshot=current,
            current_total=current_total,
            snapshots_used=snapshots_used,
            search_columns=sorted(all_search_columns),
            failures=failures,
        )

        LOG.info(
            "done: %d validated unique codes; %d failures; output=%s",
            len(exported),
            len(failures),
            ANNOTATED_PATH,
        )
        if len(exported) < TARGET_COUNT:
            LOG.error("only %d valid codes, target is %d", len(exported), TARGET_COUNT)
            return 2
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
