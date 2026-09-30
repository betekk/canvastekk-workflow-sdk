# Changelog

All notable changes to this project will be documented in this file.

## [0.36.0] - 2026-09-30

### Features

- **sdk**: Session-only uploads — remove legacy presigned PUT target (DA-3340) (#89) (**BREAKING**)


## [0.35.2] - 2026-09-30

### Bug Fixes

- **sdk**: Drop unsigned Content-MD5 from multipart part PUTs (DA-3341)


### Miscellaneous Tasks

- **release**: Prepare v0.35.2


## [0.35.1] - 2026-09-29

### Bug Fixes

- **ts-sdk**: DA-3314 red-CI fix — unused helper + dead resume code (#87)


### Miscellaneous Tasks

- **release**: Prepare v0.35.1


## [0.35.0] - 2026-09-29

### Features

- **ts-sdk**: Multipart upload-session support (DA-2886 parity, DA-3314) (#86)


### Miscellaneous Tasks

- **release**: Prepare v0.35.0


## [0.34.0] - 2026-09-29

### Features

- **auth**: Accept CANVASTEKK_API_KEY_NEXT alongside the current key (rotation window) (#85)


### Miscellaneous Tasks

- **release**: Prepare v0.34.0


## [0.33.0] - 2026-09-28

### Features

- **sdk-py**: BaseNode.report_progress via ambient contextvars (DA-3230) (#84)


### Miscellaneous Tasks

- **release**: Prepare v0.33.0


## [0.32.0] - 2026-09-28

### Features

- **sdk-ts**: BaseNode.reportProgress mid-run progress pings (DA-3232) (#83)


### Miscellaneous Tasks

- **release**: Prepare v0.32.0


## [0.31.3] - 2026-09-28

### Miscellaneous Tasks

- **docs**: Remove AGENTS.md
- **release**: Prepare v0.31.3


## [0.31.2] - 2026-09-28

### Miscellaneous Tasks

- Convert workflow-sdk CI + release to local-if-idle pool via canonical pick-runner (DA-3160) (#82)
- **release**: Prepare v0.31.2


## [0.31.1] - 2026-09-26

### Miscellaneous Tasks

- Remove accidentally committed .venv-gates; gitignore .venv*/ (DA-3086) (#81)
- **release**: Prepare v0.31.1


## [0.31.0] - 2026-09-26

### Features

- **cli**: Registry-convergence subcommand (DA-3086) (#80)


### Miscellaneous Tasks

- **release**: Prepare v0.31.0


## [0.30.3] - 2026-09-26

### Miscellaneous Tasks

- Standardize poetry — >=2.2 floor + python -m poetry module invocation (DA-3036) (#79)
- **release**: Prepare v0.30.3


## [0.30.2] - 2026-09-25

### Documentation

- **typescript**: WASM worker pattern for heavy nodes (DA-3010) (#78)


### Miscellaneous Tasks

- **release**: Prepare v0.30.2


## [0.30.1] - 2026-09-25

### Miscellaneous Tasks

- **skills**: Add skill-mirror drift guard; canonical example cleanup (DA-3026) (#77)
- **release**: Prepare v0.30.1


## [0.30.0] - 2026-09-25

### Features

- **python**: Return freed heap to OS at end of node invocation (DA-3009) (#76)


### Miscellaneous Tasks

- **release**: Prepare v0.30.0


## [0.29.4] - 2026-09-25

### Documentation

- **skills**: Document UploadSession upload-target lane in node skills (DA-3005) (#75)


### Miscellaneous Tasks

- **release**: Prepare v0.29.4


## [0.29.3] - 2026-09-25

### Testing

- **cli**: Pin sdk init scaffold destination to .agents/skills (DA-3004) (#74)


### Miscellaneous Tasks

- **release**: Prepare v0.29.3


## [0.29.2] - 2026-09-25

### Miscellaneous Tasks

- **skills**: Resync repo mirrors from bundled canonical, fix 2 canonical errors (DA-3003) (#73)
- **release**: Prepare v0.29.2


## [0.29.1] - 2026-09-25

### Miscellaneous Tasks

- **skills**: Move .opencode/skills to .agents/skills for cross-harness discovery (DA-2982) (#72)
- **release**: Prepare v0.29.1


## [0.29.0] - 2026-09-23

### Features

- **uploads**: Multipart session uploader + legacy single-PUT deprecation [DA-2886] (#71)


### Miscellaneous Tasks

- **release**: Prepare v0.29.0


## [0.28.2] - 2026-09-18

### Miscellaneous Tasks

- **release**: Attach TypeScript tarball to GitHub Releases [DA-2677]
- **release**: Prepare v0.28.2


## [0.28.1] - 2026-09-18

### Bug Fixes

- **cli**: Register --manifest <file|URL> input, ts parity [DA-2604]


### Miscellaneous Tasks

- **release**: Prepare v0.28.1


## [0.28.0] - 2026-09-18

### Features

- **manifest**: Serve handler code_digest computed at startup [DA-2603]
- **cli**: Register subcommand + offline probe harness [DA-2603]
- **cli,manifest**: Ts code_digest + register/probe CLI parity [DA-2603]


### Refactoring

- **cli**: Delegate to build_registry_payload, probe value domain [DA-2603] (**BREAKING**)


### Documentation

- **plan**: Add PLAN-DA-2603.md for DA-2603
- **guide,readmes**: Code_digest, register CLI, probe harness [DA-2603]
- **plan**: Tick DA-2603 ACs with live-engine register evidence


### Style

- **tests**: Rename TestClient alias to satisfy ruff N814 [DA-2603]


### Testing

- **cli**: Scope manifestPath in appended ts describe [DA-2603]
- **cli**: Hoist manifest fixtures to module scope [DA-2603]


### Miscellaneous Tasks

- **release**: Prepare v0.28.0


## [0.27.0] - 2026-09-18

### Features

- **definition**: Manifest identity is slug, display is name [DA-2627] (#67) (**BREAKING**)


### Miscellaneous Tasks

- **release**: Prepare v0.27.0


## [0.26.4] - 2026-09-14

### Bug Fixes

- **config**: Replace V1 atlassian MCP stub with full v2 servers entry


### Miscellaneous Tasks

- **release**: Prepare v0.26.4


## [0.26.3] - 2026-09-03

### Documentation

- **plan**: Tick DA-2337 phases 4.2 and 5.1 (DA-2337) (#63)


### Miscellaneous Tasks

- **release**: Prepare v0.26.3


## [0.26.2] - 2026-09-03

### Testing

- **sdk**: Make deprecation tests timezone-independent (DA-2337) (#62)


### Miscellaneous Tasks

- **release**: Prepare v0.26.2


## [0.26.1] - 2026-09-03

### Bug Fixes

- **sdk**: Fail node when declared file output is not a local file (DA-2337) (#61)


### Miscellaneous Tasks

- **release**: Prepare v0.26.1


## [0.26.0] - 2026-09-03

### Features

- **deprecation**: Sunset validator + runtime lifecycle parity with Python v0.25.0 [DA-2312] (#60)


### Miscellaneous Tasks

- **release**: Prepare v0.26.0


## [0.25.0] - 2026-09-03

### Features

- **sdk**: Emit deprecation in registry payload + sunset lifecycle enforcement [DA-2305] (#59)


### Miscellaneous Tasks

- **release**: Prepare v0.25.0


## [0.24.0] - 2026-09-01

### Features

- **sdk**: Propagate X-Account-Id into node execution context (DA-2242) (#58)


### Miscellaneous Tasks

- **release**: Prepare v0.24.0


## [0.23.1] - 2026-08-24

### Bug Fixes

- **lint**: Commit eslint 9 flat config so npm run lint gates CI [DA-1968] (#57)


### Miscellaneous Tasks

- **release**: Prepare v0.23.1


## [0.23.0] - 2026-08-24

### Features

- Diff CLI compat fields typed errors and robustness [DA-1955]


### Miscellaneous Tasks

- **release**: Prepare v0.23.0


## [0.22.3] - 2026-08-22

### Testing

- **uploads**: Pin fixed-length identity PUT contract — DA-1900
- **uploads**: Drop inert DEV_MODE setenv; correct plan release narrative
- **uploads**: Pin fixed-length identity PUT contract — DA-1900 (#55)


### Miscellaneous Tasks

- **release**: Prepare v0.22.3


## [0.22.2] - 2026-08-19

### Bug Fixes

- **uploads**: Send fixed-length identity PUT for S3 presigned uploads [DA-1811]


### Miscellaneous Tasks

- **release**: Prepare v0.22.2


## [0.22.1] - 2026-08-19

### Bug Fixes

- **uploads**: Set duplex half for stream bodies in S3 output upload [DA-1811]
- **node**: Guard download write stream against late open errors [DA-1811]


### Miscellaneous Tasks

- **release**: Prepare v0.22.1


## [0.22.0] - 2026-08-15

### Features

- **runner**: Per-node output subdirs in local WorkflowRunner (DA-1711 2.3) (**BREAKING**)


### Bug Fixes

- **security**: Implement Phase 1 download hardening (DA-1711)
- **runner**: Merge START inputs and isolate resolver errors (DA-1711 2.1-2.2)
- **security**: Request validation, body limits, auth posture (DA-1711 Ph3)
- **uploads/executors**: Fail on upload failure, proto-pollution guards, executor hardening (DA-1711 Ph4)


### Documentation

- **plan**: Add PLAN-DA-1711 for security & robustness hardening
- **plan**: Amend PLAN-DA-1711 per plan-review findings PLAN-1..12
- **examples**: Fix echo double-download, sync docs for v0.22 security changes, add parity manifest (DA-1711 Ph5)
- Add missing docstrings across SDK modules


### Miscellaneous Tasks

- Remove completed plan files
- Add opencode repo config and AGENTS rule blocks
- **release**: Prepare v0.22.0


## [0.21.0] - 2026-08-02

### Features

- Add deprecation metadata field to WorkflowNodeManifest (DA-1582) (#51)


### Miscellaneous Tasks

- **release**: Prepare v0.21.0


## [0.20.0] - 2026-07-20

### Features

- **ci**: DA-1546 manifest schema stability check (#50)


### Documentation

- DA-1546 add dispatch contract to AGENTS.md (#49)


### Miscellaneous Tasks

- **release**: Prepare v0.20.0


## [0.19.0] - 2026-07-20

### Features

- **ci**: DA-1546 dispatch sdk-released to nodes repo on release (#48)


### Miscellaneous Tasks

- **release**: Prepare v0.19.0


## [0.18.2] - 2026-07-12

### Bug Fixes

- **ci**: Make PyPI publish non-blocking until org registry is enabled (#47)


### Miscellaneous Tasks

- **release**: Prepare v0.18.2


## [0.18.1] - 2026-07-12

### Bug Fixes

- **ci**: Switch to twine for GitHub Packages PyPI publish (poetry 404) (#46)


### Miscellaneous Tasks

- **release**: Prepare v0.18.1


## [0.18.0] - 2026-07-12

### Features

- **ci**: Publish Python SDK to GitHub Packages PyPI registry (#45)


### Miscellaneous Tasks

- **release**: Prepare v0.18.0


## [0.17.2] - 2026-07-12

### Bug Fixes

- **ci**: Scope TS package name for GitHub Packages + make publish non-blocking (#44)


### Miscellaneous Tasks

- **release**: Prepare v0.17.2


## [0.17.1] - 2026-07-12

### Bug Fixes

- **ci**: Make post-publish smoke tests non-blocking (continue-on-error) (#43)


### Miscellaneous Tasks

- **release**: Prepare v0.17.1


## [0.17.0] - 2026-07-12

### Features

- **ts**: DA-1461 TypeScript SDK parity fixes — wire-format, security, resolver, robustness (#40) (**BREAKING**)


### Bug Fixes

- **ci**: Fix release.yml indentation + add TypeScript CI + multi-version matrix + TS publish (#41)
- **ci**: Extract bump script to standalone file to fix indentation errors (#42)


### Miscellaneous Tasks

- **release**: Prepare v0.17.0


## [0.16.0] - 2026-06-14

### Features

- Remove backward-compat aliases and harden release pipeline [DA-1302] (#39) (**BREAKING**)


### Miscellaneous Tasks

- **release**: Prepare v0.16.0


## [0.15.0] - 2026-06-09

### Features

- SDK model renames with parent→child naming convention [DA-1230] (#38) (**BREAKING**)


### Miscellaneous Tasks

- **release**: Prepare v0.15.0


## [0.14.1] - 2026-05-29

### Documentation

- **DA-1162**: Add docstrings/JSDoc coverage + fix exception handling (#37)


### Miscellaneous Tasks

- **release**: Prepare v0.14.1


## [0.14.0] - 2026-05-28

### Features

- **typescript**: Add TypeScript SDK with full feature parity (DA-1148) (#36)


### Miscellaneous Tasks

- **release**: Prepare v0.14.0


## [0.13.0] - 2026-05-26

### Features

- **sdk**: Add WorkflowRunner output_dir support and LocalFileServer test utility (DA-1102) (#34)


### Miscellaneous Tasks

- **release**: Prepare v0.13.0


## [0.12.0] - 2026-05-25

### Features

- Add workflow builder and local runner (DA-1087) (#33)


### Miscellaneous Tasks

- **release**: Prepare v0.12.0


## [0.11.0] - 2026-05-22

### Features

- **sdk**: Align SDK docs with engine semver versioning [DA-1041] (#32)


### Miscellaneous Tasks

- **release**: Prepare v0.11.0


## [0.10.1] - 2026-05-22

### Documentation

- **sdk**: Document {{variable}} template substitution behavior for node authors [DA-1038] (#31)


### Miscellaneous Tasks

- **release**: Prepare v0.10.1


## [0.10.0] - 2026-05-22

### Features

- **docs**: Align SDK naming with engine WorkflowNode/WorkflowDefinitionNode model [DA-1028]


### Miscellaneous Tasks

- **release**: Prepare v0.10.0


## [0.9.1] - 2026-05-21

### Bug Fixes

- **registry**: Align register_node() payload with engine RegisterNodeRequest schema [DA-1016] (#29)


### Miscellaneous Tasks

- **release**: Prepare v0.9.1


## [0.9.0] - 2026-05-21

### Features

- Enforce node definition versioning and auto-derive id field (DA-1014) (#28) (**BREAKING**)


### Miscellaneous Tasks

- **release**: Prepare v0.9.0


## [0.8.0] - 2026-05-20

### Features

- **sdk**: Auto-download presigned URL file inputs before execute() [DA-996] (#26)


### Miscellaneous Tasks

- **release**: Prepare v0.8.0


## [0.7.2] - 2026-05-17

### Documentation

- Add EXTERNAL-AUTHOR-GUIDE.md for node registration [DA-943]


### Miscellaneous Tasks

- **release**: Prepare v0.7.2


## [0.7.1] - 2026-05-17

### Style

- Apply ruff formatter to existing codebase


### Miscellaneous Tasks

- **release**: Prepare v0.7.1


## [0.7.0] - 2026-05-17

### Features

- **registry**: Add service_token auth support to register_node() [DA-931]


### Miscellaneous Tasks

- **release**: Prepare v0.7.0


## [0.6.0] - 2026-05-16

### Features

- **DA-910**: Add opencode skill scaffolding CLI for AI agent node creation
- **DA-910**: Add opencode skill scaffolding CLI for AI agent node creation (#DA-910)


### Miscellaneous Tasks

- **release**: Prepare v0.6.0


## [0.5.2] - 2026-05-16

### Documentation

- **DA-898**: Separate deployment concerns from SDK documentation (#21)


### Miscellaneous Tasks

- **release**: Prepare v0.5.2


## [0.5.1] - 2026-05-16

### Bug Fixes

- Resolve ruff N812 and I001 lint errors in test files


### Miscellaneous Tasks

- **release**: Prepare v0.5.1


## [0.5.0] - 2026-05-16

### Features

- **sdk**: V0.5.0 — public-endpoint hardening with auth, timeout enforcement, and DX improvements (#14)
- Migrate format:binary to format:file, remove multipart, add CLI validate (**BREAKING**)
- Add industry-standard SDK enhancements, structured logging, env vars docs
- Migrate format:binary to format:file, add SDK enhancements (DA-894) (**BREAKING**)


### Bug Fixes

- Address code review findings — P0/P1/P2 fixes
- Use sys.executable instead of hardcoded .venv path in test_main.py (CI fix)
- Revert manual version bump to 0.4.9, let release workflow handle bump


### Documentation

- **plan**: Add PLAN-DA-894 for format:binary → format:file migration
- **plan**: Revise PLAN-DA-894 with architecture review findings
- **plan**: Add end-to-end file flow, release coordination, and reference docs
- **plan**: Simplify file flow to CDS-only — remove MODE A browser upload
- **plan**: Add file field validation helper and x-* extensions
- **plan**: Hard break — remove dual detection, promote httpx
- **plan**: Add manifest format enforcement via Pydantic validator
- **plan**: Add full workflow diagram and manifest enforcement diagram
- **plan**: Clarify HTTP client choice in publisher, add CLI validate utility
- **plan+readme+example**: Add utilities section, architecture decisions, echo node example
- Add logging section to Python README, expand root README features, update plan checkboxes


### Style

- Remove unused SDKVersionMiddleware import in test_middleware
- Fix ruff N812 and I001 in test files — use __version__ directly


### Miscellaneous Tasks

- Add workflow_dispatch and __init__.py bump to release workflow
- Regenerate poetry.lock (remove python-multipart, promote httpx to main)
- Configure git-cliff to not bump major on breaking for 0.x
- **release**: Prepare v0.5.0


## [0.4.9] - 2026-05-14

### Bug Fixes

- **release**: Upload Python SDK as release assets instead of GitHub Packages


### Miscellaneous Tasks

- **release**: Prepare v0.4.9


## [0.4.8] - 2026-05-14

### Bug Fixes

- **release**: Use twine for GitHub Packages publish


### Miscellaneous Tasks

- **release**: Prepare v0.4.8


## [0.4.7] - 2026-05-14

### Bug Fixes

- **release**: Use GH_PAT for GitHub Packages publish


### Miscellaneous Tasks

- **release**: Prepare v0.4.7


## [0.4.6] - 2026-05-14

### Bug Fixes

- **release**: Configure poetry publish repository URL for GitHub Packages


### Miscellaneous Tasks

- **release**: Prepare v0.4.6


## [0.4.5] - 2026-05-14

### Bug Fixes

- **release**: Unconditional version bump, detect only for publish gate
- **release**: Restore pull-requests read permission for git-cliff GitHub API
- **release**: Remove --no-update flag incompatible with Poetry 2.x


### Miscellaneous Tasks

- **release**: Prepare v0.4.5


## [0.4.4] - 2026-05-14

### Bug Fixes

- **release**: Export version variable for Python bump and sync poetry.lock


### Miscellaneous Tasks

- **release**: Prepare v0.4.4


## [0.4.3] - 2026-05-14

### Refactoring

- Combine release and publish into single workflow (#5)


### Miscellaneous Tasks

- **release**: Prepare v0.4.3


## [0.4.2] - 2026-05-14

### Bug Fixes

- Prevent release workflow from re-triggering on changelog commits (#4)


### Miscellaneous Tasks

- **release**: Prepare v0.4.2


## [0.4.1] - 2026-05-14

### Features

- Add git-cliff semantic versioning and automated release workflow (#2)


### Bug Fixes

- Unified monorepo versioning with per-language selective publish (#3)


### Refactoring

- Restructure as polyglot monorepo with GitHub Packages CI/CD (#1)


<!-- generated by git-cliff -->
