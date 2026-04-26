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

export function StepwiseGenerationView({ projectName, generationState, loadGenerationState }: Props) {
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [previewScript, setPreviewScript] = useState<string>("");
  const [previewScriptFiles, setPreviewScriptFiles] = useState<string[]>([]);
  const [manualCharacterTarget, setManualCharacterTarget] = useState("");
  const [manualCharacterVariant, setManualCharacterVariant] = useState("normal");
  const [manualBackgroundTarget, setManualBackgroundTarget] = useState("");
  const [manualBackgroundVariant, setManualBackgroundVariant] = useState("main");

  const characters = useMemo(() => {
    if (!generationState) return [];
    return Object.values(generationState.character_assets);
  }, [generationState]);

  const backgrounds = useMemo(() => {
    if (!generationState) return [];
    return Object.values(generationState.background_assets);
  }, [generationState]);

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

  const uploadForSlot = async (kind: "character_sprite" | "background", target: string, variant: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
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
  const canUploadManualBackground = activeState !== "script_preview" && activeState !== "committed";
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
  const canPreview = activeState === "character_assets_confirmed" || activeState === "background_assets_confirmed" || activeState === "script_preview";

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Stepwise Generation</h2>
              <p className="mt-1 text-sm text-gray-500">Current state: {activeState}</p>
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
              <p className="text-sm text-gray-700">No generated character slots yet.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-sm">
                  Target
                  <input
                    type="text"
                    value={manualCharacterTarget}
                    onChange={(event) => setManualCharacterTarget(event.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                    placeholder="character name/id"
                  />
                </label>
                <label className="text-sm">
                  Variant
                  <input
                    type="text"
                    value={manualCharacterVariant}
                    onChange={(event) => setManualCharacterVariant(event.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                    placeholder="normal"
                  />
                </label>
              </div>
              <div className="mt-3">
                <label className="inline-flex items-center gap-2 text-sm font-medium text-blue-700">
                  <Upload className="h-4 w-4" />
                  <span>Upload character image (fallback)</span>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={!canUploadManualCharacter || busyAction !== null || !manualCharacterTarget}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;
                      void withBusy("upload-manual-character", async () => {
                        await uploadForSlot(
                          "character_sprite",
                          manualCharacterTarget,
                          manualCharacterVariant || "normal",
                          file
                        );
                        setManualCharacterTarget("");
                        setManualCharacterVariant("normal");
                      });
                      event.target.value = "";
                    }}
                    className="sr-only"
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className="mt-3 grid gap-3">
              {characters.map((slot) => (
                <div key={slot.asset_id} className="rounded-md border border-gray-200 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        {slot.source ? `Source: ${slot.source}` : "Source: none"}
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusChipClass(slot.status)}`}>
                      {slot.status}
                    </span>
                  </div>
                  {slot.preview_url && (
                    <img
                      src={slot.preview_url}
                      alt={`${slot.target} ${slot.variant}`}
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
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <label className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm">
                      <Upload className="h-4 w-4" />
                      Upload
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        disabled={busyAction !== null || !canUploadManualCharacter}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          void withBusy(`upload-${slot.asset_id}`, async () => {
                            await uploadForSlot("character_sprite", slot.target, slot.variant, file);
                          });
                          event.target.value = "";
                        }}
                        className="sr-only"
                      />
                    </label>
                    {slot.status === "accepted" ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs text-green-700">
                        <CheckCircle2 className="h-4 w-4" />
                        Accepted
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          void withBusy(`accept-${slot.asset_id}`, async () =>
                            acceptSlot(
                              "character_sprite",
                              slot,
                              slot.status !== "accepted" && !slot.renderable
                            )
                          )
                        }
                        disabled={
                          busyAction !== null ||
                          !(slot.status === "uploaded" || slot.status === "generated") ||
                          !canAcceptCharacter ||
                          (slot.renderable === false && slot.placeholder)
                        }
                        className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {busyAction === `accept-${slot.asset_id}`
                          ? "Accepting..."
                          : slot.renderable === false
                          ? "Accept as non-renderable"
                          : "Accept"}
                      </button>
                    )}
                  </div>
                  {slot.placeholder && (
                    <div className="mt-2 text-xs text-gray-500">Placeholder slot</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">Background Assets</h3>
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
              <p className="text-sm text-gray-700">No generated background slots yet.</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="text-sm">
                  Target
                  <input
                    type="text"
                    value={manualBackgroundTarget}
                    onChange={(event) => setManualBackgroundTarget(event.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                    placeholder="scene id"
                  />
                </label>
                <label className="text-sm">
                  Variant
                  <input
                    type="text"
                    value={manualBackgroundVariant}
                    onChange={(event) => setManualBackgroundVariant(event.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-2 py-1 text-sm"
                    placeholder="main"
                  />
                </label>
              </div>
              <div className="mt-3">
                <label className="inline-flex items-center gap-2 text-sm font-medium text-blue-700">
                  <Upload className="h-4 w-4" />
                  <span>Upload background image (fallback)</span>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={!canUploadManualBackground || busyAction !== null || !manualBackgroundTarget}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;
                      void withBusy("upload-manual-background", async () => {
                        await uploadForSlot(
                          "background",
                          manualBackgroundTarget,
                          manualBackgroundVariant || "main",
                          file
                        );
                        setManualBackgroundTarget("");
                        setManualBackgroundVariant("main");
                      });
                      event.target.value = "";
                    }}
                    className="sr-only"
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className="mt-3 grid gap-3">
              {backgrounds.map((slot) => (
                <div key={slot.asset_id} className="rounded-md border border-gray-200 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        {slot.source ? `Source: ${slot.source}` : "Source: none"}
                      </div>
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
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <label className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-1.5 text-sm">
                      <Upload className="h-4 w-4" />
                      Upload
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        disabled={busyAction !== null || !canUploadManualBackground}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          void withBusy(`upload-${slot.asset_id}`, async () => {
                            await uploadForSlot("background", slot.target, slot.variant, file);
                          });
                          event.target.value = "";
                        }}
                        className="sr-only"
                      />
                    </label>
                    {slot.status === "accepted" ? (
                      <span className="inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-3 py-1.5 text-xs text-green-700">
                        <CheckCircle2 className="h-4 w-4" />
                        Accepted
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          void withBusy(`accept-${slot.asset_id}`, async () => acceptSlot("background", slot))
                        }
                        disabled={
                          busyAction !== null ||
                          !(slot.status === "uploaded" || slot.status === "generated") ||
                          !canAcceptBackground
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
            <h3 className="text-sm font-semibold text-gray-900">Script Preview & Commit</h3>
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
            <p className="mt-2 text-xs text-gray-500">
              Script files: {previewScriptFiles.join(", ")}
            </p>
          )}
          {previewScript && (
            <pre className="mt-3 max-h-72 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800">
              {previewScript}
            </pre>
          )}
          {generationState?.script_preview?.chapter_ids && generationState.script_preview.chapter_ids.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">
              Chapter IDs: {generationState.script_preview.chapter_ids.join(", ")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
