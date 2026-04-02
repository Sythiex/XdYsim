## Repo Guidelines

- Keep the analytical engine importable and testable without any GUI imports.
- Put GUI code under `src/xdysim/gui` and engine/domain code under `src/xdysim/engine`.
- Write or update tests with every engine change, especially for probability math.
- Preserve deterministic behavior where possible and surface randomness via explicit seeds.
- Prefer small, focused changes that do not mix UI refactors with engine behavior changes.
- Treat the spreadsheet-derived reference data in `tests/data` as a regression oracle for analytical outputs.
