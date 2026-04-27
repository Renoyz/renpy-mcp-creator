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
        display_name: "Aya",
        role: "Detective protagonist",
        appearance: "red coat, black notebook",
        character_source: "blueprint",
        prompt: "Generate Aya with red coat and black notebook.",
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

function backgroundState(state: GenerationState["state"]): GenerationState {
  return {
    ...baseState(state),
    character_assets: {},
    background_assets: {
      bg_scene_01_main: {
        asset_id: "bg_scene_01_main",
        kind: "background",
        target: "scene_01",
        variant: "main",
        generation_prompt: "existing background prompt",
        source: "generated",
        status: "generated",
        path: "game/images/background/scene_01_main.png",
        staging_path: "game/__staging__/r0001/images/background/scene_01_main.png",
        preview_url: "/api/projects/demo/asset-file/__staging__/r0001/images/background/scene_01_main.png",
        placeholder: false,
        renderable: true,
        description: "An evening city street with neon lights and wet pavement.",
        validation: { ok: true, width: 1280, height: 720, reason: "ok" },
      },
    },
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

  it("shows derived character design metadata as a reviewable slot list", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={baseState("character_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    const slotCard = screen.getByTestId("slot-card-char_Alice_normal");

    expect(screen.queryByText("No character slots yet.")).not.toBeInTheDocument();
    expect(within(slotCard).getByText("Aya")).toBeInTheDocument();
    expect(within(slotCard).getByText(/Detective protagonist/)).toBeInTheDocument();
    expect(within(slotCard).getByText(/red coat, black notebook/)).toBeInTheDocument();
    expect(within(slotCard).getByText(/Design source: blueprint/)).toBeInTheDocument();
    expect(within(slotCard).getByLabelText("Alice normal prompt")).toHaveValue(
      "existing generated prompt"
    );
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

  it("shows manual workflow text and Scene Backgrounds section name", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={backgroundState("background_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    expect(screen.getByText(/Manual progression:/)).toBeInTheDocument();
    expect(screen.getByText("Character Assets")).toBeInTheDocument();
    expect(screen.getByText("Scene Backgrounds")).toBeInTheDocument();
    expect(screen.getByText("Script Preview & Commit")).toBeInTheDocument();
  });

  it("shows scene background description field and keeps prompt editable from the UI", async () => {
    const user = userEvent.setup();
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={backgroundState("background_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    const slotCard = screen.getByTestId("slot-card-bg_scene_01_main");
    const descriptionBox = within(slotCard).getByLabelText("scene_01 main description");
    const promptBox = within(slotCard).getByLabelText("scene_01 main prompt");

    expect(descriptionBox).toHaveValue("An evening city street with neon lights and wet pavement.");
    expect(promptBox).toHaveValue("existing background prompt");
    await user.clear(descriptionBox);
    await user.type(descriptionBox, "A moonlit cyberpunk alley.");
    await user.clear(promptBox);
    await user.type(promptBox, "wide-angle alley backdrop");

    expect(descriptionBox).toHaveValue("A moonlit cyberpunk alley.");
    expect(promptBox).toHaveValue("wide-angle alley backdrop");
  });

  it("sends background generation body with prompt/replace/description payload when regenerating", async () => {
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
        generationState={backgroundState("background_assets_draft")}
        loadGenerationState={loadGenerationState}
      />
    );

    const slotCard = screen.getByTestId("slot-card-bg_scene_01_main");
    const descriptionBox = within(slotCard).getByLabelText("scene_01 main description");
    await user.clear(descriptionBox);
    await user.type(descriptionBox, "Neon alley at night");
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/backgrounds/scene_01/main/generate",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: "existing background prompt",
          replace: false,
          description: "Neon alley at night",
        }),
      })
    );
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });

  it("sends background upload multipart body with the edited description", async () => {
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
        generationState={backgroundState("background_assets_draft")}
        loadGenerationState={loadGenerationState}
      />
    );

    const slotCard = screen.getByTestId("slot-card-bg_scene_01_main");
    const descriptionBox = within(slotCard).getByLabelText("scene_01 main description");
    await user.clear(descriptionBox);
    await user.type(descriptionBox, "Rainy moonlit alley");

    const uploadInput = within(slotCard).getByLabelText("Manual Upload");
    const file = new File(["fake"], "scene.png", { type: "image/png" });
    await user.upload(uploadInput, file);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/backgrounds/scene_01/main/upload",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      })
    );
    const [, init] = fetchMock.mock.calls[0];
    const formData = init.body as FormData;
    expect(formData.get("description")).toBe("Rainy moonlit alley");
    expect(formData.get("file")).toBe(file);
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });

  it("lets the empty-state background upload card use its own target and description", async () => {
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
        generationState={{
          ...baseState("background_assets_draft"),
          character_assets: {},
          background_assets: {},
        }}
        loadGenerationState={loadGenerationState}
      />
    );

    await user.type(screen.getByLabelText("Background upload target"), "upload_scene");
    await user.clear(screen.getByLabelText("Background upload variant"));
    await user.type(screen.getByLabelText("Background upload variant"), "dusk");
    await user.type(screen.getByLabelText("Background upload description"), "Uploaded rainy pier at dusk");

    const file = new File(["fake"], "pier.png", { type: "image/png" });
    await user.upload(screen.getAllByLabelText("Manual Upload")[1], file);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/backgrounds/upload_scene/dusk/upload",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      })
    );
    const [, init] = fetchMock.mock.calls[0];
    const formData = init.body as FormData;
    expect(formData.get("description")).toBe("Uploaded rainy pier at dusk");
    expect(formData.get("file")).toBe(file);
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
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
