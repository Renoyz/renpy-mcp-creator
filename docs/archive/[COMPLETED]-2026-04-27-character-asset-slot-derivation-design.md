# Character Asset Slot Derivation Design

## Goal

The Character Assets step must present a reviewable list derived from completed story/character design instead of making the user retype character names.

## Scope

This change only affects the stepwise generation character asset stage. It does not add a full character editor, custom roster management, or route-specific costume variants.

## Behavior

- `Start Characters` creates `character_sprite` slots from existing project data.
- Source priority is:
  1. `scene_packages.sprite_plan` `character_id` / `character_name`
  2. `scene_packages.characters_present`
  3. `blueprint.characters`
  4. `project_brief.character_identity.characters`
- Each auto slot stores enough metadata for UI review:
  - `display_name`
  - `role`
  - `appearance`
  - `character_source`
- The default AI prompt for a character uses that metadata when available.
- The UI displays the derived character cards with AI generation and manual upload actions per card.
- The manual “add character” entry remains available only as a fallback when no derived character slots exist.

## Testing

- Unit tests cover blueprint/brief-derived character slots and prompt metadata.
- Frontend tests cover derived character list rendering and ensure the empty manual entry is not the primary UI when slots exist.
- Existing E2E generation tab coverage must still pass.

