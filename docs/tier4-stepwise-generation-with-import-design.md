# Tier 4 Stepwise Generation With User Image Import

Updated: 2026-04-26

Status: Design proposal

## Goal

Tier 4 should let users review and intervene at every generation step, and image assets must support two first-class sources:

- AI-generated assets
- User-imported images

User import is not a fallback for failed generation. It is an equal path for filling an asset slot, with the same validation, preview, accept, retry, persistence, commit, and rollback behavior.

## Target Flow

```text
Freeze Blueprint
  -> Step 1: Generate and review scene outline
  -> Step 2: Character sprites: generate or upload -> accept per asset
  -> Step 3: Backgrounds: generate or upload -> accept per asset
  -> Step 4: Script preview -> final commit -> build/preview
```

The existing full-auto prototype pipeline should remain available during the migration. Stepwise generation adds a controlled workflow; it should not break the current verified full-chain path.

## Asset Slot Model

Every generated or uploaded image fills an asset slot. The slot is the stable unit of state and testing.

Example:

```json
{
  "asset_id": "char_alice_normal",
  "kind": "character_sprite",
  "target": "Alice",
  "variant": "normal",
  "source": "generated",
  "status": "accepted",
  "path": "game/images/character/alice_normal.png",
  "staging_path": "game/__staging__/r123/images/character/alice_normal.png",
  "preview_url": "/api/projects/demo/asset-file/__staging__/r123/images/character/alice_normal.png",
  "placeholder": false,
  "renderable": true,
  "validation": {
    "ok": true,
    "width": 512,
    "height": 768,
    "reason": "ok"
  }
}
```

Allowed `source` values:

- `generated`
- `uploaded`

Allowed `status` values:

- `empty`
- `generating`
- `uploaded`
- `accepted`
- `failed`

Production API responses must not expose absolute filesystem paths. Persisted metadata and API payloads should use project-relative paths and preview URLs only.

## Backend Architecture

Add two focused services:

```text
src/renpy_mcp/services/stepwise_generation_service.py
src/renpy_mcp/services/imported_asset_service.py
```

`StepwiseGenerationService` owns:

- step state machine
- step gate checks
- scene outline start/confirm
- character/background generate, upload, accept, confirm
- script preview
- final commit coordination
- rollback coordination

`ImportedAssetService` owns:

- upload validation
- safe filename normalization
- image decoding and dimension checks
- staging path allocation
- metadata generation
- preview URL generation

## Persistence

Persist stepwise state to:

```text
project/meta/generation_state.json
project/game/__staging__/<round_id>/
```

Recommended state values:

```text
idle
scene_outline_draft
scene_outline_confirmed
character_assets_draft
character_assets_confirmed
background_assets_draft
background_assets_confirmed
script_preview
committed
failed
```

Step 1-3 must write only staging files and metadata. They must not modify:

- `game/script.rpy`
- final prototype scripts
- final `game/images/...` assets
- project index runtime entries

Only the final script commit may promote staging artifacts to final runtime paths.

## Upload Rules

Image upload must be project-scoped and safe by default.

Rules:

- Accept only `png`, `jpg`, `jpeg`, and `webp`.
- Reject non-image bytes even if the extension looks valid.
- Normalize user filenames; never trust submitted path segments.
- Store uploads under `game/__staging__/<round_id>/...` first.
- Return only project-relative paths and preview URLs.
- Reject path traversal attempts.
- Enforce a reasonable upload size limit.

Background validation:

- Decode dimensions.
- Prefer 16:9 images.
- Non-16:9 should be allowed with a warning unless it cannot be decoded.

Character sprite validation:

- Decode dimensions.
- Prefer transparent PNG or WebP with alpha.
- If the image has no alpha channel, do not silently mark it renderable.
- The UI may offer background removal, re-upload, or keep as a non-renderable draft.

Placeholder assets:

- Must be explicitly marked with `placeholder: true`.
- Must not be silently accepted as real generated/imported assets.
- If accepting placeholders is supported, the UI must make that explicit.

## API Design

Add these routes under the existing generation router:

```text
GET  /api/projects/{name}/generation-state

POST /api/projects/{name}/generation/scene-outline/start
POST /api/projects/{name}/generation/scene-outline/confirm

POST /api/projects/{name}/generation/characters/start
POST /api/projects/{name}/generation/characters/{character_id}/{variant}/generate
POST /api/projects/{name}/generation/characters/{character_id}/{variant}/upload
POST /api/projects/{name}/generation/characters/{character_id}/{variant}/accept
POST /api/projects/{name}/generation/characters/confirm

POST /api/projects/{name}/generation/backgrounds/start
POST /api/projects/{name}/generation/backgrounds/{location_id}/generate
POST /api/projects/{name}/generation/backgrounds/{location_id}/upload
POST /api/projects/{name}/generation/backgrounds/{location_id}/accept
POST /api/projects/{name}/generation/backgrounds/confirm

POST /api/projects/{name}/generation/script/preview
POST /api/projects/{name}/generation/script/commit
```

