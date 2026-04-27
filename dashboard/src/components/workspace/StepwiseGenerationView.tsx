import { useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Play, RefreshCw, Upload } from "lucide-react";
import type { AssetSlot, GenerationState } from "@/context/ProjectContext";

interface Props {
  projectName: string;
  generationState: GenerationState | null;
  loadGenerationState: (name: string) => Promise<void>;
}

function statusChipClass(status: AssetSlot["status"]) {
  if (status === "accepted") return "bg-green-100 text-green-700";
  if (status === "failed") return "bg-red-100 text-red-700";
  if (status === "uploaded") return "bg-blue-100 text-blue-700";
  return "bg-gray-100 text-gray-700";
}

function buildDefaultPrompt(kind: AssetSlot["kind"], target: string, variant: string) {
  const safeTarget = target || "target";
  const safeVariant = variant || "main";
  return kind === "character_sprite"
    ? `Generate a ${safeVariant} character sprite for ${safeTarget}`
    : `Generate a background for ${safeTarget} (${safeVariant})`;
}

function promptPlaceholder(kind: AssetSlot["kind"], target: string, variant: string) {
  return `${buildDefaultPrompt(kind, target, variant)}. Leave blank to use the backend default prompt.`;
}

function descriptionPlaceholder(description?: string | null) {
  return description?.trim().length ? description : "Describe the scene background composition and mood.";
}

function prettyValidation(slot: AssetSlot): string | null {
  if (!slot.validation) return null;
  const base = `${slot.validation.width}x${slot.validation.height} (${slot.validation.reason})`;
  if (slot.kind === "background" && !slot.validation.ok) {
    return `Image is usable, but it is not close to 16:9 and may be cropped in preview: ${base}`;
  }
  if (slot.kind === "character_sprite" && !slot.renderable) {
    return `This sprite has no transparent background: ${base}`;
  }
  if (!slot.validation.ok) {
    return `Validation warning: ${base}`;
  }
  return null;
}

type SlotPromptMap = Record<string, string>;
type SlotDescriptionMap = Record<string, string>;

type GenerationRequestPayload = {
  prompt: string;
  replace: boolean;
  description?: string;
};

