# Changelog

## [0.2.0] - 2026-06-30

### Added

- Added a `Circumstance` modifier to the Static Checks tab.
- Added Attacker and Defender `Circumstance` modifiers to the Opposed Rolls tab.

### Changed

- Replaced the Opposed Rolls tie probability row with `Attacker <= Defender`.

## [0.1.1] - 2026-06-30

### Added

- Added `probability_lte` to `StaticCheckSummary`.

### Changed

- Replaced the static checks tab metric `Result >= DC` with `Result <= DC`.
- Updated static checks tab labels for clearer probability display.

### Fixed

- Fixed `QApplication` instance validation in GUI test fixtures.
