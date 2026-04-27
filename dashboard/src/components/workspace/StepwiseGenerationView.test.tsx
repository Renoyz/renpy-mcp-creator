import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GenerationState } from "@/context/ProjectContext";
import { StepwiseGenerationView } from "./StepwiseGenerationView";

function baseState(state: GenerationState["state"]): GenerationState {
  return {
    state,
    round_id: "r0001",
    character_assets: {
      char_Alice_normal: {
        asset_id: "char_Alice_normal",
        kind: "character_sprite",
        target: "Alice",
        variant: "normal",
        generation_prompt: "existing generated prompt",
        source: "uploaded",
        status: "uploaded",
        path: "game/images/sprites/char_Alice_normal.png",
        staging_path: "game/__staging__/r0001/images/sprites/char_Alice_normal.png",
        preview_url: "/api/projects/demo/asset-file/__staging__/r0001/images/sprites/char_Alice_normal.png",
        placeholder: false,
        renderable: true,
        validation: { ok: true, width: 640, height: 360, reason: "ok" },
      },
    },
    background_assets: {},
    script_preview: null,
  };
}

describe("StepwiseGenerationView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("allows character acceptance and confirmation while backgrounds are in draft", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={baseState("background_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    const characterSection = screen.getByText("Character Assets").closest("div")?.parentElement;
    expect(characterSection).not.toBeNull();

    expect(within(characterSection as HTMLElement).getByRole("button", { name: "Confirm Characters" })).toBeEnabled();
    expect(within(characterSection as HTMLElement).getByRole("button", { name: "Accept" })).toBeEnabled();
  });

  it("shows AI generation and manual upload as peer entry points without fallback wording", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={{
          ...baseState("character_assets_draft"),
          character_assets: {},
          background_assets: {},
        }}
        loadGenerationState={vi.fn()}
      />
    );

    expect(screen.getAllByText("Generate with AI").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Upload Image").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByLabelText("Prompt").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/fallback/i)).not.toBeInTheDocument();
  });

  it("regenerates an existing character slot with the edited prompt and reloads state", async () => {
    const user = userEvent.setup();
    const loadGenerationState = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={baseState("character_assets_draft")}
        loadGenerationState={loadGenerationState}
      />
    );

    const slotCard = screen.getByTestId("slot-card-char_Alice_normal");
    const promptBox = within(slotCard).getByLabelText("Alice normal prompt");
    await user.clear(promptBox);
    await user.type(promptBox, "new ink vampire sprite prompt");
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/characters/Alice/normal/generate",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "new ink vampire sprite prompt", replace: false }),
      })
    );
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });

  it("regenerates an accepted slot with replace=true so edited prompts can be applied", async () => {
    const user = userEvent.setup();
    const loadGenerationState = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    const state = baseState("character_assets_confirmed");
    state.character_assets.char_Alice_normal.status = "accepted";

    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={state}
        loadGenerationState={loadGenerationState}
      />
    );

    const slotCard = screen.getByTestId("slot-card-char_Alice_normal");
    const promptBox = within(slotCard).getByLabelText("Alice normal prompt");
    await user.clear(promptBox);
    await user.type(promptBox, "replacement accepted sprite prompt");
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate accepted" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/characters/Alice/normal/generate",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "replacement accepted sprite prompt", replace: true }),
      })
    );
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });
});
