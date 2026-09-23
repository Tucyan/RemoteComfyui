# Qwen Image 2.1 Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Qwen Image 2.1 8GB Edit and Text-to-Image alongside the existing Qwen 2511 Edit and MiniMax video workflows, with per-workflow controls and resolution settings.

**Architecture:** Keep one image-job API and add a validated workflow identifier so the server selects a fixed, checked-in ComfyUI API prompt template. The mobile app will show a four-choice workflow picker and keep prompt, reference images, and settings scoped to each choice. Edit dimensions are derived from the first reference image and the selected scale or locked-ratio dimensions; text-to-image dimensions use the existing video-style ratio and megapixel controls.

**Tech Stack:** FastAPI, Pydantic, Pillow, SQLite JSON job payloads, ComfyUI API prompt JSON, Expo React Native, TypeScript, pytest, Vitest.

---

## Current State and Decisions

- Current branch: `feature/remote-comfyui-mvp`; working tree was clean when inspected.
- Existing image endpoint is `/api/v1/jobs/image`; it accepts 1–3 references and always builds the Qwen Edit 2511 workflow.
- Existing video workflow accepts explicit width, height, and frame count. Mobile video controls already include aspect ratios, a 0.2–1.5 MP slider, and custom dimensions.
- The two source canvas workflows are in `D:/AI/ComfyUI_windows_portable_nvidia/ComfyUI_windows_portable/ComfyUI/user/default/workflows/`:
  - `qwen_image_2_1_8gb_edit.json`: one to ten images; image 1 is the edit target; has `ResolutionSelector`, a custom-size switch, and 32-pixel dimension multiples.
  - `qwen_image_2_1_8gb_t2i.json`: no input image; has `ResolutionSelector` and 8-pixel dimension multiples.
- Source canvas JSON is not the ComfyUI API prompt format. Commit API-format templates into the repository; do not load arbitrary canvas JSON submitted by a mobile client.
- The required Qwen 2.1 model files and relevant node types were present on the local ComfyUI installation when inspected. The ComfyUI HTTP service was unavailable on a later schema query, so confirm prompt schemas and perform a low-resolution queue check during implementation.
- Preserve all four workflows under stable identifiers: `qwen_edit_2511`, `qwen_image_2_1_8gb_edit`, `qwen_image_2_1_8gb_t2i`, `minimax_h3`.
- UI decision: show four selectable workflow cards in a two-column grid at the top of the generate page. Each card names the model and whether it edits references, creates from text, or creates video. Display controls appropriate to the selected card below it.
- Keep prompts and reference selections independent per workflow. T2I hides reference controls and always submits an empty reference list. The first selected/reordered image is the edit target for both edit workflows.
- Qwen 2.1 Edit uses a multiplier slider from 0.5× to 2.0× in 0.1× increments, initially 1.0×. Width/height inputs share the source image aspect ratio and update each other as the user types. Show the aligned dimensions that will be submitted. Keep the initial range and step in a named domain constant so it can be adjusted after device testing.
- Align Edit width and height to multiples of 32 and T2I width and height to multiples of 8. Reject non-positive values and cap each side at 2048 for these 8GB workflows. For Edit, preserve the source aspect ratio within alignment rounding; report the submitted size in the UI.
- Determine reference dimensions from the uploaded image bytes on the server using EXIF-oriented dimensions. Add Pillow as a direct server dependency. Return dimensions with upload and library-import results so mobile can initialize edit controls before submit; re-check the stored file at job creation as the authoritative validation.

## File Map

| File | Responsibility |
| --- | --- |
| `server/app/comfy/templates/image_qwen_21_edit_8gb.json` | Fixed ComfyUI API prompt graph for Qwen 2.1 Edit, with reference slots and editable values isolated for the builder. |
| `server/app/comfy/templates/image_qwen_21_t2i_8gb.json` | Fixed ComfyUI API prompt graph for Qwen 2.1 T2I. |
| `server/app/comfy/workflows.py` | Workflow builders, per-workflow reference limits, and dimension validation. |
| `server/app/api/public.py` | Workflow-specific request validation, image metadata responses, and job payload construction. |
| `server/app/jobs/service.py` | Dispatch queued image jobs to the correct fixed builder. |
| `server/pyproject.toml` | Pillow dependency. |
| `server/tests/test_workflows.py` | API prompt graph and dimensions tests. |
| `server/tests/test_public_api.py` | Request/reference rules and metadata response tests. |
| `server/tests/test_jobs.py` | Queued workflow dispatch tests. |
| `apps/mobile/src/domain/draft.ts` | Four workflow IDs, limits, prompt/reference state helpers, and dimension calculations. |
| `apps/mobile/src/components/ImageSettings.tsx` | Qwen 2.1 Edit multiplier/locked-ratio controls and T2I ratio/quality/custom-size controls. |
| `apps/mobile/src/components/WorkflowPicker.tsx` | Four workflow cards and accessible selection state. |
| `apps/mobile/src/api/client.ts` | Typed workflow payloads and image metadata fields. |
| `apps/mobile/App.tsx` | Per-workflow drafts, conditional controls, reference caps, and submissions. |
| `apps/mobile/tests/draft.test.ts` | Workflow limits, switching state, edit aspect locking, and T2I dimensions tests. |
| `apps/mobile/tests/api.test.ts` | Image workflow and dimension payload tests. |
| `README.md` | User-facing capabilities and workflow requirements. |

