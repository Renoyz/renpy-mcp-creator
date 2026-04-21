# Multi-Chapter Style Consistency Design

## Scope

This design covers a Phase 6 generation-before-audit consistency layer for:

- text generation
- background generation
- character sprite generation

It does not implement full audit automation yet. Audit remains a follow-up phase that will consume the same structured inputs introduced here.

## Goal

Ensure that multi-chapter projects keep a stable identity across chapters while still allowing controlled chapter-level variation.

The system should preserve:

- project-wide visual language
- stable character appearance and identity anchors
- stable dialogue voice and narrative tone
- continuity-critical world and relationship facts

The system should allow chapter-level variation only in a bounded way, such as:

- mood
- color temperature
- lighting bias
- pacing
- emotional pressure / warmth / isolation

## Non-Goals

- No full CreatorAgent / AuditorAgent implementation
- No Phase 6 audit UI implementation in this round
- No full CG / audio / UI asset bible in the first rollout
- No model-fine-tuning workflow
- No image embedding / CLIP-style similarity system in the first rollout

## Product Requirement

When a project has multiple chapters, generation should not treat each chapter as an isolated prompt-writing task.

Instead, each chapter generation request must be grounded in:

1. a project-wide canonical style bible
2. a chapter-level controlled style profile
3. a generation contract built from those two layers

This contract must be consumed by:

- chapter scene generation
- background prompt generation
- character sprite prompt generation

## Design Summary

Use a two-layer consistency model:

### 1. Project Style Bible

The project-level source of truth. This defines what must remain stable across the entire game.

### 2. Chapter Style Profile

A chapter-level overlay that can shift mood and presentation within project-defined bounds, without replacing the project identity.

### 3. Generation Contract

A normalized runtime structure assembled from the project bible and the chapter profile. This is what generation code actually consumes.

This keeps editing and persistence human-readable while making runtime usage deterministic and testable.

## Data Model

### ProjectStyleBible

Recommended persisted location:

- `meta/style_bible.json`

Suggested schema:

```json
{
  "visual_bible": {
    "art_direction": "modern anime VN, clean line art, soft cinematic shading",
    "palette_baseline": "neutral-cool office palette with restrained accents",
    "camera_language": "mid-distance readable staging, not poster-like closeups",
    "background_complexity_budget": "medium",
    "forbidden_visual_drift": [
      "photorealism",
      "chibi",
      "heavy painterly rendering",
      "poster composition",
      "extreme wide-shot storytelling backgrounds for sprites"
    ]
  },
  "character_bible": {
    "characters": [
      {
        "name": "Lin Xiao",
        "identity_anchors": [
          "black shoulder-length hair",
          "thin-framed glasses",
          "slim officewear silhouette"
        ],
        "default_costume": "modern office casual",
        "forbidden_drift": [
          "different hairstyle family",
          "fantasy costume",
          "teenage school uniform"
        ]
      }
    ]
  },
  "tone_bible": {
    "narration_style": "clean, readable, restrained",
    "dialogue_style": "direct spoken Chinese, not summary prose",
    "dialogue_density": "short to medium",
    "forbidden_tone_drift": [
      "melodramatic monologue",
      "omniscient literary summary in dialogue box",
      "internet slang unless character-specific"
    ]
  },
  "continuity_bible": {
    "world_rules": [],
    "relationship_baselines": [],
    "must_preserve_facts": []
  }
}
```

### ChapterStyleProfile

Recommended persisted location:

- `meta/chapter_style_profiles.json`

Suggested schema:

```json
{
  "chapters": [
    {
      "chapter_id": "ch1",
      "mood_target": "uneasy but grounded",
      "temperature_bias": "cool-neutral",
      "lighting_bias": "soft overcast interior light",
      "pacing_bias": "measured",
      "emotional_bias": "suppressed pressure",
      "location_motifs": [
        "office interior",
        "glass partitions",
        "workstation clutter"
      ],
      "allowed_variation": {
        "palette_shift_max": "small",
        "contrast_shift_max": "small",
        "dialogue_intensity_shift_max": "small-to-medium"
      }
    }
  ]
}
```

### GenerationContract

This is not primarily an authoring format. It is the internal normalized input for generation.

Suggested structure:

```json
{
  "chapter_id": "ch1",
  "visual_contract": {
    "art_direction": "...",
    "palette_baseline": "...",
    "camera_language": "...",
    "mood_target": "...",
    "temperature_bias": "...",
    "lighting_bias": "...",
    "location_motifs": ["..."]
  },
  "character_contract": {
    "characters": [
      {
        "name": "Lin Xiao",
        "identity_anchors": ["..."],
        "default_costume": "...",
        "chapter_variation": "none"
      }
    ]
  },
  "tone_contract": {
    "dialogue_style": "...",
    "dialogue_density": "...",
    "pacing_bias": "..."
  },
  "continuity_contract": {
    "must_preserve_facts": ["..."],
    "relationship_state": ["..."]
  }
}
```

