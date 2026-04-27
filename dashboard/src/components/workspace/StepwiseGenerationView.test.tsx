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
    scene_generation: null,
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

    const characterSection = screen.getByTestId("character-assets-section");

    expect(within(characterSection).getByRole("button", { name: "Confirm Characters" })).toBeEnabled();
    expect(within(characterSection).getByRole("button", { name: "Accept" })).toBeEnabled();
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
    expect(within(slotCard).getByText("existing generated prompt")).toBeInTheDocument();
    expect(within(slotCard).getByRole("button", { name: "Edit Prompt" })).toBeInTheDocument();
    expect(within(slotCard).getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
    expect(within(slotCard).getByLabelText("Manual Upload")).toBeInTheDocument();
  });

  it("renders generated assets as list rows with thumbnail, description, prompt, and combined actions columns", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={baseState("character_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    const slotRow = screen.getByTestId("asset-row-char_Alice_normal");
    const columns = within(slotRow).getAllByRole("cell");

    expect(columns).toHaveLength(4);
    expect(within(columns[0]).getByAltText("Aya normal")).toBeInTheDocument();
    expect(within(columns[1]).getByText("Aya")).toBeInTheDocument();
    expect(within(columns[1]).getByText(/Detective protagonist/)).toBeInTheDocument();
    expect(within(columns[2]).getByText("existing generated prompt")).toBeInTheDocument();
    expect(within(columns[2]).getByRole("button", { name: "Edit Prompt" })).toBeInTheDocument();
    expect(within(columns[3]).getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
    expect(within(columns[3]).getByLabelText("Manual Upload")).toBeInTheDocument();
  });

  it("does not show manual target forms as the default empty-state workflow", () => {
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

    expect(screen.getByText("No derived character slots available.")).toBeInTheDocument();
    expect(screen.getByText("No derived scene background slots available.")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("character name/id")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("scene id")).not.toBeInTheDocument();
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
    expect(screen.getByTestId("character-assets-section")).toHaveTextContent("Character Assets");
    expect(screen.getByTestId("scene-backgrounds-section")).toHaveTextContent("Scene Backgrounds");
    expect(screen.getByText("Script Preview & Commit")).toBeInTheDocument();
  });

  it("renders a visible generation flow panel before asset tables", () => {
    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={backgroundState("background_assets_draft")}
        loadGenerationState={vi.fn()}
      />
    );

    const flow = screen.getByTestId("generation-flow-panel");

    expect(flow).toHaveTextContent("Scene Packages");
    expect(flow).toHaveTextContent("Character Assets");
    expect(flow).toHaveTextContent("Scene Backgrounds");
    expect(flow).toHaveTextContent("Script Preview");
    expect(flow).toHaveTextContent("Build");
    expect(flow).toHaveTextContent("Preview");
  });

  it("shows per-chapter scene package progress and generates all remaining chapters in one action", async () => {
    const user = userEvent.setup();
    const loadGenerationState = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          complete: false,
          scene_generation: {
            status: "in_progress",
            completed_count: 1,
            total_count: 2,
            current_chapter_id: "ch1",
            chapters: [],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          complete: true,
          scene_generation: {
            status: "complete",
            completed_count: 2,
            total_count: 2,
            current_chapter_id: null,
            chapters: [],
          },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={{
          ...baseState("idle"),
          scene_generation: {
            status: "in_progress",
            completed_count: 1,
            total_count: 2,
            current_chapter_id: "ch1",
            chapters: [
              { chapter_id: "ch1", chapter_name: "Opening", chapter_order: 1, status: "complete", scene_count: 3 },
              { chapter_id: "ch2", chapter_name: "Aftermath", chapter_order: 2, status: "pending", scene_count: 0 },
            ],
          },
        }}
        loadGenerationState={loadGenerationState}
      />
    );

    expect(screen.getByText("Scene Package Progress")).toBeInTheDocument();
    expect(within(screen.getByTestId("scene-package-progress-panel")).getByText(/1\s*\/\s*2 chapters complete/)).toBeInTheDocument();
    expect(screen.getByText("Opening")).toBeInTheDocument();
    expect(screen.getByText("Aftermath")).toBeInTheDocument();
    expect(screen.getByText("complete")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate Scene Packages" }));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/projects/demo/scene-packages/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/projects/demo/scene-packages/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(loadGenerationState).toHaveBeenCalledTimes(3);
  });

  it("does not hammer scene package generation while a chapter is already generating", async () => {
    const user = userEvent.setup();
    const loadGenerationState = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        complete: false,
        scene_generation: {
          status: "in_progress",
          completed_count: 1,
          total_count: 2,
          current_chapter_id: "ch1",
          chapters: [
            { chapter_id: "ch1", chapter_name: "Opening", chapter_order: 1, status: "generating", scene_count: 0 },
            { chapter_id: "ch2", chapter_name: "Aftermath", chapter_order: 2, status: "pending", scene_count: 0 },
          ],
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={{
          ...baseState("idle"),
          scene_generation: {
            status: "in_progress",
            completed_count: 1,
            total_count: 2,
            current_chapter_id: "ch1",
            chapters: [
              { chapter_id: "ch1", chapter_name: "Opening", chapter_order: 1, status: "generating", scene_count: 0 },
              { chapter_id: "ch2", chapter_name: "Aftermath", chapter_order: 2, status: "pending", scene_count: 0 },
            ],
          },
        }}
        loadGenerationState={loadGenerationState}
      />
    );

    await user.click(screen.getByRole("button", { name: "Generate Scene Packages" }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(loadGenerationState).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("Scene package generation did not reach completion.")).not.toBeInTheDocument();
  });

  it("shows scene background description field and edits prompt from a dialog", async () => {
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

    expect(descriptionBox).toHaveValue("An evening city street with neon lights and wet pavement.");
    expect(within(slotCard).getByText("existing background prompt")).toBeInTheDocument();
    await user.clear(descriptionBox);
    await user.type(descriptionBox, "A moonlit cyberpunk alley.");
    await user.click(within(slotCard).getByRole("button", { name: "Edit Prompt" }));
    const dialog = screen.getByRole("dialog", { name: "Edit asset prompt" });
    const promptBox = within(dialog).getByLabelText("scene_01 main prompt");
    await user.clear(promptBox);
    await user.type(promptBox, "wide-angle alley backdrop");
    await user.click(within(dialog).getByRole("button", { name: "Done" }));

    expect(descriptionBox).toHaveValue("A moonlit cyberpunk alley.");
    expect(within(slotCard).getByText("wide-angle alley backdrop")).toBeInTheDocument();
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
    await user.click(within(slotCard).getByRole("button", { name: "Edit Prompt" }));
    const dialog = screen.getByRole("dialog", { name: "Edit asset prompt" });
    const promptBox = within(dialog).getByLabelText("Alice normal prompt");
    await user.clear(promptBox);
    await user.type(promptBox, "new ink vampire sprite prompt");
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/characters/assets/char_Alice_normal/generate",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "new ink vampire sprite prompt", replace: false }),
      })
    );
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });

  it("does not render polluted background slots in the character asset list", async () => {
    const user = userEvent.setup();
    const loadGenerationState = vi.fn().mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    const state = baseState("character_assets_draft");
    state.character_assets.bg_polluted_main = {
      asset_id: "bg_polluted_main",
      kind: "background",
      target: "polluted",
      variant: "main",
      generation_prompt: "background prompt leaked into character collection",
      source: null,
      status: "empty",
      path: null,
      staging_path: null,
      preview_url: null,
      placeholder: false,
      renderable: true,
      description: "A leaked background slot.",
      validation: { ok: true, width: 1280, height: 720, reason: "ok" },
    };

    render(
      <StepwiseGenerationView
        projectName="demo"
        generationState={state}
        loadGenerationState={loadGenerationState}
      />
    );

    expect(screen.queryByTestId("slot-card-bg_polluted_main")).not.toBeInTheDocument();

    const slotCard = screen.getByTestId("slot-card-char_Alice_normal");
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate" }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/demo/generation/characters/assets/char_Alice_normal/generate");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/generation/backgrounds/"))).toBe(false);
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
    await user.click(within(slotCard).getByRole("button", { name: "Edit Prompt" }));
    const dialog = screen.getByRole("dialog", { name: "Edit asset prompt" });
    const promptBox = within(dialog).getByLabelText("Alice normal prompt");
    await user.clear(promptBox);
    await user.type(promptBox, "replacement accepted sprite prompt");
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await user.click(within(slotCard).getByRole("button", { name: "Regenerate accepted" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/demo/generation/characters/assets/char_Alice_normal/generate",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "replacement accepted sprite prompt", replace: true }),
      })
    );
    expect(loadGenerationState).toHaveBeenCalledWith("demo");
  });
});
