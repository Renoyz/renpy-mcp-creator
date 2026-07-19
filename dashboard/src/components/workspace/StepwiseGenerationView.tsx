import { useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Play, RefreshCw, Upload } from "lucide-react";
import type { AssetSlot, GenerationState } from "@/context/ProjectContext";
import { GenerationFlowPanel } from "./GenerationFlowPanel";

interface Props {
  projectName: string;
  generationState: GenerationState | null;
  loadGenerationState: (name: string) => Promise<void>;
  generationAllowed?: boolean;
  blockedReason?: string | null;
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
  return `${buildDefaultPrompt(kind, target, variant)}。留空则使用后端默认提示词。`;
}

function descriptionPlaceholder(description?: string | null) {
  return description?.trim().length ? description : "描述场景背景的构图与氛围。";
}

function prettyValidation(slot: AssetSlot): string | null {
  if (!slot.validation) return null;
  const base = `${slot.validation.width}x${slot.validation.height} (${slot.validation.reason})`;
  if (slot.kind === "background" && !slot.validation.ok) {
    return `图片可用，但比例不接近 16:9，预览中可能被裁剪：${base}`;
  }
  if (slot.kind === "character_sprite" && !slot.renderable) {
    return `该立绘没有透明背景：${base}`;
  }
  if (!slot.validation.ok) {
    return `校验警告：${base}`;
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

export function StepwiseGenerationView({ projectName, generationState, loadGenerationState, generationAllowed = true, blockedReason = null }: Props) {
  const [actionMessage, setActionMessage] = useState<string>("");
  const [actionError, setActionError] = useState<string>("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [previewScript, setPreviewScript] = useState<string>("");
  const [previewScriptFiles, setPreviewScriptFiles] = useState<string[]>([]);

  const [slotPrompts, setSlotPrompts] = useState<SlotPromptMap>({});
  const [slotDescriptions, setSlotDescriptions] = useState<SlotDescriptionMap>({});
  const [promptEditorSlotId, setPromptEditorSlotId] = useState<string | null>(null);

  const characters = useMemo(
    () => (generationState ? Object.values(generationState.character_assets).filter((slot) => slot.kind === "character_sprite") : []),
    [generationState]
  );
  const backgrounds = useMemo(
    () => (generationState ? Object.values(generationState.background_assets).filter((slot) => slot.kind === "background") : []),
    [generationState]
  );
  const sceneGeneration = generationState?.scene_generation ?? null;
  const allSlots = useMemo(() => [...characters, ...backgrounds], [characters, backgrounds]);
  const promptEditorSlot = useMemo(
    () => allSlots.find((slot) => slot.asset_id === promptEditorSlotId) ?? null,
    [allSlots, promptEditorSlotId]
  );

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
      setActionMessage("操作已完成。");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "操作失败";
      setActionError(msg);
    } finally {
      setBusyAction(null);
    }
  };

  const parseError = async (response: Response) => {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败 (${response.status})`);
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

  const generateScenePackages = () =>
    withBusy("scene-packages-all", async () => {
      let complete = false;
      let attempts = 0;
      const maxAttempts = Math.max(sceneGeneration?.total_count ?? 1, 1) + 2;
      while (!complete && attempts < maxAttempts) {
        attempts += 1;
        const response = await fetch(`/api/projects/${encodeURIComponent(projectName)}/scene-packages/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        if (!response.ok) {
          await parseError(response);
        }
        const data = await response.json().catch(() => ({}));
        complete = data.complete === true || data.scene_generation?.status === "complete";
        const hasInFlightChapter =
          Array.isArray(data.scene_generation?.chapters) &&
          data.scene_generation.chapters.some((chapter: { status?: string }) => chapter.status === "generating");
        await loadGenerationState(projectName);
        if (hasInFlightChapter) {
          return;
        }
        if (!data.scene_generation && data.complete !== false) {
          complete = true;
        }
      }
      if (!complete) {
        throw new Error("场景包生成未全部完成。");
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
  const canGenerateScenePackages =
    generationAllowed &&
    busyAction === null &&
    sceneGeneration !== null &&
    sceneGeneration.status !== "complete" &&
    sceneGeneration.total_count > 0;

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
      generationAllowed && busyAction === null && (slot.kind === "character_sprite" ? canUploadManualCharacter : canUploadManualBackground);
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
        className="grid min-w-[980px] gap-3 border-b border-gray-100 p-3 last:border-b-0 xl:grid-cols-[96px_minmax(240px,1.1fr)_minmax(260px,1fr)_220px]"
      >
        <div role="cell" className="min-w-0">
          {slot.preview_url ? (
            <img
              src={slot.preview_url}
              alt={`${slot.display_name || slot.target} ${slot.variant}`}
              className={`h-24 w-24 rounded border bg-gray-50 ${isCharacter ? "object-contain" : "object-cover"}`}
            />
          ) : (
            <div className="flex h-24 w-24 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50 text-xs text-gray-400">
              暂无图片
            </div>
          )}
        </div>
        <div role="cell" className="min-w-0 text-sm">
          <div className="font-medium text-gray-900">
            {slot.display_name || slot.target} <span className="text-xs text-gray-500">({slot.variant})</span>
          </div>
          <div className="mt-1 text-xs text-gray-500">来源：{slot.source ?? "无"}</div>
          {slot.character_source ? <div className="text-xs text-gray-500">设计来源：{slot.character_source}</div> : null}
          {slot.status === "accepted" ? (
            <span className="mt-2 inline-flex items-center gap-1 rounded-md border border-green-200 bg-green-50 px-2 py-1 text-xs text-green-700">
              <CheckCircle2 className="h-3.5 w-3.5" />
              已验收
            </span>
          ) : (
            <span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusChipClass(slot.status)}`}>
              {slot.status}
            </span>
          )}
          {slot.role ? <p className="mt-2 text-xs text-gray-700"><span className="font-medium">定位：</span> {slot.role}</p> : null}
          {slot.appearance ? (
            <p className="mt-1 line-clamp-3 text-xs text-gray-700"><span className="font-medium">外观：</span> {slot.appearance}</p>
          ) : null}
          {!isCharacter && slot.description ? (
            <p className="mt-2 line-clamp-3 text-xs text-gray-700"><span className="font-medium">描述：</span> {slot.description}</p>
          ) : null}
          {validationMessage ? (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
              {isCharacter && slot.renderable === false ? (
                <div className="mb-1 flex items-start gap-1">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5" />
                  <span>无透明背景。</span>
                </div>
              ) : null}
              <p>{validationMessage}</p>
            </div>
          ) : null}
          {slot.placeholder && <div className="mt-2 text-xs text-gray-500">占位槽位</div>}
          {slot.kind === "background" ? (
            <label className="mt-3 block text-xs font-medium text-gray-700">
              可编辑描述
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
              {busyAction === `accept-${slot.asset_id}` ? "验收中..." : isCharacter && slot.renderable === false ? "按不可渲染验收" : "验收"}
            </button>
          ) : null}
        </div>
        <div role="cell">
          <div className="text-xs font-medium text-gray-700">
            提示词
          </div>
          <p className="mt-1 line-clamp-3 whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-2 text-xs text-gray-700">
            {prompt || slot.generation_prompt || slot.prompt || promptPlaceholder(slot.kind, slot.target, slot.variant)}
          </p>
          <button
            type="button"
            onClick={() => setPromptEditorSlotId(slot.asset_id)}
            className="mt-2 rounded-md border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
          >
            编辑提示词
          </button>
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
            className="w-full whitespace-normal rounded-md bg-gray-900 px-2 py-2 text-xs font-medium leading-snug text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {slot.status === "empty" ? "使用 AI 生成" : isAccepted ? "重新生成（已验收）" : "重新生成"}
          </button>
          {isAccepted ? <p className="mt-2 text-xs text-amber-700">重新生成后需要重新验收。</p> : null}
          <label className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-md border border-gray-300 px-2 py-2 text-xs font-medium">
            <Upload className="h-4 w-4" />
            手动上传
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={busyAction !== null || !generationAllowed || slot.status === "accepted"}
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
      <div className="mx-auto max-w-none space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">分步生成</h2>
              <p className="mt-1 text-sm text-gray-500">当前状态：{activeState}</p>
              <p className="mt-1 text-xs text-gray-500">
                手动流程：角色素材 -&gt; 场景背景 -&gt; 脚本预览与提交；构建在本页之外进行。
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadGenerationState(projectName)}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </button>
          </div>
          {actionMessage && <div className="mt-3 text-sm text-green-700">{actionMessage}</div>}
          {actionError && <div className="mt-3 text-sm text-red-700">{actionError}</div>}
          {!generationAllowed && blockedReason && (
            <div data-testid="generation-blocked-reason" className="mt-3 text-sm text-amber-700">{blockedReason}</div>
          )}
        </div>

        <GenerationFlowPanel generationState={generationState} busyAction={busyAction} />

        {sceneGeneration && (
          <div data-testid="scene-package-progress-panel" className="rounded-lg border border-gray-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">场景包进度</h3>
                <p className="mt-1 text-sm text-gray-500">
                  {sceneGeneration.completed_count} / {sceneGeneration.total_count} 个章节已完成
                  {sceneGeneration.current_chapter_id ? ` · 当前：${sceneGeneration.current_chapter_id}` : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void generateScenePackages()}
                disabled={!canGenerateScenePackages || busyAction === "scene-packages-all"}
                className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "scene-packages-all" ? "生成中..." : "生成场景包"}
              </button>
            </div>
            {sceneGeneration.chapters.length > 0 && (
              <div className="mt-3 overflow-hidden rounded-md border border-gray-200">
                {sceneGeneration.chapters.map((chapter) => (
                  <div
                    key={chapter.chapter_id}
                    className="grid gap-3 border-b border-gray-100 px-3 py-2 text-sm last:border-b-0 md:grid-cols-[80px_minmax(180px,1fr)_120px_100px]"
                  >
                    <div className="text-gray-500">#{chapter.chapter_order}</div>
                    <div className="min-w-0">
                      <div className="truncate font-medium text-gray-900">{chapter.chapter_name}</div>
                      <div className="text-xs text-gray-500">{chapter.chapter_id}</div>
                      {chapter.error ? <div className="mt-1 text-xs text-red-700">{chapter.error}</div> : null}
                    </div>
                    <div>
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          chapter.status === "complete"
                            ? "bg-green-100 text-green-700"
                            : chapter.status === "failed"
                            ? "bg-red-100 text-red-700"
                            : chapter.status === "generating"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {chapter.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500">{chapter.scene_count} 个场景</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div data-testid="character-assets-section" className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">角色素材</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void startCharacters()}
                disabled={busyAction !== null || !generationAllowed}
                className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "start-characters" ? "启动中..." : "开始角色素材"}
              </button>
              <button
                type="button"
                onClick={() => void confirmCharacters()}
                disabled={busyAction !== null || !canConfirmCharacters}
                style={{ display: canConfirmCharacters ? "inline-block" : "none" }}
                className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "confirm-characters" ? "确认中..." : "确认角色素材"}
              </button>
            </div>
          </div>

          {characters.length === 0 ? (
            <div className="mt-4 rounded-md border border-dashed border-gray-300 bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-800">暂无派生的角色槽位。</p>
              <p className="mt-1 text-xs text-gray-500">
                请确认或刷新已冻结的蓝图，以便在素材生成前列出角色设计。
              </p>
            </div>
          ) : (
            <div role="table" className="mt-3 overflow-x-auto rounded-md border border-gray-200">
              <div role="row" className="hidden min-w-[980px] bg-gray-50 px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 xl:grid xl:grid-cols-[96px_minmax(240px,1.1fr)_minmax(260px,1fr)_220px]">
                <div role="columnheader">缩略图</div>
                <div role="columnheader">描述</div>
                <div role="columnheader">提示词</div>
                <div role="columnheader">操作</div>
              </div>
              {characters.map((slot) => assetRow(slot))}
            </div>
          )}
        </div>

        <div data-testid="scene-backgrounds-section" className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">场景背景</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void startBackgrounds()}
                disabled={busyAction !== null || !generationAllowed}
                className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "start-backgrounds" ? "启动中..." : "开始场景背景"}
              </button>
              <button
                type="button"
                onClick={() => void confirmBackgrounds()}
                disabled={busyAction !== null || !canConfirmBackgrounds}
                style={{ display: canConfirmBackgrounds ? "inline-block" : "none" }}
                className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "confirm-backgrounds" ? "确认中..." : "确认场景背景"}
              </button>
            </div>
          </div>

          {backgrounds.length === 0 ? (
            <div className="mt-4 rounded-md border border-dashed border-gray-300 bg-gray-50 p-4">
              <p className="text-sm font-medium text-gray-800">暂无派生的场景背景槽位。</p>
              <p className="mt-1 text-xs text-gray-500">
                请从冻结的蓝图生成场景包，让每个场景都提供 AI 生成 / 上传入口。
              </p>
            </div>
          ) : (
            <div role="table" className="mt-3 overflow-x-auto rounded-md border border-gray-200">
              <div role="row" className="hidden min-w-[980px] bg-gray-50 px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500 xl:grid xl:grid-cols-[96px_minmax(240px,1.1fr)_minmax(260px,1fr)_220px]">
                <div role="columnheader">缩略图</div>
                <div role="columnheader">描述</div>
                <div role="columnheader">提示词</div>
                <div role="columnheader">操作</div>
              </div>
              {backgrounds.map((slot) => assetRow(slot))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-900">脚本预览与提交</h3>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void previewScriptAction()}
                disabled={busyAction !== null || !canPreview}
                className="inline-flex items-center gap-1 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" />
                {busyAction === "preview-script" ? "生成中..." : "生成预览脚本"}
              </button>
              <button
                type="button"
                onClick={() => void commitScript()}
                disabled={busyAction !== null || activeState !== "script_preview"}
                className="inline-flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busyAction === "commit-script" ? "提交中..." : "提交预览脚本"}
              </button>
            </div>
          </div>
          {generationState?.script_preview?.staging_path && (
            <p className="mt-2 text-xs text-gray-500">最近暂存脚本：{generationState.script_preview.staging_path}</p>
          )}
          {previewScriptFiles.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">脚本文件：{previewScriptFiles.join(", ")}</p>
          )}
          {previewScript && (
            <pre className="mt-3 max-h-72 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-800">
              {previewScript}
            </pre>
          )}
          {generationState?.script_preview?.chapter_ids && generationState.script_preview.chapter_ids.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">章节 ID：{generationState.script_preview.chapter_ids.join(", ")}</p>
          )}
        </div>
      </div>
      {promptEditorSlot ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Edit asset prompt"
            className="w-full max-w-2xl rounded-lg bg-white p-5 shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-gray-900">编辑提示词</h3>
                <p className="mt-1 text-sm text-gray-500">
                  {promptEditorSlot.display_name || promptEditorSlot.target} ({promptEditorSlot.variant})
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPromptEditorSlotId(null)}
                className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700"
              >
                关闭
              </button>
            </div>
            <label className="mt-4 block text-sm font-medium text-gray-700">
              提示词
              <textarea
                aria-label={`${promptEditorSlot.target} ${promptEditorSlot.variant} prompt`}
                className="mt-1 block min-h-56 w-full rounded-md border border-gray-300 p-3 text-sm"
                value={currentPrompt(promptEditorSlot)}
                placeholder={
                  promptEditorSlot.generation_prompt ||
                  promptEditorSlot.prompt ||
                  promptPlaceholder(promptEditorSlot.kind, promptEditorSlot.target, promptEditorSlot.variant)
                }
                onChange={(event) => {
                  updateSlotPrompt(promptEditorSlot, event.target.value);
                }}
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPromptEditorSlotId(null)}
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