## Ownership and Flow

### Persistence Layer

Responsible for:

- reading / writing `style_bible.json`
- reading / writing `chapter_style_profiles.json`
- providing safe defaults for old projects

Recommended location:

- `ProjectManager` plus small dedicated helpers if needed

### Contract Assembly Layer

Responsible for:

- loading project bible
- loading chapter profile
- merging them into a normalized generation contract
- rejecting invalid chapter overrides that replace project-level invariants

Recommended location:

- new helper inside `prototype_generation_service.py` first
- later extract into dedicated service if it grows

### Generation Consumers

#### A. Scene Generation

`generate_scenes()` must consume:

- visual contract
- tone contract
- continuity contract

Effects:

- scene summaries stay in one visual world
- `location_visual_brief` stops drifting chapter by chapter
- `mood` remains chapter-shaped but project-consistent
- dialogue beats keep one stable voice

#### B. Background Generation

Background prompts must consume:

- project visual bible
- chapter visual profile
- scene-specific location brief

Prompt priority should be:

1. project art direction
2. project camera language
3. chapter mood / lighting / palette shift
4. scene-specific location content

This prevents scene location descriptions from overpowering the project-wide style.

#### C. Character Sprite Generation

Character prompts must consume:

- project visual bible
- character identity anchors
- chapter mood / lighting bias
- scene context only as secondary support

Important rule:

Scene context must not be allowed to rewrite core character identity or turn sprite generation into chapter-specific redesign.

Character prompts should use:

- project-wide character anchors as hard constraints
- chapter profile only for mood-compatible presentation
- scene context only for atmosphere matching

## Constraints and Override Rules

### Project-Level Hard Constraints

These may not be overridden by chapter profiles:

- core art direction
- character identity anchors
- forbidden visual drift
- dialogue style baseline
- continuity-critical world facts

### Chapter-Level Soft Constraints

These may vary within limits:

- mood
- warmth / coldness
- lighting direction and intensity
- pacing
- emotional intensity
- environmental motif emphasis

### Conflict Resolution

If chapter profile conflicts with project bible:

- project bible wins
- chapter profile is clipped to an allowed subset
- conflict is logged for future audit consumption

## Backward Compatibility

Old projects without these files should still work.

Fallback behavior:

1. infer a minimal project style bible from:
   - blueprint art style
   - worldview
   - existing chapter summaries
2. infer a minimal chapter profile from:
   - chapter summary
   - generated scene moods
3. mark inferred data as generated defaults rather than user-authored truth

This allows progressive adoption without migration gates.

## Failure Modes

### Missing Bible Data

Fallback to inferred defaults, but keep generation working.

### Invalid Chapter Override

Reject only the invalid override and continue with project-level defaults.

### Over-Specified Prompt Explosion

The contract builder should produce compact normalized guidance, not dump raw bible text into every prompt.

The prompt layer must summarize and prioritize:

- invariants
- chapter bias
- scene specifics

rather than concatenate everything verbatim.

## Testing Strategy

### Unit / Integration Requirements

At minimum:

1. project style bible can be persisted and read back
2. chapter style profiles can be persisted and read back
3. generation contract merges project + chapter rules deterministically
4. chapter profile cannot override forbidden project-level invariants
5. scene generation prompt includes project-level style plus chapter-level bias
6. background prompt includes project baseline plus chapter bias without dropping scene location
7. character prompt includes character identity anchors plus chapter atmosphere but does not over-weight location scene content
8. backward-compatible inference path works when style files are missing

### Deferred Audit Tests

Not in the first implementation round, but this design intentionally enables:

- continuity deviation detection
- tone drift detection
- character identity drift detection
- chapter-to-chapter visual drift detection

## Recommended Implementation Order

### Phase 6 Round 1

- add `style_bible.json` persistence
- add `chapter_style_profiles.json` persistence
- add contract assembly helper
- make scene/background/character generation consume the contract
- add tests for merge rules and prompt composition

### Phase 6 Round 2

- expose read APIs for style bible and chapter profiles
- surface chapter style snapshots in workspace
- add debug visibility for effective generation contract

### Phase 6 Round 3

- plug same contract into audit generation
- produce first `AuditReport` dimensions for continuity and tone alignment

## Recommendation

Implement a two-layer consistency system:

- project-level canonical style bible
- chapter-level controlled style profile

Then build a normalized generation contract that every generation step consumes.

This is the smallest design that:

- stabilizes multi-chapter output before audit
- keeps chapter variation possible
- remains compatible with the existing Phase 5 prototype pipeline
- directly prepares the ground for later AuditReport and dual-agent work
