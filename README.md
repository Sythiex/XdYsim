# XdYsim

XdYsim is a local desktop probability and combat simulator for a WIP TTRPG.

## Requirements

- [`uv`](https://docs.astral.sh/uv/)
- Python `3.13+` (can be installed with `uv`)

## Setup

Install Python `3.13` if you do not have it already:

```bash
uv python install 3.13
```

Install runtime and development dependencies:

```bash
uv sync --dev
```

If you only want runtime dependencies:

```bash
uv sync
```

## Run The App

Preferred:

```bash
uv run xdysim
```

Module entrypoint:

```bash
uv run python -m xdysim
```

Repository-root compatibility entrypoint:

```bash
uv run python main.py
```

## Presets

The `Combat Simulator` tab has `Presets` that can be saved as JSON or shared as strings.

## Project Layout

- `src/xdysim/engine`
  - Analytical math, combat simulation, preset codecs, and shared domain models.
- `src/xdysim/gui`
  - Qt Widgets UI for the app tabs and main window.
- `tests`
  - Regression, UI, and simulation tests.
- `scripts`
  - Developer utilities such as spreadsheet extraction.

## Tests And Lint

Run the full test suite:

```bash
uv run python -m pytest -q
```

Run Ruff:

```bash
uv run ruff check .
```