## Implementation Tasks

### Task 1: Extract and test fixed Qwen 2.1 API prompt templates

**Files:** `server/app/comfy/templates/image_qwen_21_edit_8gb.json`, `server/app/comfy/templates/image_qwen_21_t2i_8gb.json`, `server/app/comfy/workflows.py`, `server/tests/test_workflows.py`

- [x] Query node schemas from the installed ComfyUI source because the upstream HTTP service was stopped; convert both canvas subgraphs into API prompt dictionaries with valid string node references.
- [x] Add fixed Qwen 2.1 Edit and T2I prompt templates with model names from the source workflows and without canvas notes, comparisons, or example prompts.
- [x] Add Edit and T2I builders with ordered Edit references, shared prompt/seed validation, per-workflow aligned dimensions, a deep-copied template, and fixed graph settings.
- [x] Set Edit's custom-size switch and target latent dimensions; set the encoder resolution from target pixel area and align it to 32.
- [x] Add tests for model names, outputs, prompt/seed validity, dimensions, reference order and limits, T2I's no-reference builder, deep-copy isolation, and unsafe reference paths.
- [x] Verify red-green behavior, run `python -m pytest server/tests/test_workflows.py -q` (**68 passed**) and `git diff --check`; reviewed against both source canvases and installed node code.

### Task 2: Add API request rules and source-image metadata

**Files:** `server/app/api/public.py`, `server/pyproject.toml`, `server/tests/test_public_api.py`

- [x] Add `Pillow>=10` to server dependencies. Use `ImageOps.exif_transpose` before reading dimensions so portrait photos with EXIF rotation get the dimensions shown to the user.
- [x] Raise `/uploads/images` maximum from 9 to 10. Add EXIF-aware `width` and `height` to upload/library-import results; read metadata without decoding pixels, reject Pillow decompression bombs and malformed files with 422, and retain MIME/size checks.
- [x] Extend `ImageJobRequest` with the default legacy workflow and `editSizeMode`/scale/dimensions fields. Enforce per-workflow reference counts, strict JSON numeric types, mode-specific inputs, and `extra="forbid"`.
- [x] For Edit, derive or validate dimensions against the first stored reference, align to 32 and cap at 2048. For T2I, require dimensions aligned to 8 and cap at 2048. Store normalized dimensions in the job payload.
- [x] Add API tests for PNG/JPEG/WebP metadata, all swapped EXIF orientations, malformed/bomb images, 10/11 upload counts, numeric type rejection, workflow limits, dimensions, and payload normalization.
- [x] Verify red-green behavior; run API/library/workflow tests (**105 passed**) and `git diff --check`.

### Task 3: Dispatch the queued job by workflow ID

**Files:** `server/app/jobs/service.py`, `server/tests/test_jobs.py`

- [x] Keep the database job kind as `image` or `video`; store the validated workflow ID and normalized image settings in the existing JSON payload so no SQLite schema migration is needed.
- [x] In `JobService.run_once`, dispatch `qwen_edit_2511` to `build_qwen_prompt`, `qwen_image_2_1_8gb_edit` to `build_qwen_21_edit_prompt`, and `qwen_image_2_1_8gb_t2i` to `build_qwen_21_t2i_prompt`. Keep video dispatch unchanged.
- [x] Add async service tests that capture the ComfyUI prompt and prove each image workflow selects its own graph, passes uploaded image names in order, and supplies validated dimensions. Verify T2I does not upload or pass references.
- [x] Run `python -m pytest server/tests/test_jobs.py -q` and `python -m pytest server/tests/test_workflows.py server/tests/test_public_api.py -q` (Task 3 full server suite: **154 passed**).

### Task 4: Add workflow-scoped mobile state and controls

**Files:** `apps/mobile/src/domain/draft.ts`, `apps/mobile/src/components/ImageSettings.tsx`, `apps/mobile/src/components/WorkflowPicker.tsx`, `apps/mobile/tests/draft.test.ts`

