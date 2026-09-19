# Remote ComfyUI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Windows-hosted Gateway, localhost browser administration UI, and Expo React Native Android client for two fixed ComfyUI workflows.

**Architecture:** A FastAPI service exposes the authenticated LAN API on port 3000 and a separate loopback-only admin application on port 3001. The service persists jobs and assets in SQLite, talks only to ComfyUI at `127.0.0.1:8188`, and serves a compiled React administration UI. An Expo TypeScript app consumes only the LAN API and never receives filesystem paths or workflow JSON.

**Tech Stack:** Python 3.11, FastAPI, Pydantic Settings, SQLAlchemy 2, httpx, pytest; React 19, Vite, TypeScript, Vitest; Expo React Native, Expo Router, TanStack Query, Zustand, Jest/React Native Testing Library.

---

## File Map

```text
server/
  pyproject.toml
  app/
    main.py                 # Creates public and admin FastAPI applications
    settings.py             # Environment/YAML-backed validated settings
    schemas.py              # Shared HTTP request/response models
    security.py             # Device bearer tokens and local admin CSRF session
    db.py                   # SQLite engine, sessions, schema initialization
    comfy/client.py         # Typed ComfyUI HTTP/WebSocket adapter
    comfy/workflows.py      # Fixed image/video prompt builders
    jobs/service.py         # Job lifecycle, submission, reconciliation
    libraries/service.py    # Root validation, scanning, pagination, thumbnails
    api/public.py           # Mobile-facing routes
    api/admin.py            # Loopback-only administration routes
  tests/
apps/
  windows-admin/            # Vite React localhost administration UI
  mobile/                   # Expo Router Android/iOS client
scripts/
  start-server.ps1
  start-admin.ps1
```

## Task 1: Repository and Gateway Foundation

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/app/__init__.py`
- Create: `server/app/settings.py`
- Create: `server/app/schemas.py`
- Create: `server/app/main.py`
- Create: `server/tests/test_health.py`
- Create: `server/tests/test_settings.py`
- Create: `server/config.example.yaml`

- [ ] Write tests asserting default ComfyUI URL is `http://127.0.0.1:8188`, public/admin ports are 3000/3001, invalid non-loopback ComfyUI URLs are rejected, and `/api/v1/health` returns a stable degraded response when ComfyUI is unavailable.
- [ ] Run `python -m pytest server/tests/test_settings.py server/tests/test_health.py -v` and verify collection/import fails because the application does not exist.
- [ ] Implement minimal Pydantic settings, health schemas, an injected ComfyUI health probe, and public/admin FastAPI application factories.
- [ ] Run the focused tests and then `python -m pytest server/tests -v`; require zero failures.
- [ ] Add `config.example.yaml` with loopback ComfyUI, LAN/public port, admin loopback/port, data directory, upload limits, and an empty library list.
- [ ] Commit as `feat(server): establish gateway foundation`.

## Task 2: Library Configuration and Windows Admin API

**Files:**
- Create: `server/app/libraries/models.py`
- Create: `server/app/libraries/service.py`
- Create: `server/app/api/admin.py`
- Create: `server/tests/test_library_service.py`
- Create: `server/tests/test_admin_api.py`
- Modify: `server/app/main.py`
- Modify: `server/app/settings.py`

- [ ] Write tests for fixed-drive filtering, direct-child directory listing, rejection of relative/device/traversal paths, duplicate and parent/child root detection, atomic config updates, library CRUD, and removal that never deletes source images.
- [ ] Run the focused tests and verify they fail because library/admin modules are missing.
- [ ] Implement `LibraryService` with injected filesystem/drive providers so security rules are tested without depending on the developer machine.
- [ ] Implement loopback middleware, Host/Origin validation, strict admin session cookie and CSRF checks for mutation routes.
- [ ] Implement `/admin/api/filesystem/*` and `/admin/api/libraries*` routes and mount them only in the admin app factory.
- [ ] Run `python -m pytest server/tests -v`; require zero failures.
- [ ] Commit as `feat(server): add secure library administration`.

## Task 3: Browser Administration UI

**Files:**
- Create: `apps/windows-admin/package.json`
- Create: `apps/windows-admin/vite.config.ts`
- Create: `apps/windows-admin/src/api.ts`
- Create: `apps/windows-admin/src/App.tsx`
- Create: `apps/windows-admin/src/pages/OverviewPage.tsx`
- Create: `apps/windows-admin/src/pages/LibrariesPage.tsx`
- Create: `apps/windows-admin/src/components/DirectoryPicker.tsx`
- Create: `apps/windows-admin/src/styles.css`
- Create: `apps/windows-admin/src/**/*.test.tsx`
- Modify: `server/app/main.py`

- [ ] Write component tests for loading/error states, directory traversal, add/edit/disable/delete flows, scan progress display, and the explicit statement that removing a library does not delete originals.
- [ ] Run `npm test -- --run` in `apps/windows-admin` and verify tests fail because components are absent.
- [ ] Implement a restrained Windows management interface with Overview and Image Directories views, lucide icons, accessible dialogs, stable responsive tables, and no nested cards.
- [ ] Build static assets and configure the admin FastAPI app to serve the SPA with history fallback at `/admin`.
- [ ] Run unit tests and `npm run build`; require zero errors.
- [ ] Commit as `feat(admin): add local browser management UI`.

## Task 4: Fixed Workflow Builders and ComfyUI Client