Upload endpoints use `multipart/form-data`:

```text
file: image
note: optional string
```

WebSocket should be progress-only, not the only source of truth:

```text
generation_step_started
generation_item_progress
generation_item_done
generation_item_failed
generation_step_ready_for_review
generation_state_updated
```

The Dashboard should recover state from `GET /generation-state`, not from local fake state machines.

## Frontend Interaction

Step 2 and Step 3 asset cards should expose the same actions:

```text
[AI Generate] [Upload Image] [Accept] [Replace]
```

Character card layout:

```text
Alice
  normal: empty/generated/uploaded/accepted
  happy:  empty/generated/uploaded/accepted
  sad:    empty/generated/uploaded/accepted
```

Background card layout:

```text
Rooftop Cafe
  source: uploaded
  validation: 1280x720 ok
  preview: /api/projects/demo/asset-file/...
```

If an uploaded background has a non-ideal aspect ratio, show a warning:

```text
Image is usable, but it is not close to 16:9 and may be cropped in preview.
```

If an uploaded character image has no alpha channel, show a blocking or explicit-choice warning:

```text
This sprite has no transparent background. Choose background removal, re-upload, or keep it as a non-renderable draft.
```

## Transaction And Rollback Rules

These rules are non-negotiable:

- Generate and upload must write draft assets to staging only.
- Accepting an item updates metadata only; it does not promote files to final runtime paths.
- Retrying or uploading one item must not affect other accepted items.
- Accepted items must not be overwritten unless the user explicitly replaces them.
- Script preview must read confirmed scene packages and accepted assets only.
- Final commit must fail with `409` if required assets are missing or unaccepted.
- Final commit must promote staging files and update scripts/index/manifest transactionally.
- Commit failure must preserve the previous working prototype and stable assets.
- Same-path regeneration must not overwrite a stable prior asset before commit.

Final commit should reuse existing prototype activation and staged replacement behavior instead of creating a second commit path.

## Testing Strategy

Testing must be implemented before production logic for each step. Do not change production logic and then preserve old tests with compatibility flags.

New tests:

```text
tests/unit/test_imported_asset_service.py
tests/unit/test_stepwise_generation_state.py
tests/unit/test_stepwise_generation_service.py
tests/integration/test_stepwise_generation_api.py
tests/integration/test_stepwise_generation_import_upload.py
tests/integration/test_stepwise_generation_commit_rollback.py
```

Required coverage:

- Uploading a valid background writes to staging, marks `source=uploaded`, and returns a preview URL.
- Uploading a transparent character PNG marks the item renderable.
- Uploading a non-transparent JPG for a character does not mark it renderable silently.
- Uploading a non-image file returns `400`.
- Uploading with a malicious filename cannot escape the staging directory.
- Accepting one item updates only that item.
- AI generation after upload replaces only the draft for that item.
- An accepted item is not overwritten unless the request explicitly says replace.
- Script preview does not write final script files.
- Final commit fails when required assets are missing or unaccepted.
- Final commit promotes accepted uploaded assets to final project-relative paths.
- Final commit updates script, index, and manifest consistently.
- Commit failure rolls back and preserves old prototype files and assets.
- API payloads do not contain absolute paths.
- Placeholder assets remain explicit and are not treated as real imported assets.

Existing full-auto prototype tests should stay in place as backward-compatibility coverage. Do not add production `RENPY_MCP_LEGACY_*` branches to satisfy old tests.

## Verification Commands

Run at minimum:

```text
python -m pytest tests/unit/test_imported_asset_service.py tests/unit/test_stepwise_generation_state.py tests/unit/test_stepwise_generation_service.py -q
python -m pytest tests/integration/test_stepwise_generation_api.py tests/integration/test_stepwise_generation_import_upload.py tests/integration/test_stepwise_generation_commit_rollback.py -q
python -m pytest tests/integration/test_prototype_generation_phase6_round1.py tests/integration/test_prototype_generation_round11.py -q
cd dashboard && npm run build
```

Do not run real LLM or real image-generation services in automated tests. Stub provider chat and image generation. Use small in-memory or temporary image files for upload tests.

## Implementation Order

1. Add `ImportedAssetService` tests and implementation.
2. Add stepwise state model tests and implementation.
3. Add `StepwiseGenerationService` unit tests for gate, start, upload, generate, accept, confirm, preview, and commit.
4. Add REST API integration tests and routes.
5. Integrate script preview and final commit with existing prototype activation logic.
6. Update Dashboard to consume real project-scoped APIs.
7. Run the verification commands and update `docs/ROADMAP.md` status.

## Main Risk

The main risk is accidentally creating two separate asset lifecycles: one for generated assets and one for uploaded assets. The design avoids that by making the asset slot the shared abstraction. Generation and upload are only two ways to fill a slot; validation, acceptance, preview, persistence, commit, and rollback must be shared.