- [x] Define a `WorkflowId` union with the four stable IDs. Add a descriptor for each workflow containing Chinese display name, short description, reference minimum/maximum, and kind (`image` or `video`).
- [x] Change reference-count validation to receive `WorkflowId`; return true for T2I only at count 0, 1–3 for legacy edit, 1–10 for Qwen 2.1 edit, and 1–9 for video.
- [x] Add pure helpers to calculate Edit target dimensions from source width/height and scale factor; round both dimensions to multiples of 32 while minimizing aspect-ratio drift. Add a helper that updates the opposite width/height field from the source ratio, then aligns the submitted result. For T2I, reuse seven existing video ratios and megapixel calculations, with 8-pixel alignment and the 2048-per-side limit.
- [x] Add domain tests for each workflow's min/max counts, scale 0.5×/1.0×/2.0×, portrait and landscape references, width-driven and height-driven locked-ratio edits, alignment rounding, T2I ratio/quality dimensions, and rejection of invalid or over-limit sizes.
- [x] Implement `WorkflowPicker` as four selectable cards in a two-column grid. Show the active model label, one-line purpose, and an accessible selected state. Keep touch targets at least 44 points high.
- [x] Implement Edit settings with the scale slider, editable width and height that remain tied to the first reference image's ratio, source dimensions, and a visible “实际提交尺寸” preview. Reset/recalculate the 1.0× starting target when the first reference changes; retain the user's scale choice while reordering additional references.
- [x] Implement T2I settings with the same ratio, megapixel slider, and custom-dimension affordance used for video, using the T2I alignment and maximums. Hide the reference image strip and insertion controls for T2I.
- [x] Run `npm test -- --run` in `apps/mobile` and `npm run typecheck` after the domain helpers and controls are added (**24 tests passed; typecheck passed**).

### Task 5: Connect workflow selection, drafts, metadata, and submission

**Files:** `apps/mobile/src/api/client.ts`, `apps/mobile/App.tsx`, `apps/mobile/tests/api.test.ts`, `apps/mobile/tests/draft.test.ts`

- [x] Add typed upload/import metadata fields and an image job method that sends `{ prompt, workflow, referenceAssetIds, editSizeMode, scaleFactor, width, height }` as applicable. In `scale` mode send `editSizeMode` and `scaleFactor`; in `dimensions` mode send `editSizeMode`, `width`, and `height`. Omit irrelevant settings by workflow; send T2I with `referenceAssetIds: []` and dimensions.
- [x] Replace the current image/video toggle with `WorkflowPicker`. Store prompts, references, and resolution settings by workflow ID so switching does not silently reuse or truncate another workflow's data.
- [x] Apply each workflow's reference maximum in phone-picker and library-import paths. When an Edit reference is reordered, the new first image becomes the target and the dimension preview is recalculated from its reported metadata.
- [x] Validate prompt, reference count, dimensions, scale, and workflow before submit; show the server validation message without losing the current draft. Submit video through the existing method and retain current video settings behavior.
- [x] Add API tests that assert exact payloads for all three image workflows, including empty references for T2I, normalized dimensions, and omitted irrelevant fields. Add UI/domain regression coverage for switching away and back with independent prompt/reference drafts.
- [x] Run `npm test -- --run` and `npm run typecheck` in `apps/mobile` (**24 tests passed; typecheck passed**).

### Task 6: Document the four choices and verify integration

**Files:** `README.md`, backend and mobile tests listed above

- [x] Update README workflow descriptions and controls: legacy Qwen Edit (1–3 refs), Qwen Image 2.1 8GB Edit (1–10 refs, first image is target, 0.5×–2.0×), Qwen Image 2.1 8GB T2I (no refs, free ratio/resolution), and MiniMax H3 video (1–9 refs).
- [x] Run `python -m pytest server/tests -q` (**154 passed**), then `npm test -- --run` (**24 passed**), `npm run typecheck`, and `npm run export` from `apps/mobile`; run `git diff --check`.
- [ ] With ComfyUI running, submit one low-resolution T2I and one low-resolution Edit manually. Confirm the queue accepts both prompts, Edit uses the first uploaded reference as the target, and artifacts are collected by the existing output reader. Do not make GPU generation part of unattended automated tests. **Not run:** `http://127.0.0.1:8188/system_stats` actively refused the connection, so ComfyUI was not started and no GPU jobs were submitted.
- [ ] Update this plan's checkboxes with the results and record any ComfyUI node schema or runtime constraints discovered during the manual run.

## Self-Review

- Workflow coverage: each of the four choices has a fixed ID, explicit selection UI, distinct API dispatch, and user-facing description.
- Resolution coverage: Edit slider uses source-relative scale; linked inputs preserve the source aspect ratio; server derives/validates dimensions, aligns to 32, and sets the encoder's area-based resize parameter to match the chosen output. T2I has free ratio/quality/custom sizing and 8 alignment.
- Reference coverage: legacy Edit 1–3, Qwen 2.1 Edit 1–10 with ordered target semantics, T2I 0, and MiniMax video 1–9.
- Compatibility: old image requests default to `qwen_edit_2511`; existing video request and builder stay as they are; job payload JSON avoids a database migration.
- Remaining external validation: live ComfyUI `/object_info` schema and low-resolution GPU queue check because the local upstream was not listening during the last query.
