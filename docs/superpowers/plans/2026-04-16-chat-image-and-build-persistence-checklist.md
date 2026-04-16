# Chat Image And Build Persistence Checklist

## Goal

1. Let users see generated images directly inside the chat drawer. Done.
2. Make build status recoverable after page refresh and server restart. Done in working tree and verified.
3. Defer chat history persistence to a later design pass.

## Current Status

- Task A: Complete and already committed.
- Task B: Complete in the working tree and verified locally; not committed from this workspace state.
- Task C: Not started.

## Task A: Render Generated Images In Chat

Status: Complete and committed (`0115f85`, with follow-up fix in `09f8a8c`).

- [x] Read the current chat result flow:
  - `dashboard/src/components/ChatDrawer.tsx`
  - `src/renpy_mcp/web/chat_ws.py`
  - `src/renpy_mcp/web/fastapi_app.py`
- [x] Design a browser-safe image URL strategy for project assets under `game/images/...`
- [x] Add a backend asset-serving route for current-project image preview
- [x] Enforce path safety so the route cannot read arbitrary files outside the project
- [x] Extend successful image-generation `tool_result` payloads with browser-usable URLs
- [x] Include enough metadata for frontend rendering:
  - `image_type`
  - `relative_files`
  - `preview_urls`
  - `primary_preview_url`
- [x] Extend chat message rendering so image results can appear inline
- [x] Keep the chat UI free of raw `tool_start` / `tool_result` noise
- [x] Show both a short summary and an image preview
- [x] Cover both background and character image results
- [x] Add integration tests for image result payloads with preview URLs
- [x] Add E2E coverage that verifies an image appears in the chat drawer after generation

## Task A Acceptance

- [x] Generated background images are visible directly in the chat drawer
- [x] Generated character images are visible directly in the chat drawer
- [x] Image URLs are backend-served and path-safe
- [x] Existing confirmation flow still works

## Task B: Persist And Restore Build Status

Status: Complete in working tree and verified locally; current fixes address the latest review items.

- [x] Read the current workspace build/preview flow:
  - `dashboard/src/pages/ProjectWorkspacePage.tsx`
  - `src/renpy_mcp/web/fastapi_app.py`
- [x] Confirm the current status model:
  - chat messages are frontend-only state
  - build result is frontend-only state plus process-memory `_last_build_results`
- [x] Add a backend status persistence file per project
- [x] Choose a project-local path such as:
  - `logs/build-status.json`
  - or `_mcp/build-status.json`
- [x] Write build status on both success and failure
- [x] Store enough information to restore UI state:
  - `status`
  - `message`
  - `output_path`
  - `previewable`
  - `updated_at`
- [x] Add `GET /api/projects/build/status`
- [x] Make the preview path resolve from persisted successful build data, not only in-memory cache
- [x] Keep `_last_build_results` as a fast cache only if it stays consistent with persisted state
- [x] Load build status when the workspace page mounts
- [x] Restore build message and preview availability after page refresh
- [x] Restore build status after server restart
- [x] Add integration tests for status write/read and app recreation
- [x] Add E2E coverage for refresh recovery after a successful build

## Task B Acceptance

- [x] Refreshing the workspace preserves the last build status
- [x] Restarting the backend preserves the last build status
- [x] Preview still uses the latest successful build result
- [x] Build state is no longer only component memory

## Task C: Chat History Persistence Evaluation Only

Status: Not started.

- [ ] Document whether chat history should be persisted per project
- [ ] Compare minimal storage approaches:
  - frontend `localStorage`
  - backend project JSON
  - session storage
- [ ] Recommend a scope for a future implementation
- [ ] Do not implement chat history persistence in this round

## Execution Order

1. Task A
2. Task B
3. Task C evaluation only

## Scope Limits

- [x] Do not redesign the full chat protocol
- [x] Do not implement general chat-history persistence in this round
- [x] Do not refactor unrelated pages
- [x] Prefer tests first, then minimal implementation

## Suggested Commit Split

1. `feat: render generated images in chat drawer`
2. `feat: persist and restore project build status`
