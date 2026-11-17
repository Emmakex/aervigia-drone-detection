"""Fictional, deterministic scenario presets for local AERVIGIA demonstrations.

Coordinate values are an abstract 0..100 drawing plane, NOT real sensor feeds,
flight plans, geolocations or operational surveillance instructions.
"""

from math import sin, cos


SCENARIOS = {
    "standard": {
        "id": "standard",
        "name": "Recorrido estándar",
        "description": "Dos pistas sintéticas; una cruza la zona de prueba.",
        "expected": "Entrada eventual de una pista",
        "simulation": True,
    },
    "clear": {
        "id": "clear",
        "name": "Sin entradas",
        "description": "Dos pistas ficticias que permanecen fuera de la zona.",
        "expected": "Sin alertas de entrada",
        "simulation": True,
    },
    "dual-entry": {
        "id": "dual-entry",
        "name": "Entradas múltiples",
        "description": "Tres pistas ficticias; dos cruzan la zona de prueba.",
        "expected": "Dos alertas de entrada independientes",
        "simulation": True,
    },
}
DEFAULT_SCENARIO = "standard"


def catalog() -> list[dict]:
    return [dict(scenario) for scenario in SCENARIOS.values()]


def scenario_paths(scenario_id: str, step: int) -> list[tuple[str, float, float, str]]:
    """Return (source ID, x, y, classification) on a synthetic 0..100 plane."""
    if scenario_id not in SCENARIOS:
        raise ValueError("Unknown simulation scenario")
    # Phase wraps around a repeated toy path, not an actual surveillance track.
    phase = step % 28
    if scenario_id == "standard":
        return [
            ("alpha", 8 + phase * 3.2, 52 + sin(phase / 3) * 4, "quadcopter"),
            ("bravo", 87 - phase * 1.6, 19 + sin(phase / 4) * 5, "unknown"),
        ]
    if scenario_id == "clear":
        return [
            ("alpha", 15 + sin(phase / 3) * 8, 20 + cos(phase / 4) * 6, "unknown"),
            ("bravo", 82 + sin(phase / 5) * 7, 84 + cos(phase / 4) * 7, "quadcopter"),
        ]
    return [
        ("alpha", min(95, 24 + phase * 4.0), 51 + sin(phase / 5) * 3, "quadcopter"),
        ("bravo", max(5, 77 - phase * 5.0), 54 + cos(phase / 5) * 3, "unknown"),
        ("charlie", 20 + sin(phase / 4) * 7, 85 + cos(phase / 6) * 5, "fixed-wing"),
    ]
