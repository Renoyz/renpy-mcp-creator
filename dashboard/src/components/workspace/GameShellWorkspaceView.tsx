import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CircleEllipsis, Eye, EyeOff, Play, Save } from "lucide-react";

export interface GameShellGalleryItem {
  id: string;
  title: string;
  image_path: string;
  source: string;
  unlock_mode: string;
  persistent_key: string;
}

export interface GameShellEndingItem {
  id: string;
  title: string;
  description: string;
  unlock_mode: string;
  persistent_key: string;
}

export interface GameShellConfig {
  title: string;
  subtitle: string;
  theme: string;
  main_menu_background: string;
  show_gallery: boolean;
  show_endings: boolean;
  show_replay: boolean;
  show_credits: boolean;
  gallery_items: GameShellGalleryItem[];
  ending_items: GameShellEndingItem[];
  credits: string[];
}

interface Props {
  projectName: string;
}

interface ActionState {
  busy: boolean;
  message: string | null;
  error: string | null;
}

const EMPTY_CONFIG: GameShellConfig = {
  title: "",
  subtitle: "",
  theme: "",
  main_menu_background: "",
  show_gallery: true,
  show_endings: false,
  show_replay: false,
  show_credits: true,
  gallery_items: [],
  ending_items: [],
  credits: [],
};

function normalizeGalleryItems(value: unknown): GameShellGalleryItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item, idx) => {
      if (typeof item === "string") {
        return {
          id: `gallery_${idx + 1}`,
          title: item,
          image_path: "",
          source: "placeholder",
          unlock_mode: "always",
          persistent_key: "",
        };
      }
      const candidate = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        id: typeof candidate.id === "string" && candidate.id ? candidate.id : `gallery_${idx + 1}`,
        title: typeof candidate.title === "string" ? candidate.title : "",
        image_path: typeof candidate.image_path === "string" ? candidate.image_path : "",
        source: typeof candidate.source === "string" ? candidate.source : "placeholder",
        unlock_mode: typeof candidate.unlock_mode === "string" ? candidate.unlock_mode : "always",
        persistent_key: typeof candidate.persistent_key === "string" ? candidate.persistent_key : "",
      };
    })
    .filter((item) => item.title.trim().length > 0 || item.image_path.trim().length > 0);
}

function normalizeEndingItems(value: unknown): GameShellEndingItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item, idx) => {
      if (typeof item === "string") {
        return {
          id: `ending_${idx + 1}`,
          title: item,
          description: "",
          unlock_mode: "always",
          persistent_key: "",
        };
      }
      const candidate = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
      return {
        id: typeof candidate.id === "string" && candidate.id ? candidate.id : `ending_${idx + 1}`,
        title: typeof candidate.title === "string" ? candidate.title : "",
        description: typeof candidate.description === "string" ? candidate.description : "",
        unlock_mode: typeof candidate.unlock_mode === "string" ? candidate.unlock_mode : "always",
        persistent_key: typeof candidate.persistent_key === "string" ? candidate.persistent_key : "",
      };
    })
    .filter((item) => item.title.trim().length > 0 || item.description.trim().length > 0);
}