export function StepwiseGenerationView({ projectName, generationState, loadGenerationState }: Props) {
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [previewScript, setPreviewScript] = useState<string>("");
  const [previewScriptFiles, setPreviewScriptFiles] = useState<string[]>([]);

  const [slotPrompts, setSlotPrompts] = useState<SlotPromptMap>({});
  const [slotDescriptions, setSlotDescriptions] = useState<SlotDescriptionMap>({});

  const characters = useMemo(() => (generationState ? Object.values(generationState.character_assets) : []), [generationState]);
  const backgrounds = useMemo(() => (generationState ? Object.values(generationState.background_assets) : []), [generationState]);

  const activeState = generationState?.state ?? "idle";

  const clearMessages = () => {
    setActionMessage("");
    setActionError("");
  };

  const withBusy = async (actionId: string, action: () => Promise<void>) => {
    setBusyAction(actionId);
    clearMessages();
    try {
      await action();
      await loadGenerationState(projectName);
      setActionMessage("Operation completed.");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Operation failed";
      setActionError(msg);
    } finally {
      setBusyAction(null);
    }
  };

  const parseError = async (response: Response) => {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${response.status})`);
  };

  const buildGenerationPayload = ({ prompt, replace, description }: GenerationRequestPayload) => {
    const requestBody: GenerationRequestPayload = { prompt, replace };
    if (description !== undefined && description !== null) {
      requestBody.description = description;
    }
    return requestBody;
  };

  const startCharacters = () =>
    withBusy("start-characters", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/characters/start`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
    });

  const startBackgrounds = () =>
    withBusy("start-backgrounds", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/backgrounds/start`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
    });

  const generateCharacterSlot = async (
    characterId: string,
    variant: string,
    prompt: string,
    replace = false,
    description?: string,
  ) => {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(projectName)}/generation/characters/${encodeURIComponent(characterId)}/${encodeURIComponent(
        variant
      )}/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildGenerationPayload({ prompt, replace, description })),
      }
    );
    if (!response.ok) {
      await parseError(response);
    }
  };

  const generateBackgroundSlot = async (
    locationId: string,
    variant: string,
    prompt: string,
    replace = false,
    description?: string,
  ) => {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(projectName)}/generation/backgrounds/${encodeURIComponent(locationId)}/${encodeURIComponent(
        variant
      )}/generate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildGenerationPayload({ prompt, replace, description })),
      }
    );
    if (!response.ok) {
      await parseError(response);
    }
  };

  const uploadForSlot = async (
    kind: "character_sprite" | "background",
    target: string,
    variant: string,
    file: File,
    description?: string,
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    if (kind === "background" && description !== undefined) {
      formData.append("description", description);
    }
    const response = await fetch(
      kind === "character_sprite"
        ? `/api/projects/${encodeURIComponent(projectName)}/generation/characters/${encodeURIComponent(target)}/${encodeURIComponent(
            variant
          )}/upload`
        : `/api/projects/${encodeURIComponent(projectName)}/generation/backgrounds/${encodeURIComponent(target)}/${encodeURIComponent(
            variant
          )}/upload`,
      { method: "POST", body: formData }
    );
    if (!response.ok) {
      await parseError(response);
    }
  };

  const acceptSlot = async (kind: "character_sprite" | "background", slot: AssetSlot, allowNonRenderable = false) => {
    const endpoint =
      kind === "character_sprite"
        ? `/api/projects/${encodeURIComponent(projectName)}/generation/characters/${encodeURIComponent(slot.asset_id)}/accept`
        : `/api/projects/${encodeURIComponent(projectName)}/generation/backgrounds/${encodeURIComponent(slot.asset_id)}/accept`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: kind === "character_sprite" ? { "Content-Type": "application/json" } : undefined,
      body: kind === "character_sprite" ? JSON.stringify({ allow_non_renderable: allowNonRenderable }) : undefined,
    });
    if (!response.ok) {
      await parseError(response);
    }
  };

  const confirmCharacters = () =>
    withBusy("confirm-characters", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/characters/confirm`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
    });

  const confirmBackgrounds = () =>
    withBusy("confirm-backgrounds", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/backgrounds/confirm`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
    });

  const previewScriptAction = () =>
    withBusy("preview-script", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/script/preview`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
      const data = await response.json();
      setPreviewScriptFiles(data.script_files ?? []);
      setPreviewScript(data.script ?? "");
    });

  const commitScript = () =>
    withBusy("commit-script", async () => {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/generation/script/commit`, {
        method: "POST",
      });
      if (!response.ok) {
        await parseError(response);
      }
      setPreviewScript("");
      setPreviewScriptFiles([]);
    });

  const canUploadManualCharacter = activeState !== "script_preview" && activeState !== "committed";
  const canUploadManualBackground =
    activeState === "background_assets_draft" || activeState === "background_assets_confirmed";
  const canAcceptCharacter =
    activeState === "character_assets_draft" ||
    activeState === "character_assets_confirmed" ||
    activeState === "background_assets_draft" ||
    activeState === "background_assets_confirmed";
  const canAcceptBackground =
    activeState === "background_assets_draft" || activeState === "background_assets_confirmed";
  const canConfirmCharacters =
    activeState === "character_assets_draft" ||
    activeState === "character_assets_confirmed" ||
    activeState === "background_assets_draft" ||
    activeState === "background_assets_confirmed";
  const canConfirmBackgrounds =
    activeState === "character_assets_confirmed" ||
    activeState === "background_assets_draft" ||
    activeState === "background_assets_confirmed";
  const canPreview =
    activeState === "background_assets_confirmed" ||
    activeState === "script_preview";

  const currentPrompt = (slot: AssetSlot) => {
    return slotPrompts[slot.asset_id] ?? slot.generation_prompt ?? slot.prompt ?? "";
  };

  const promptPayloadValue = (slot: AssetSlot) => {
    return currentPrompt(slot);
  };

  const descriptionPayloadValue = (slot: AssetSlot) => {
    if (slotDescriptions[slot.asset_id] !== undefined) return slotDescriptions[slot.asset_id];
    return slot.description ?? undefined;
  };

  const updateSlotPrompt = (slot: AssetSlot, prompt: string) => {
    setSlotPrompts((previous) => ({ ...previous, [slot.asset_id]: prompt }));
  };

  const updateSlotDescription = (slot: AssetSlot, description: string) => {
    setSlotDescriptions((previous) => ({ ...previous, [slot.asset_id]: description }));
  };

  const slotActionPanel = (slot: AssetSlot) => {
    const prompt = currentPrompt(slot);
    const promptForPayload = promptPayloadValue(slot);
    const descriptionForPayload = descriptionPayloadValue(slot);
    const isAccepted = slot.status === "accepted";
    const canGenerateSlot =
      busyAction === null && (slot.kind === "character_sprite" ? canUploadManualCharacter : canUploadManualBackground);
    return (
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div className="rounded-md border border-gray-200 p-3">
          <div className="text-sm font-medium text-gray-900">Generate with AI</div>
          {slot.kind === "background" ? (
            <label className="mt-3 block text-sm">
              Description
                      <textarea
                        aria-label={`${slot.target} ${slot.variant} description`}
                        className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                        rows={3}
                        value={slotDescriptions[slot.asset_id] ?? slot.description ?? ""}
                        placeholder={descriptionPlaceholder(slot.description)}
                        onChange={(event) => {
                          updateSlotDescription(slot, event.target.value);
                        }}
                      />
            </label>
          ) : null}
          <label className="mt-3 block text-sm">
            Prompt
            <textarea
              aria-label={`${slot.target} ${slot.variant} prompt`}
              className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
              rows={3}
              value={prompt}
              placeholder={slot.generation_prompt || slot.prompt || promptPlaceholder(slot.kind, slot.target, slot.variant)}
              onChange={(event) => {
                updateSlotPrompt(slot, event.target.value);
              }}
            />
          </label>
          <div className="mt-3">
            <button
              type="button"
              onClick={() =>
                void withBusy(`generate-${slot.asset_id}`, async () => {
                  if (slot.kind === "character_sprite") {
                    await generateCharacterSlot(slot.target, slot.variant, promptForPayload, isAccepted, descriptionForPayload);
                  } else {
                    await generateBackgroundSlot(
                      slot.target,
                      slot.variant,
                      promptForPayload,
                      isAccepted,
                      descriptionForPayload
                    );
                  }
                })
              }
              disabled={!canGenerateSlot || busyAction === `generate-${slot.asset_id}`}
              className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {slot.status === "empty" ? "Generate with AI" : isAccepted ? "Regenerate accepted" : "Regenerate"}
            </button>
          </div>
          {isAccepted ? (
            <p className="mt-2 text-xs text-amber-700">
              Regenerating will replace the accepted draft and require accepting the new image again.
            </p>
          ) : null}
        </div>
        <div className="rounded-md border border-gray-200 p-3">
          <div className="text-sm font-medium text-gray-900">Upload Image</div>
          <div className="mt-3">
            <label className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium">
              <Upload className="h-4 w-4" />
              Manual Upload
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={busyAction !== null || slot.status === "accepted"}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  void withBusy(`upload-${slot.asset_id}`, async () => {
                    await uploadForSlot(slot.kind, slot.target, slot.variant, file, descriptionForPayload);
                  });
                  event.target.value = "";
                }}
                className="sr-only"
              />
            </label>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Stepwise Generation</h2>
              <p className="mt-1 text-sm text-gray-500">Current state: {activeState}</p>
              <p className="mt-1 text-xs text-gray-500">
                Manual progression: Character Assets → Scene Backgrounds → Script Preview &amp; Commit; Build is outside this tab.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadGenerationState(projectName)}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
          {actionMessage && <div className="mt-3 text-sm text-green-700">{actionMessage}</div>}
          {actionError && <div className="mt-3 text-sm text-red-700">{actionError}</div>}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Character Assets</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void startCharacters()}
                disabled={busyAction !== null}
                className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "start-characters" ? "Starting..." : "Start Characters"}
              </button>
              <button
                type="button"
                onClick={() => void confirmCharacters()}
                disabled={busyAction !== null || !canConfirmCharacters}
                style={{ display: canConfirmCharacters ? "inline-block" : "none" }}
                className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "confirm-characters" ? "Confirming..." : "Confirm Characters"}
              </button>
            </div>
          </div>

          {characters.length === 0 ? (
            <div className="mt-4 rounded-md border border-dashed border-gray-300 bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-800">No derived character slots available.</p>
              <p className="mt-1 text-xs text-gray-500">
                Confirm or refresh the frozen blueprint so character designs can be listed here before asset generation.
              </p>
            </div>
          ) : (
            <div className="mt-3 grid gap-3">
              {characters.map((slot) => (
                <div
                  key={slot.asset_id}
                  data-testid={`slot-card-${slot.asset_id}`}
                  className="rounded-md border border-gray-200 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {slot.display_name || slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
                      </div>
                      <div className="text-xs text-gray-500">Source: {slot.source ?? "none"}</div>
                      {slot.character_source ? (
                        <div className="text-xs text-gray-500">Design source: {slot.character_source}</div>
                      ) : null}
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusChipClass(slot.status)}`}>
                      {slot.status}
                    </span>
                  </div>
                  {(slot.role || slot.appearance) && (
                    <div className="mt-3 rounded-md border border-gray-100 bg-gray-50 p-3 text-xs text-gray-700">
                      {slot.role ? <p><span className="font-medium text-gray-900">Role:</span> {slot.role}</p> : null}
                      {slot.appearance ? (
                        <p className="mt-1"><span className="font-medium text-gray-900">Appearance:</span> {slot.appearance}</p>
                      ) : null}
                    </div>
                  )}
                  {slot.preview_url && (
                    <img
                      src={slot.preview_url}
                      alt={`${slot.display_name || slot.target} ${slot.variant}`}
                      className="mt-3 h-28 w-auto rounded border object-contain"
                    />
                  )}
                  {prettyValidation(slot) && (
                    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                      {slot.kind === "character_sprite" && slot.renderable === false && (
                        <div className="mb-1 flex items-start gap-2">
                          <AlertCircle className="mt-0.5 h-4 w-4" />
                          <span>
                            This sprite has no transparent background. Choose background removal, re-upload, or keep it as a non-renderable
                            draft.
                          </span>
                        </div>
                      )}
                      <p>{prettyValidation(slot)}</p>
                    </div>
                  )}
                  {slotActionPanel(slot)}
                  <div className="mt-3 flex items-center gap-2">
                    {slot.status === "accepted" ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs text-green-700">
                        <CheckCircle2 className="h-4 w-4" />
                        Accepted
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          void withBusy(`accept-${slot.asset_id}`, async () => acceptSlot("character_sprite", slot, !slot.renderable))
                        }
                        disabled={
                          busyAction !== null ||
                          !(slot.status === "uploaded" || slot.status === "generated") ||
                          !canAcceptCharacter ||
                          (slot.renderable === false && slot.placeholder)
                        }
                        className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {busyAction === `accept-${slot.asset_id}` ? "Accepting..." : slot.renderable === false ? "Accept as non-renderable" : "Accept"}
                      </button>
                    )}
                  </div>
                  {slot.placeholder && <div className="mt-2 text-xs text-gray-500">Placeholder slot</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Scene Backgrounds</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void startBackgrounds()}
                disabled={busyAction !== null}
                className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "start-backgrounds" ? "Starting..." : "Start Backgrounds"}
              </button>
              <button
                type="button"
                onClick={() => void confirmBackgrounds()}
                disabled={busyAction !== null || !canConfirmBackgrounds}
                style={{ display: canConfirmBackgrounds ? "inline-block" : "none" }}
                className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "confirm-backgrounds" ? "Confirming..." : "Confirm Backgrounds"}
              </button>
            </div>
          </div>

          {backgrounds.length === 0 ? (
            <div className="mt-4 rounded-md border border-dashed border-gray-300 bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-800">No derived scene background slots available.</p>
              <p className="mt-1 text-xs text-gray-500">
                Generate scene packages from the frozen blueprint so each scene can expose an AI generation/upload entry.
              </p>
            </div>
          ) : (
            <div className="mt-3 grid gap-3">
              {backgrounds.map((slot) => (
                <div
                  key={slot.asset_id}
                  data-testid={`slot-card-${slot.asset_id}`}
                  className="rounded-md border border-gray-200 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
                      </div>
                      <div className="text-xs text-gray-500">Source: {slot.source ?? "none"}</div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusChipClass(slot.status)}`}>
                      {slot.status}
                    </span>
                  </div>
                  {slot.preview_url && (
                    <img
                      src={slot.preview_url}
                      alt={`${slot.target} ${slot.variant}`}
                      className="mt-3 h-28 w-auto rounded border object-cover"
                    />
                  )}
                  {prettyValidation(slot) && (
                    <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
                      <p>{prettyValidation(slot)}</p>
                    </div>
                  )}
                  {slotActionPanel(slot)}
                  <div className="mt-3 flex items-center gap-2">
                    {slot.status === "accepted" ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs text-green-700">
                        <CheckCircle2 className="h-4 w-4" />
                        Accepted
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void withBusy(`accept-${slot.asset_id}`, async () => acceptSlot("background", slot))}
                        disabled={
                          busyAction !== null || !(slot.status === "uploaded" || slot.status === "generated") || !canAcceptBackground
                        }
                        className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {busyAction === `accept-${slot.asset_id}` ? "Accepting..." : "Accept"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Script Preview &amp; Commit</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void previewScriptAction()}
                disabled={busyAction !== null || !canPreview}
                className="inline-flex items-center gap-1 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" />
                {busyAction === "preview-script" ? "Generating..." : "Generate Preview Script"}
              </button>
              <button
                type="button"
                onClick={() => void commitScript()}
                disabled={busyAction !== null || activeState !== "script_preview"}
                className="inline-flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "commit-script" ? "Committing..." : "Commit Preview Script"}
              </button>
            </div>
          </div>
          {generationState?.script_preview?.staging_path && (
            <p className="mt-2 text-xs text-gray-500">Last staging script: {generationState.script_preview.staging_path}</p>
          )}
          {previewScriptFiles.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">Script files: {previewScriptFiles.join(", ")}</p>
          )}
          {previewScript && (
            <pre className="mt-3 max-h-72 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800">
              {previewScript}
            </pre>
          )}
          {generationState?.script_preview?.chapter_ids && generationState.script_preview.chapter_ids.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">Chapter IDs: {generationState.script_preview.chapter_ids.join(", ")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
