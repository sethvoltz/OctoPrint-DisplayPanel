# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.1] - 2021-04-11
### Changed
- Update micro panel tab to render the scaled up image with nearest neighbor (crisp pixels)

## [3.0.0] - 2021-04-11
### Refactor
- Modularize panel interface and add a "virtual panel" in the web UI (kgutwin)
- Modularize display screens for future expansion (kgutwin)

## [2.1.1] - 2021-03-04
### Fixes
- Fix off-by-one issue with bi-color section on display

## [2.1.0] - 2021-02-28
### Changed
- Add missing dependency for RPi.GPIO (unclej84)
- Trap and log errors in retrieving system stats to avoid getting stuck in "Gathering System Stats" (kgutwin)
- Play button now can be used to connect to a disconnected printer and start a queued job (kgutwin)

## [2.0.1] - 2021-02-07
### Changed
- Apply changed plugin name to settings panel (unclej84)
- Trim down printer screen to fit all text (unclej84)

## [2.0.0] - 2021-01-29
### Changed
- Changed plugin name from Display Panel to Micro Panel

## [1.4.0] - 2021-01-29
### Added
- Z-height display while printing if the DisplayLayerProgress plugin is installed
- Pull Request template

### Changed
- Trim down system screen to fit all text

## [1.3.0] - 2021-01-28
### Added
- Support for bi-color (or two-color) OLED displays, keeping the progress from crossing the section (unclej84)
- Started tracking changes with a Changelog (right here!)
- Contributor thanks in the README

### Changed
- Improved language across the board to be more clear about the settings (Andy-ABTec)

## [1.2.0] - 2021-01-16
### Added
- Enable display timeout with setting (unclej84)
- Add a new method of calculating remaining time to drive the progress bar (unclej84)

### Changed
- Updated language on some of the controls to be more clear with new options

## [1.1.0] - 2021-01-16
### Added
- Configuration panel UI within OctoPrint (unclej84)
- Allow configuration of GPIO pins for buttons (unclej84)
- Allow 180º rotation of the screen for more hardware installation freedom (unclej84)

## 1.1.0
### Added
- Initial release to community, official plugin on the OctoPrint plugin repository.

[Unreleased]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v3.0.1...HEAD
[3.0.1]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v2.1.1...v3.0.0
[2.1.1]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v1.4.0...v2.0.0
[1.4.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/sethvoltz/OctoPrint-DisplayPanel/releases/tag/v1.1.0
