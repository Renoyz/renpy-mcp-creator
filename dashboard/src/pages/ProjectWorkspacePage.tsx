import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CurrentProject, useProject } from "../context/ProjectContext";
import { WorkspaceSidebar } from "../components/workspace/WorkspaceSidebar";
import { WorkspaceTabs, type WorkspaceTab } from "../components/workspace/WorkspaceTabs";
import { BlueprintWorkspaceView } from "../components/workspace/BlueprintWorkspaceView";
import { StoryMapWorkspaceView } from "../components/workspace/StoryMapWorkspaceView";
import { SceneWorkspaceView } from "../components/workspace/SceneWorkspaceView";
import { WorkspaceOnboardingView } from "../components/workspace/WorkspaceOnboardingView";
import { Loader2, Play, Hammer, AlertCircle } from "lucide-react";

type Status = "idle" | "running" | "success" | "failed";

export function ProjectWorkspacePage() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const {
    currentProject,
    meta,
    blueprint,
    chapters,
    storymap,
    selectedSceneId,
    selectedSceneScript,
    scriptError,
    error,
    blueprintPhase,
    generationProgress,
    selectProject,
    loadProjectData,
    selectScene,
    startBlueprintCollection,
  } = useProject();

  const [resolvedProject, setResolvedProject] = useState<CurrentProject | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(true);
  const snapshotLoadTokenRef = useRef(0);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("blueprint");
  const [buildStatus, setBuildStatus] = useState<Status>("idle");
  const [buildMessage, setBuildMessage] = useState<string>("");
  const [previewStatus, setPreviewStatus] = useState<Status>("idle");
  const [previewMessage, setPreviewMessage] = useState<string>("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewAvailable, setPreviewAvailable] = useState(false);

  // Derive the active project name as a stable primitive.
  // This prevents object-reference changes from re-triggering the load effect.
  const activeProjectName =
    currentProject != null && currentProject.name === name
      ? currentProject.name
      : resolvedProject != null && resolvedProject.name === name
      ? resolvedProject.name
      : null;

  // Resolve current project selection
  useEffect(() => {
    if (!name) return;
    if (currentProject?.name === name) {
      setResolvedProject(currentProject);
      return;
    }
    selectProject(name)
      .then((project) => {
        setResolvedProject(project);
      })
      .catch((err) => {
        const status = err instanceof Error && "status" in err ? (err as Error & { status?: number }).status : undefined;
        if (status === 404) {
          // Keep the route alive so loadProjectData can surface the error state
          setResolvedProject({ name, path: "" } as CurrentProject);
        } else {
          navigate("/projects");
        }
      });
  }, [name, currentProject, selectProject, navigate]);

  // Load project snapshot data
  useEffect(() => {
    if (!name || !activeProjectName) {
      setSnapshotLoading(true);
      return;
    }

    const token = ++snapshotLoadTokenRef.current;
    setSnapshotLoading(true);

    loadProjectData(name).finally(() => {
      if (token === snapshotLoadTokenRef.current) {
        setSnapshotLoading(false);
      }
    });
  }, [name, activeProjectName, loadProjectData]);

  const hasEditingWorkspace = !!blueprint || blueprintPhase === "editing";
  const isOnboarding = !hasEditingWorkspace;

  // Reset build/preview local state and active tab when project changes
  useEffect(() => {
    setBuildStatus("idle");
    setBuildMessage("");
    setPreviewStatus("idle");
    setPreviewMessage("");
    setPreviewUrl(null);
    setPreviewAvailable(false);
    setActiveTab("blueprint");
  }, [name]);

  // Poll build status (project-scoped)
  useEffect(() => {
    if (!activeProjectName) return;

    let intervalId: ReturnType<typeof setInterval> | null = null;
    let pollCount = 0;
    const MAX_POLLS = 30; // ~60 seconds max

    const poll = () => {
      pollCount += 1;
      fetch(`/api/projects/${encodeURIComponent(activeProjectName)}/build/status`)
        .then((r) => r.json())
        .then((data) => {
          if (data.status && data.status !== "idle") {
            setBuildStatus(data.status);
            setBuildMessage(data.message || "");
            setPreviewAvailable(!!data.previewable);

            // Keep polling while building; stop once terminal
            if (data.status === "building" && !intervalId) {
              intervalId = setInterval(poll, 2000);
            } else if (data.status !== "building" && intervalId) {
              clearInterval(intervalId);
              intervalId = null;
            }
          }
          // Stop after max polls to avoid infinite polling
          if (pollCount >= MAX_POLLS && intervalId) {
            clearInterval(intervalId);
            intervalId = null;
          }
        })
        .catch(() => {});
    };

    poll();

    // When entering editing from generating, auto-build may still be in progress.
    // Start a short-interval poll to catch the status update.
    if (blueprintPhase === "editing" && !intervalId) {
      intervalId = setInterval(poll, 2000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [activeProjectName, blueprintPhase]);

  const handleBuild = async () => {
    if (!activeProjectName) return;
    setBuildStatus("running");
    setBuildMessage("");
    setPreviewUrl(null);
    try {
      // Query prototype status to decide which build endpoint to use
      const statusResp = await fetch(
        `/api/projects/${encodeURIComponent(activeProjectName)}/prototype/status`
      );
      const protoStatus = await statusResp.json();
      const hasPrototype = protoStatus.has_prototype === true;

      const buildUrl = hasPrototype
        ? `/api/projects/${encodeURIComponent(activeProjectName)}/prototype/build`
        : `/api/projects/${encodeURIComponent(activeProjectName)}/build`;

      let resp = await fetch(buildUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: "web" }),
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        setBuildStatus("success");
        setBuildMessage(data.output_path ? `Built to ${data.output_path}` : "Build succeeded");
        setPreviewAvailable(true);
      } else {
        setBuildStatus("failed");
        setBuildMessage(data.error || "Build failed");
        setPreviewAvailable(false);
      }
    } catch (e) {
      setBuildStatus("failed");
      setBuildMessage(e instanceof Error ? e.message : "Build request failed");
    }
  };

  const handlePreview = async () => {
    if (!activeProjectName) return;
    setPreviewLoading(true);
    setPreviewStatus("running");
    setPreviewMessage("");
    try {
      const resp = await fetch(
        `/api/projects/${encodeURIComponent(activeProjectName)}/preview`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        }
      );
      const data = await resp.json();
      if (resp.ok && data.success) {
        setPreviewUrl(data.url);
        setPreviewStatus("success");
      } else {
        setPreviewUrl(null);
        setPreviewStatus("failed");
        setPreviewMessage(data.detail || "Preview failed");
      }
    } catch (e) {
      setPreviewUrl(null);
      setPreviewStatus("failed");
      setPreviewMessage(e instanceof Error ? e.message : "Preview request failed");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSelectScene = async (sceneId: string) => {
    await selectScene(sceneId, activeProjectName || undefined);
    setActiveTab("scene");
  };

  if (!name) {
    return null;
  }

  if (snapshotLoading || !activeProjectName) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-900">{error}</h2>
          <p className="text-muted-foreground mt-2">项目不存在或无法访问</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col -m-4">
      {/* Top header */}
      <div className="shrink-0 border-b bg-white px-4 py-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 data-testid="workspace-project-title" className="text-xl font-bold tracking-tight text-gray-900">{activeProjectName}</h1>
            {meta && (
              <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs font-medium">
                  {meta.status}
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded bg-gray-100 text-gray-700 text-xs">
                  {meta.pipeline_stage}
                </span>
                {meta.description && <span className="truncate max-w-md">{meta.description}</span>}
              </div>
            )}
          </div>
          {!isOnboarding && (
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={handleBuild}
                disabled={buildStatus === "running"}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium disabled:cursor-not-allowed ${
                  buildStatus === "failed"
                    ? "bg-red-600 text-white"
                    : buildStatus === "success"
                    ? "bg-green-600 text-white"
                    : "bg-gray-900 text-white"
                }`}
              >
                {buildStatus === "running" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Hammer className="h-3.5 w-3.5" />
                )}
                {buildStatus === "running"
                  ? "Building..."
                  : buildStatus === "success"
                  ? "Build OK"
                  : buildStatus === "failed"
                  ? "Build Failed"
                  : "Build"}
              </button>
              <button
                onClick={handlePreview}
                disabled={previewLoading}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed"
              >
                {previewLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {previewLoading ? "Starting..." : "Preview"}
              </button>
            </div>
          )}
        </div>

        {!isOnboarding && buildMessage && (
          <div
            data-testid="build-status"
            className={`mt-2 rounded-md p-2 text-xs ${
              buildStatus === "failed"
                ? "bg-red-50 text-red-700"
                : buildStatus === "success"
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {buildMessage}
            {previewAvailable && (
              <span className="ml-2 text-green-600">Preview available</span>
            )}
          </div>
        )}
        {!isOnboarding && previewMessage && (
          <div
            className={`mt-2 rounded-md p-2 text-xs ${
              previewStatus === "failed"
                ? "bg-red-50 text-red-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {previewMessage}
          </div>
        )}
        {!isOnboarding && previewUrl && (
          <div className="mt-2 rounded-md border border-gray-200 bg-white p-2 text-xs">
            <span className="text-gray-500">Preview: </span>
            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-blue-600 underline"
            >
              {previewUrl}
            </a>
          </div>
        )}
      </div>

      {/* Error banner for critical snapshot failures */}
      {error && (
        <div className="shrink-0 mx-4 mt-3 rounded-md border border-red-200 bg-red-50 p-3 flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main workspace area */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Chapter/Scene navigation — only in editing */}
        {!isOnboarding && (
          <div data-testid="workspace-sidebar" className="w-60 flex-shrink-0 bg-gray-50/50 border-r border-gray-200">
            <WorkspaceSidebar
              chapters={chapters}
              selectedSceneId={selectedSceneId}
              onSelectScene={handleSelectScene}
            />
          </div>
        )}

        {/* Main content */}
        <div className={`flex-1 min-w-0 flex flex-col ${isOnboarding ? "bg-gray-50" : "bg-white"}`}>
          {isOnboarding ? (
            <div data-testid="workspace-onboarding-view" className="flex-1 overflow-hidden">
              <WorkspaceOnboardingView
                phase={blueprintPhase}
                generationProgress={generationProgress}
                onStartAI={() => {
                  startBlueprintCollection();
                  window.dispatchEvent(new CustomEvent("open-chat-drawer"));
                }}

              />
            </div>
          ) : (
            <>
              <WorkspaceTabs
                activeTab={activeTab}
                onChange={setActiveTab}
                hasSceneSelected={!!selectedSceneId}
                onBackToOverview={() => setActiveTab("blueprint")}
              />
              <div className="flex-1 overflow-hidden">
                {activeTab === "blueprint" && <BlueprintWorkspaceView blueprint={blueprint} />}
                {activeTab === "storymap" && <StoryMapWorkspaceView storymap={storymap} chapters={chapters} />}
                {activeTab === "scene" && (
                  <SceneWorkspaceView
                    script={selectedSceneScript}
                    scriptError={scriptError}
                    chapters={chapters}
                  />
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