**Files:**
- Create: `server/app/comfy/client.py`
- Create: `server/app/comfy/workflows.py`
- Create: `server/app/comfy/templates/image_qwen_1.json`
- Create: `server/app/comfy/templates/image_qwen_2.json`
- Create: `server/app/comfy/templates/image_qwen_3.json`
- Create: `server/app/comfy/templates/video_minimax_h3.json`
- Create: `server/tests/test_comfy_client.py`
- Create: `server/tests/test_workflows.py`

- [ ] Export or construct API-format templates containing only the required fixed nodes and confirm them against local `/object_info`.
- [ ] Write tests asserting Qwen accepts 1–3 references, MiniMax accepts 1–9, clients cannot override model/node/output path, generated LoadImage links preserve order, dimensions are multiples of 32, and video frames match `17n+5` in the allowed 124–362 range.
- [ ] Run focused tests and verify expected missing-module failures.
- [ ] Implement immutable template loading, deep-copy prompt builders, explicit field injection, upload, prompt, history, queue and view methods in the ComfyUI client.
- [ ] Validate each generated prompt through local ComfyUI `POST /prompt` using low-cost test inputs where practical; cancel or wait for submitted smoke jobs and record prompt IDs.
- [ ] Run all server tests; require zero failures.
- [ ] Commit as `feat(server): add fixed ComfyUI workflows`.

## Task 5: Persistent Jobs, Pairing, Public API, and Artifacts

**Files:**
- Create: `server/app/db.py`
- Create: `server/app/security.py`
- Create: `server/app/jobs/models.py`
- Create: `server/app/jobs/service.py`
- Create: `server/app/api/public.py`
- Create: `server/tests/test_security.py`
- Create: `server/tests/test_jobs.py`
- Create: `server/tests/test_public_api.py`
- Modify: `server/app/main.py`

- [ ] Write tests for one-time pairing expiry, hashed device tokens, unauthorized requests, image/video request validation, single controlled execution queue, persisted `prompt_id`, restart reconciliation, artifact Range responses, and path hiding.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement SQLite models and schema initialization, pairing/token service, upload validation, job state machine, ComfyUI submission/reconciliation, artifact mapping and the public routes from `方案.md`.
- [ ] Implement WebSocket/SSE task events with polling fallback; reconnecting clients must recover from persisted state.
- [ ] Run all server tests; require zero failures.
- [ ] Commit as `feat(server): add persistent generation API`.

## Task 6: Expo React Native Client

**Files:**
- Create: `apps/mobile/package.json`
- Create: `apps/mobile/app.json`
- Create: `apps/mobile/app/_layout.tsx`
- Create: `apps/mobile/app/index.tsx`
- Create: `apps/mobile/app/generate.tsx`
- Create: `apps/mobile/app/jobs.tsx`
- Create: `apps/mobile/app/artifacts.tsx`
- Create: `apps/mobile/app/library.tsx`
- Create: `apps/mobile/app/settings.tsx`
- Create: `apps/mobile/src/api/client.ts`
- Create: `apps/mobile/src/state/draft.ts`
- Create: `apps/mobile/src/components/ReferenceImageStrip.tsx`
- Create: `apps/mobile/src/components/VideoSettings.tsx`
- Create: `apps/mobile/src/**/*.test.tsx`

- [ ] Write tests for pairing persistence, image/video segmented mode, reference limits and reorder behavior, `<Picture N>` renumbering, allowed video presets/frames, submit/retry states, paged library selection and artifact save/share actions.
- [ ] Run the mobile test command and verify failures because screens/components are absent.
- [ ] Implement the Expo TypeScript app with a quiet operational UI, safe-area handling, stable touch targets, Android cleartext LAN configuration, media permissions, and reconnecting task queries.
- [ ] Run unit tests, TypeScript checks and Expo export; require zero errors.
- [ ] Start Metro on an available port and install/open the debug app through the located Android SDK `adb.exe`.
- [ ] Commit as `feat(mobile): add remote ComfyUI client`.

## Task 7: Windows Startup and End-to-End Verification

**Files:**
- Create: `scripts/start-server.ps1`
- Create: `scripts/start-admin.ps1`
- Create: `scripts/install-autostart.ps1`
- Create: `README.md`
- Modify: `server/config.example.yaml`

- [ ] Write PowerShell/Python smoke tests for path resolution independent of current directory and port selection failures.
- [ ] Implement scripts using explicit project-relative paths, hidden background startup where appropriate, and no automatic ComfyUI exposure.
- [ ] Document setup, library administration, pairing, emulator networking (`adb reverse tcp:3000 tcp:3000`), LAN device usage and private-network firewall rules.
- [ ] Start both FastAPI listeners, admin UI and Metro; exercise health, pairing, library browse, one image request and one low-cost video request when model runtime permits.
- [ ] Use ADB screenshots and interaction checks to verify no overlap, clipped text, blank screens or broken navigation at the emulator viewport.
- [ ] Run full Python, admin and mobile test/build commands and record exact results in `progress.md`.
- [ ] Commit as `docs: add Windows operation and verification`.

## Final Review

- [ ] Dispatch a specification reviewer against `方案.md` and this implementation plan; fix every missing or extra behavior.
- [ ] Dispatch a code-quality reviewer across the full branch; fix every critical and important issue.
- [ ] Run fresh full verification and report the exact test/build/device evidence.
