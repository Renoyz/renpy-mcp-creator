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
    assetId: string,
    prompt: string,
    replace = false,
    description?: string,
  ) => {
    const response = await fetch(
      `/api/projects/${encodeURIComponent(projectName)}/generation/characters/assets/${encodeURIComponent(assetId)}/generate`,
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
        ? `/api/projects/${encodeURIComponent(projectName)}/generation/characters/assets/${encodeURIComponent(target)}/upload`
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

  const assetRow = (slot: AssetSlot) => {
    const prompt = currentPrompt(slot);
    const promptForPayload = promptPayloadValue(slot);
    const descriptionForPayload = descriptionPayloadValue(slot);
    const isAccepted = slot.status === "accepted";
    const canGenerateSlot =
      busyAction === null && (slot.kind === "character_sprite" ? canUploadManualCharacter : canUploadManualBackground);
    const isCharacter = slot.kind === "character_sprite";
    const acceptDisabled =
      busyAction !== null ||
      !(slot.status === "uploaded" || slot.status === "generated") ||
      (isCharacter ? !canAcceptCharacter : !canAcceptBackground) ||
      (isCharacter && slot.renderable === false && slot.placeholder);
    const validationMessage = prettyValidation(slot);
    return (
      <div
        key={slot.asset_id}
        data-testid={`slot-card-${slot.asset_id}`}
      >
      <div
        role="row"
        data-testid={`asset-row-${slot.asset_id}`}
        className="grid gap-3 border-b border-gray-100 p-3 last:border-b-0 lg:grid-cols-[112px_minmax(220px,1.2fr)_minmax(280px,1fr)_140px_150px]"
      >
        <div role="cell">
          {slot.preview_url ? (
            <img
              src={slot.preview_url}
              alt={`${slot.display_name || slot.target} ${slot.variant}`}
              className={`h-24 w-24 rounded border bg-gray-50 ${isCharacter ? "object-contain" : "object-cover"}`}
            />
          ) : (
            <div className="flex h-24 w-24 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 text-xs text-gray-400">
              No image
            </div>
          )}
        </div>
        <div role="cell" className="min-w-0 text-sm">
          <div className="font-medium text-gray-900">
            {slot.display_name || slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
          </div>
          <div className="mt-1 text-xs text-gray-500">Source: {slot.source ?? "none"}</div>
          {slot.character_source ? <div className="text-xs text-gray-500">Design source: {slot.character_source}</div> : null}
          {slot.status === "accepted" ? (
            <span className="mt-2 inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2 py-1 text-xs text-green-700">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Accepted
            </span>
          ) : (
            <span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusChipClass(slot.status)}`}>
              {slot.status}
            </span>
          )}
          {slot.role ? <p className="mt-2 text-xs text-gray-700"><span className="font-medium">Role:</span> {slot.role}</p> : null}
          {slot.appearance ? (
            <p className="mt-1 line-clamp-3 text-xs text-gray-700"><span className="font-medium">Appearance:</span> {slot.appearance}</p>
          ) : null}
          {!isCharacter && slot.description ? (
            <p className="mt-2 line-clamp-3 text-xs text-gray-700"><span className="font-medium">Description:</span> {slot.description}</p>
          ) : null}
          {validationMessage ? (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              {isCharacter && slot.renderable === false ? (
                <div className="mb-1 flex items-start gap-1">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
                  <span>No transparent background.</span>
                </div>
              ) : null}
              <p>{validationMessage}</p>
            </div>
          ) : null}
          {slot.placeholder && <div className="mt-2 text-xs text-gray-500">Placeholder slot</div>}
          {slot.status !== "accepted" ? (
            <button
              type="button"
              onClick={() =>
                void withBusy(`accept-${slot.asset_id}`, async () =>
                  isCharacter ? acceptSlot("character_sprite", slot, !slot.renderable) : acceptSlot("background", slot)
                )
              }
              disabled={acceptDisabled}
              className="mt-2 rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busyAction === `accept-${slot.asset_id}` ? "Accepting..." : isCharacter && slot.renderable === false ? "Accept as non-renderable" : "Accept"}
            </button>
          ) : null}
        </div>
        <div role="cell">
          {slot.kind === "background" ? (
            <label className="block text-xs font-medium text-gray-700">
              Description
              <textarea
                aria-label={`${slot.target} ${slot.variant} description`}
                className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                rows={2}
                value={slotDescriptions[slot.asset_id] ?? slot.description ?? ""}
                placeholder={descriptionPlaceholder(slot.description)}
                onChange={(event) => {
                  updateSlotDescription(slot, event.target.value);
                }}
              />
            </label>
          ) : null}
          <label className={slot.kind === "background" ? "mt-2 block text-xs font-medium text-gray-700" : "block text-xs font-medium text-gray-700"}>
            Prompt
            <textarea
              aria-label={`${slot.target} ${slot.variant} prompt`}
              className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
              rows={4}
              value={prompt}
              placeholder={slot.generation_prompt || slot.prompt || promptPlaceholder(slot.kind, slot.target, slot.variant)}
              onChange={(event) => {
                updateSlotPrompt(slot, event.target.value);
              }}
            />
          </label>
        </div>
        <div role="cell">
          <button
            type="button"
            onClick={() =>
              void withBusy(`generate-${slot.asset_id}`, async () => {
                if (slot.kind === "character_sprite") {
                  await generateCharacterSlot(slot.asset_id, promptForPayload, isAccepted, descriptionForPayload);
                } else {
                  await generateBackgroundSlot(slot.target, slot.variant, promptForPayload, isAccepted, descriptionForPayload);
                }
              })
            }
            disabled={!canGenerateSlot || busyAction === `generate-${slot.asset_id}`}
            className="w-full rounded-md bg-gray-900 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {slot.status === "empty" ? "Generate with AI" : isAccepted ? "Regenerate accepted" : "Regenerate"}
          </button>
          {isAccepted ? <p className="mt-2 text-xs text-amber-700">Requires re-accept after regeneration.</p> : null}
        </div>
        <div role="cell">
          <label className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium">
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
                  await uploadForSlot(
                    slot.kind,
                    slot.kind === "character_sprite" ? slot.asset_id : slot.target,
                    slot.variant,
                    file,
                    descriptionForPayload
                  );
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
            <div role="table" className="mt-3 overflow-hidden rounded-md border border-gray-200">
              <div role="row" className="hidden bg-gray-50 px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 lg:grid lg:grid-cols-[112px_minmax(220px,1.2fr)_minmax(280px,1fr)_140px_150px]">
                <div role="columnheader">Thumbnail</div>
                <div role="columnheader">Description</div>
                <div role="columnheader">Prompt</div>
                <div role="columnheader">AI Generate</div>
                <div role="columnheader">Upload Image</div>
              </div>
              {characters.map((slot) => assetRow(slot))}
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
            <div role="table" className="mt-3 overflow-hidden rounded-md border border-gray-200">
              <div role="row" className="hidden bg-gray-50 px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 lg:grid lg:grid-cols-[112px_minmax(220px,1.2fr)_minmax(280px,1fr)_140px_150px]">
                <div role="columnheader">Thumbnail</div>
                <div role="columnheader">Description</div>
                <div role="columnheader">Prompt</div>
                <div role="columnheader">AI Generate</div>
                <div role="columnheader">Upload Image</div>
              </div>
              {backgrounds.map((slot) => assetRow(slot))}
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