function normalizeCredits(value: unknown): string[] {
  if (typeof value === "string") {
    return value.split("\n").map((item) => item.trim()).filter(Boolean);
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  return [];
}

function parseApiError(payload: unknown): string {
  if (payload && typeof payload === "object") {
    const candidate = payload as Record<string, unknown>;
    if (typeof candidate.detail === "string") return candidate.detail;
    if (typeof candidate.message === "string") return candidate.message;
    if (typeof candidate.error === "string") return candidate.error;
  }
  return "Request failed. Please check backend response and retry.";
}

async function parseFetchError(resp: Response): Promise<string> {
  try {
    const payload = await resp.json();
    return parseApiError(payload);
  } catch {
    return `Request failed (${resp.status})`;
  }
}

function withProjectPath(path: string, projectName: string) {
  return `/api/projects/${encodeURIComponent(projectName)}${path}`;
}

export function GameShellWorkspaceView({ projectName }: Props) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<GameShellConfig>(EMPTY_CONFIG);

  const [saveState, setSaveState] = useState<ActionState>({ busy: false, message: null, error: null });
  const [deriveState, setDeriveState] = useState<ActionState>({ busy: false, message: null, error: null });
  const [renderState, setRenderState] = useState<ActionState>({ busy: false, message: null, error: null });
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewFiles, setPreviewFiles] = useState<string[]>([]);
  const [previewText, setPreviewText] = useState<string>("");

  const listInputId = useMemo(
    () => ({
      gallery: "gameshell-gallery-item",
      ending: "gameshell-ending-item",
    }),
    []
  );

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const resp = await fetch(withProjectPath("/game-shell", projectName), {
          method: "GET",
        });

        if (!resp.ok) {
          const message = await parseFetchError(resp);
          if (isMounted) setLoadError(message);
          return;
        }

        const raw = await resp.json();
        if (!isMounted) return;

        setDraft({
          title: typeof raw.title === "string" ? raw.title : "",
          subtitle: typeof raw.subtitle === "string" ? raw.subtitle : "",
          theme: typeof raw.theme === "string" ? raw.theme : "",
          main_menu_background: typeof raw.main_menu_background === "string" ? raw.main_menu_background : "",
          show_gallery: raw.show_gallery === true,
          show_endings: raw.show_endings === true,
          show_replay: raw.show_replay === true,
          show_credits: raw.show_credits === true,
          gallery_items: normalizeGalleryItems(raw.gallery_items),
          ending_items: normalizeEndingItems(raw.ending_items),
          credits: normalizeCredits(raw.credits),
        });
      } catch (error) {
        if (isMounted) {
          setLoadError(error instanceof Error ? error.message : "Failed to load Game Shell data");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      isMounted = false;
    };
  }, [projectName]);

  const updateText = useCallback(
    (
      field: keyof Pick<GameShellConfig, "title" | "subtitle" | "theme" | "main_menu_background">,
      value: string
    ) => {
      setDraft((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const updateBool = useCallback(
    (field: "show_gallery" | "show_endings" | "show_replay" | "show_credits", checked: boolean) => {
      setDraft((prev) => ({ ...prev, [field]: checked }));
    },
    []
  );

  const updateGalleryItem = useCallback((idx: number, field: keyof GameShellGalleryItem, value: string) => {
    setDraft((prev) => {
      const items = [...prev.gallery_items];
      items[idx] = { ...items[idx], [field]: value };
      return { ...prev, gallery_items: items };
    });
  }, []);

  const updateEndingItem = useCallback((idx: number, field: keyof GameShellEndingItem, value: string) => {
    setDraft((prev) => {
      const items = [...prev.ending_items];
      items[idx] = { ...items[idx], [field]: value };
      return { ...prev, ending_items: items };
    });
  }, []);

  const updateCreditsText = useCallback((value: string) => {
    setDraft((prev) => ({ ...prev, credits: normalizeCredits(value) }));
  }, []);

  const addItem = useCallback((kind: "gallery_items" | "ending_items") => {
    setDraft((prev) => ({
      ...prev,
      [kind]: kind === "gallery_items"
        ? [
            ...prev.gallery_items,
            {
              id: `gallery_${prev.gallery_items.length + 1}`,
              title: "",
              image_path: "",
              source: "placeholder",
              unlock_mode: "always",
              persistent_key: "",
            },
          ]
        : [
            ...prev.ending_items,
            {
              id: `ending_${prev.ending_items.length + 1}`,
              title: "",
              description: "",
              unlock_mode: "always",
              persistent_key: "",
            },
          ],
    }));
  }, []);

  const removeItem = useCallback((kind: "gallery_items" | "ending_items", idx: number) => {
    setDraft((prev) => ({ ...prev, [kind]: prev[kind].filter((_, i) => i !== idx) }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaveState({ busy: true, message: null, error: null });
    try {
      const resp = await fetch(withProjectPath("/game-shell", projectName), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });

      if (!resp.ok) {
        const message = await parseFetchError(resp);
        setSaveState({ busy: false, message: null, error: message });
        return;
      }

      setSaveState({ busy: false, message: "Saved successfully.", error: null });
    } catch (error) {
      setSaveState({
        busy: false,
        message: null,
        error: error instanceof Error ? error.message : "Failed to save Game Shell",
      });
    }
  }, [draft, projectName]);

  const handleDerive = useCallback(async () => {
    setDeriveState({ busy: true, message: null, error: null });
    try {
      const resp = await fetch(withProjectPath("/game-shell/derive", projectName), {
        method: "POST",
      });

      if (!resp.ok) {
        const message = await parseFetchError(resp);
        setDeriveState({ busy: false, message: null, error: message });
        return;
      }

      const raw = await resp.json();
      setDraft({
        title: typeof raw.title === "string" ? raw.title : "",
        subtitle: typeof raw.subtitle === "string" ? raw.subtitle : "",
        theme: typeof raw.theme === "string" ? raw.theme : "",
        main_menu_background: typeof raw.main_menu_background === "string" ? raw.main_menu_background : "",
        show_gallery: raw.show_gallery === true,
        show_endings: raw.show_endings === true,
        show_replay: raw.show_replay === true,
        show_credits: raw.show_credits === true,
        gallery_items: normalizeGalleryItems(raw.gallery_items),
        ending_items: normalizeEndingItems(raw.ending_items),
        credits: normalizeCredits(raw.credits),
      });
      setDeriveState({ busy: false, message: "Derived from prototype.", error: null });
    } catch (error) {
      setDeriveState({
        busy: false,
        message: null,
        error: error instanceof Error ? error.message : "Failed to derive from prototype",
      });
    }
  }, [projectName]);

  const handleRender = useCallback(async () => {
    setRenderState({ busy: true, message: null, error: null });
    setPreviewUrl(null);
    setPreviewFiles([]);
    setPreviewText("");
    try {
      const resp = await fetch(withProjectPath("/game-shell/render-preview", projectName), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });

      if (!resp.ok) {
        const message = await parseFetchError(resp);
        setRenderState({ busy: false, message: null, error: message });
        return;
      }

      const payload = await resp.json().catch(() => ({}));
      const nextUrl = typeof payload.preview_url === "string" ? payload.preview_url : null;
      setPreviewUrl(nextUrl);
      setPreviewFiles(Array.isArray(payload.script_files) ? payload.script_files.map(String) : []);
      setPreviewText(typeof payload.preview === "string" ? payload.preview : "");
      setRenderState({ busy: false, message: "Preview ready.", error: null });
    } catch (error) {
      setRenderState({
        busy: false,
        message: null,
        error: error instanceof Error ? error.message : "Failed to render shell preview",
      });
    }
  }, [draft, projectName]);

  const renderAlert = (state: ActionState) =>
    state.error ? (
      <div role="alert" className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">
        {state.error}
      </div>
    ) : state.message ? (
      <div className="mt-2 rounded-md border border-green-200 bg-green-50 p-2 text-sm text-green-700">
        {state.message}
      </div>
    ) : null;

  if (loading) {
    return <div className="h-full flex items-center justify-center p-6 text-sm text-gray-500">Loading Game Shell...</div>;
  }

  if (loadError) {
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className="max-w-md rounded-md border border-red-200 bg-red-50 p-4 text-center">
          <AlertCircle className="h-8 w-8 mx-auto mb-2 text-red-500" />
          <h3 className="text-sm font-semibold text-red-800">Failed to load Game Shell</h3>
          <p className="text-sm text-red-700 mt-1">{loadError}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white">
      <div className="sticky top-0 z-10 border-b border-gray-200 bg-white/95 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Game Shell</h2>
            <p className="text-sm text-gray-500 mt-0.5">Configure how the built game shell is presented.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saveState.busy}
              className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50"
            >
              {saveState.busy ? <span className="animate-spin">...</span> : <Save className="w-3.5 h-3.5" />}
              Save
            </button>
            <button
              onClick={handleDerive}
              disabled={deriveState.busy}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {deriveState.busy ? "..." : "Derive From Prototype"}
            </button>
            <button
              onClick={handleRender}
              disabled={renderState.busy}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {renderState.busy ? <span className="animate-spin">...</span> : <Play className="w-3.5 h-3.5" />}
              Render Shell Preview
            </button>
          </div>
        </div>
        {renderAlert(saveState)}
        {renderAlert(deriveState)}
        {renderAlert(renderState)}
        {previewUrl && (
          <p className="mt-3 text-sm">
            <a className="text-blue-600 underline" href={previewUrl} target="_blank" rel="noreferrer">
              {previewUrl}
            </a>
          </p>
        )}
        {(previewFiles.length > 0 || previewText) && (
          <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
            {previewFiles.length > 0 && (
              <p>
                <span className="font-semibold">Rendered files:</span> {previewFiles.join(", ")}
              </p>
            )}
            {previewText && (
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-white p-2">
                {previewText}
              </pre>
            )}
          </div>
        )}
      </div>

      <div className="px-6 py-6 space-y-8 max-w-5xl">
        <div className="rounded-lg border border-gray-200 p-4 space-y-4">
          <h3 className="text-sm font-semibold text-gray-900">Basic Settings</h3>
          <label className="space-y-1 block text-sm">
            <span className="text-gray-600">Title</span>
            <input
              value={draft.title}
              onChange={(event) => updateText("title", event.target.value)}
              className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
            />
          </label>
          <label className="space-y-1 block text-sm">
            <span className="text-gray-600">Subtitle</span>
            <input
              value={draft.subtitle}
              onChange={(event) => updateText("subtitle", event.target.value)}
              className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
            />
          </label>
          <label className="space-y-1 block text-sm">
            <span className="text-gray-600">Theme</span>
            <input
              value={draft.theme}
              onChange={(event) => updateText("theme", event.target.value)}
              className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
            />
          </label>
          <label className="space-y-1 block text-sm">
            <span className="text-gray-600">Main Menu Background</span>
            <input
              value={draft.main_menu_background}
              onChange={(event) => updateText("main_menu_background", event.target.value)}
              className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
            />
          </label>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <label className="rounded-lg border border-gray-200 p-3 flex items-center justify-between">
            <span className="text-sm text-gray-700">Show Gallery</span>
            <button
              type="button"
              onClick={() => updateBool("show_gallery", !draft.show_gallery)}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700"
            >
              {draft.show_gallery ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
              {draft.show_gallery ? "Enabled" : "Disabled"}
            </button>
          </label>
          <label className="rounded-lg border border-gray-200 p-3 flex items-center justify-between">
            <span className="text-sm text-gray-700">Show Endings</span>
            <button
              type="button"
              onClick={() => updateBool("show_endings", !draft.show_endings)}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700"
            >
              {draft.show_endings ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
              {draft.show_endings ? "Enabled" : "Disabled"}
            </button>
          </label>
          <label className="rounded-lg border border-gray-200 p-3 flex items-center justify-between">
            <span className="text-sm text-gray-700">Show Replay</span>
            <button
              type="button"
              onClick={() => updateBool("show_replay", !draft.show_replay)}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700"
            >
              {draft.show_replay ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
              {draft.show_replay ? "Enabled" : "Disabled"}
            </button>
          </label>
          <label className="rounded-lg border border-gray-200 p-3 flex items-center justify-between">
            <span className="text-sm text-gray-700">Show Credits</span>
            <button
              type="button"
              onClick={() => updateBool("show_credits", !draft.show_credits)}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-700"
            >
              {draft.show_credits ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
              {draft.show_credits ? "Enabled" : "Disabled"}
            </button>
          </label>
        </div>

        <div className="rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Gallery Items</h3>
            <button
              type="button"
              onClick={() => addItem("gallery_items")}
              className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-xs text-gray-700"
            >
              + Add Item
            </button>
          </div>
          <div className="mt-3 space-y-2">
            {draft.gallery_items.map((item, idx) => (
              <div
                key={`${listInputId.gallery}-${item.id}-${idx}`}
                className="grid grid-cols-[1fr_1.2fr_0.7fr_auto] gap-2 items-center"
              >
                <input
                  value={item.title}
                  aria-label={`Gallery title ${idx + 1}`}
                  onChange={(event) => updateGalleryItem(idx, "title", event.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  value={item.image_path}
                  aria-label={`Gallery image path ${idx + 1}`}
                  onChange={(event) => updateGalleryItem(idx, "image_path", event.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  value={item.source}
                  aria-label={`Gallery source ${idx + 1}`}
                  onChange={(event) => updateGalleryItem(idx, "source", event.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => removeItem("gallery_items", idx)}
                  className="px-2 py-1.5 rounded-md border border-gray-300 text-xs text-gray-600"
                >
                  Remove
                </button>
              </div>
            ))}
            {draft.gallery_items.length === 0 && <p className="text-xs text-gray-500">No gallery items yet.</p>}
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">Ending Items</h3>
            <button
              type="button"
              onClick={() => addItem("ending_items")}
              className="inline-flex items-center gap-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-xs text-gray-700"
            >
              + Add Item
            </button>
          </div>
          <div className="mt-3 space-y-2">
            {draft.ending_items.map((item, idx) => (
              <div
                key={`${listInputId.ending}-${item.id}-${idx}`}
                className="grid grid-cols-[1fr_1.4fr_auto] gap-2 items-center"
              >
                <input
                  value={item.title}
                  aria-label={`Ending title ${idx + 1}`}
                  onChange={(event) => updateEndingItem(idx, "title", event.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <input
                  value={item.description}
                  aria-label={`Ending description ${idx + 1}`}
                  onChange={(event) => updateEndingItem(idx, "description", event.target.value)}
                  className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => removeItem("ending_items", idx)}
                  className="px-2 py-1.5 rounded-md border border-gray-300 text-xs text-gray-600"
                >
                  Remove
                </button>
              </div>
            ))}
            {draft.ending_items.length === 0 && <p className="text-xs text-gray-500">No ending items yet.</p>}
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 p-4 space-y-2">
          <label className="space-y-1 block text-sm">
            <span className="text-gray-600">Credits</span>
            <textarea
              value={draft.credits.join("\n")}
              rows={4}
              onChange={(event) => updateCreditsText(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm"
            />
          </label>
        </div>

        <p className="text-xs text-gray-500 flex items-center gap-1">
          <CircleEllipsis className="h-3.5 w-3.5" />
          Gallery and ending items support simple row-based editing and can be expanded later by backend schema.
        </p>
      </div>
    </div>
  );
}
