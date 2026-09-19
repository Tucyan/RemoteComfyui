# Mobile Output and Video Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Android client preview and delete generated files, retain separate image/video prompts, show running time, and choose video dimensions and frames with greater freedom.

**Architecture:** Extend the existing authenticated artifact API with an ID-scoped DELETE that verifies the physical path. Keep video dimension calculations and frame validation in the mobile domain layer, passing explicit width/height/frames to the existing server workflow validator. Render media in an authenticated in-app viewer and retain the current library-image import route.

**Tech Stack:** FastAPI, SQLite, Expo React Native, TypeScript, Vitest, pytest.

---

### Task 1: Physical artifact deletion

**Files:** `server/app/jobs/service.py`, `server/app/api/public.py`, `server/tests/test_jobs.py`, `server/tests/test_public_api.py`

- [x] Add a failing service test: deleting an artifact removes both its file and database row; a tampered outside path is refused.
- [x] Run `python -m pytest server/tests/test_jobs.py -q` and observe the expected missing-method failure.
- [x] Add a failing API test: authenticated DELETE returns 204; missing ID returns 404; unauthenticated DELETE returns 401.
- [x] Implement `JobService.delete_artifact` and the DELETE route; rerun those test files.

### Task 2: Video settings domain and UI

**Files:** `apps/mobile/src/domain/draft.ts`, `apps/mobile/src/components/VideoSettings.tsx`, `apps/mobile/tests/draft.test.ts`, `apps/mobile/App.tsx`, `apps/mobile/src/api/client.ts`

- [x] Write failing domain tests for seven aspect ratios, 0.2–1.5 MP area selection, 32-aligned dimensions, custom dimensions, and `17n+5` frame increment/decrement.
- [x] Run `npm test -- --run` from `apps/mobile` and observe the expected failures.
- [x] Implement dimension and frame helpers; send explicit width/height/frames through `RemoteApi.createVideoJob`.
- [x] Build the aspect picker with rectangle previews, clear-quality slider, optional custom width/height inputs, and numeric frame input with plus/minus buttons.
- [x] Re-run mobile tests and TypeScript check.

### Task 3: Media and task experience

**Files:** `apps/mobile/App.tsx`, `apps/mobile/src/api/client.ts`, `apps/mobile/tests/api.test.ts`, `apps/mobile/package.json`

- [x] Write failing API test for artifact DELETE and explicit video dimensions.
- [x] Implement separate image/video prompt state and elapsed time formatted as seconds or minutes/seconds.
- [x] Add authenticated in-app image zoom and video player; retain save/share actions.
- [x] Add an explicit destructive confirmation before DELETE and refresh the artifact list.
- [x] Verify the existing library-image import and add a regression test if its API path lacks coverage.

### Task 4: Acceptance

**Files:** `README.md`, `task_plan.md`, `progress.md`

- [x] Run full backend and mobile suites, mobile typecheck/export, and `git diff --check`.
- [~] Rebuild a standalone release APK and install it on the emulator; inspect the generated screen. APK built, but ADB has no online emulator.
- [x] Document any unverified GPU workflow behavior or preview limitations.
