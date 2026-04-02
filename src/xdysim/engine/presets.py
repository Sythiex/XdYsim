"""Serialization helpers for combat simulator presets and share strings."""

from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from xdysim.engine.combat import CombatTeam, DuelSimulationConfig

PRESET_SCHEMA_VERSION = 1
SHARE_STRING_VERSION = 1
SHARE_STRING_PREFIX = f"xdysim-preset-v{SHARE_STRING_VERSION}:"
SUPPORTED_SCHEMA_VERSIONS = frozenset({PRESET_SCHEMA_VERSION})
SUPPORTED_SHARE_STRING_VERSIONS = frozenset({SHARE_STRING_VERSION})
INVALID_FILE_NAME_PATTERN = re.compile(r'[<>:"/\\\\|?*]+')


class PresetCodecError(ValueError):
    """Raised when preset content cannot be serialized or deserialized safely."""


class CombatantReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    team_number: Literal[1, 2]
    combatant_index: int = Field(ge=0)


class CombatSimulatorPreset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[PRESET_SCHEMA_VERSION] = PRESET_SCHEMA_VERSION
    team_one: CombatTeam
    team_two: CombatTeam
    simulation: DuelSimulationConfig
    reference_attacker: CombatantReference
    reference_defender: CombatantReference

    @model_validator(mode="after")
    def validate_reference_targets(self) -> CombatSimulatorPreset:
        if not 100 <= self.simulation.trials <= 100_000:
            msg = "simulation.trials must be between 100 and 100000"
            raise ValueError(msg)
        if not 1 <= self.simulation.max_rounds <= 1_000:
            msg = "simulation.max_rounds must be between 1 and 1000"
            raise ValueError(msg)
        if self.simulation.seed is not None and self.simulation.seed < 0:
            msg = "simulation.seed must be null or a non-negative integer"
            raise ValueError(msg)
        self._validate_reference(self.reference_attacker, "reference_attacker")
        self._validate_reference(self.reference_defender, "reference_defender")
        return self

    def _validate_reference(self, reference: CombatantReference, field_name: str) -> None:
        team = self.team_one if reference.team_number == 1 else self.team_two
        if reference.combatant_index >= len(team.combatants):
            msg = (
                f"{field_name} points to combatant index {reference.combatant_index}, "
                f"but Team {reference.team_number} only has {len(team.combatants)} combatants"
            )
            raise ValueError(msg)


def _application_base_directory() -> Path:
    """Return the directory used as the base for app-managed artifacts."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    candidate_directories = [Path.cwd(), *Path(__file__).resolve().parents]
    for candidate in candidate_directories:
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "xdysim").is_dir()
        ):
            return candidate

    if sys.argv and sys.argv[0]:
        launch_target = Path(sys.argv[0])
        if not launch_target.is_absolute():
            launch_target = (Path.cwd() / launch_target).resolve()
        return launch_target.parent if launch_target.suffix else launch_target

    return Path.cwd()


def default_app_preset_directory() -> Path:
    """Return the app-managed preset directory next to the launch target."""
    return _application_base_directory() / "presets"


def app_preset_file_name(preset_name: str) -> str:
    """Return a safe JSON file name for an app-managed preset."""
    cleaned_name = INVALID_FILE_NAME_PATTERN.sub("_", preset_name.strip()).strip(" .")
    if not cleaned_name:
        raise PresetCodecError("Preset name cannot be blank.")
    return cleaned_name if cleaned_name.lower().endswith(".json") else f"{cleaned_name}.json"


def serialize_combat_simulator_preset_json(preset: CombatSimulatorPreset) -> str:
    """Serialize a preset to normalized human-readable JSON."""
    return json.dumps(preset.model_dump(mode="json"), indent=2)


def deserialize_combat_simulator_preset_json(json_text: str) -> CombatSimulatorPreset:
    """Parse and validate a preset from JSON text."""
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        msg = f"Invalid preset JSON: {exc.msg}."
        raise PresetCodecError(msg) from exc
    return _validate_combat_simulator_preset_payload(payload)


def save_combat_simulator_preset_file(
    preset: CombatSimulatorPreset,
    destination: str | Path,
) -> Path:
    """Write a preset to disk using the shared JSON serializer."""
    path = Path(destination)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize_combat_simulator_preset_json(preset) + "\n", encoding="utf-8")
    except OSError as exc:
        msg = f"Could not write preset file '{path.name}': {exc.strerror or exc}."
        raise PresetCodecError(msg) from exc
    return path


def load_combat_simulator_preset_file(source: str | Path) -> CombatSimulatorPreset:
    """Load and validate a preset from a JSON file."""
    path = Path(source)
    try:
        json_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Could not read preset file '{path.name}': {exc.strerror or exc}."
        raise PresetCodecError(msg) from exc
    return deserialize_combat_simulator_preset_json(json_text)


def encode_combat_simulator_preset_share_string(preset: CombatSimulatorPreset) -> str:
    """Encode a preset into a compressed URL-safe share string."""
    json_text = json.dumps(
        preset.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    )
    compressed = zlib.compress(json_text.encode("utf-8"), level=9)
    encoded = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"{SHARE_STRING_PREFIX}{encoded}"


def decode_combat_simulator_preset_share_string(share_string: str) -> CombatSimulatorPreset:
    """Decode a versioned share string into a validated preset model."""
    normalized = share_string.strip()
    if not normalized:
        raise PresetCodecError("Preset string is empty.")

    prefix, separator, payload = normalized.partition(":")
    if separator != ":" or not prefix.startswith("xdysim-preset-v"):
        raise PresetCodecError("Preset string has an invalid format.")

    try:
        version = int(prefix.removeprefix("xdysim-preset-v"))
    except ValueError as exc:
        raise PresetCodecError("Preset string has an invalid format version.") from exc

    if version not in SUPPORTED_SHARE_STRING_VERSIONS:
        msg = f"Unsupported preset string format version: {version}."
        raise PresetCodecError(msg)
    if not payload:
        raise PresetCodecError("Preset string is truncated or missing data.")

    try:
        padded_payload = payload + ("=" * (-len(payload) % 4))
        compressed = base64.urlsafe_b64decode(padded_payload.encode("ascii"))
    except (ValueError, binascii.Error) as exc:
        raise PresetCodecError("Preset string is invalid or truncated.") from exc

    try:
        json_bytes = zlib.decompress(compressed)
        json_text = json_bytes.decode("utf-8")
    except (zlib.error, UnicodeDecodeError) as exc:
        raise PresetCodecError("Preset string is invalid or truncated.") from exc

    return deserialize_combat_simulator_preset_json(json_text)


def _validate_combat_simulator_preset_payload(payload: Any) -> CombatSimulatorPreset:
    if not isinstance(payload, dict):
        raise PresetCodecError("Preset JSON must contain an object at the top level.")

    schema_version = payload.get("schema_version")
    if schema_version is None:
        raise PresetCodecError("Preset JSON is missing required field 'schema_version'.")
    if not isinstance(schema_version, int):
        raise PresetCodecError("Preset field 'schema_version' must be an integer.")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        msg = f"Unsupported preset schema version: {schema_version}."
        raise PresetCodecError(msg)

    try:
        return CombatSimulatorPreset.model_validate(payload)
    except ValidationError as exc:
        error_messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise PresetCodecError(f"Preset JSON is invalid: {error_messages}.") from exc
