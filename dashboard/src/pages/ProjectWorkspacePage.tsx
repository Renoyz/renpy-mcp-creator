import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CurrentProject, useProject } from "../context/ProjectContext";
import { WorkspaceSidebar } from "../components/workspace/WorkspaceSidebar";
import { WorkspaceTabs, type WorkspaceTab } from "../components/workspace/WorkspaceTabs";
import { BlueprintWorkspaceView } from "../components/workspace/BlueprintWorkspaceView";
import { StoryMapWorkspaceView } from "../components/workspace/StoryMapWorkspaceView";
import { SceneWorkspaceView } from "../components/workspace/SceneWorkspaceView";
import { WorkspaceOnboardingView } from "../components/workspace/WorkspaceOnboardingView";
import { BriefWorkspaceView } from "../components/workspace/BriefWorkspaceView";
import { ChapterOutlineWorkspaceView } from "../components/workspace/ChapterOutlineWorkspaceView";
import { RefinementStatusPanel } from "../components/workspace/RefinementStatusPanel";
import { IntakeWorkspaceView } from "../components/workspace/IntakeWorkspaceView";
import { runFreezeAutoGenerationChain } from "../lib/refinementAutomation";
import { Loader2, Play, Hammer, AlertCircle } from "lucide-react";

type Status = "idle" | "running" | "success" | "failed";
type UiFlowState = "idle" | "running" | "success" | "failed";

type FlowBanner = {
  status: UiFlowState;
  message: string;
  step?: string | null;
};

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
    brief,
    chapterOutline,
    refinementStatus,
    refinementIntake,
    briefError,
    chapterOutlineError,
    refinementStatusError,
    refinementIntakeError,
    selectProject,
    loadProjectData,
    selectScene,
    startBlueprintCollection,
    saveBrief,
    confirmCard,
    saveChapterOutline,
    confirmChapter,
    freezeBlueprint,
    promoteBriefDraft,
    promoteOutlineDraft,
  } = useProject();

  const [resolvedProject, setResolvedProject] = useState<CurrentProject | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(true);
  const snapshotLoadTokenRef = useRef(0);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("intake");
  const autoRouteTokenRef = useRef(0);
  const [buildStatus, setBuildStatus] = useState<Status>("idle");
  const [buildMessage, setBuildMessage] = useState<string>("");
  const [previewStatus, setPreviewStatus] = useState<Status>("idle");
  const [previewMessage, setPreviewMessage] = useState<string>("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewAvailable, setPreviewAvailable] = useState(false);
  const [pipelineStage, setPipelineStage] = useState<string>("idle");
  const [outlineReviewFlow, setOutlineReviewFlow] = useState<FlowBanner>({ status: "idle", message: "", step: null });
  const [postFreezeFlow, setPostFreezeFlow] = useState<FlowBanner>({ status: "idle", message: "", step: null });

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

  const canRunBuildPreview = !!blueprint;

  // Reset build/preview local state when project changes.
  // We do NOT force activeTab back to "intake" here because that
  // can race with promoteBriefDraft/promoteOutlineDraft and snap
  // the user away from the tab they just entered.
  useEffect(() => {
    setBuildStatus("idle");
    setBuildMessage("");
    setPreviewStatus("idle");
    setPreviewMessage("");
    setPreviewUrl(null);
    setPreviewAvailable(false);
    setPipelineStage("idle");
    setOutlineReviewFlow({ status: "idle", message: "", step: null });
    setPostFreezeFlow({ status: "idle", message: "", step: null });
    autoRouteTokenRef.current = 0;
  }, [name]);

  // Auto-route to the correct tab ONLY on the very first snapshot load after
  // a project change. We use a token ref so that mid-interaction refreshes
  // (e.g. loadBrief after confirm-card) never re-trigger routing.
  useEffect(() => {
    if (snapshotLoading || !activeProjectName) return;
    const token = ++autoRouteTokenRef.current;
    if (token !== 1) return; // only auto-route on first load for this project
    if (!brief) {
      setActiveTab("intake");
      return;
    }
    if (refinementStatus?.chapter_intake_required) {
      setActiveTab("intake");
      return;
    }
    setActiveTab("brief");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotLoading]);

  // Load unified pipeline status on mount / project change
  useEffect(() => {
    if (!activeProjectName) return;
    fetch(`/api/projects/${encodeURIComponent(activeProjectName)}/prototype/pipeline-status`)
      .then((r) => r.json())
      .then((data) => {
        setPipelineStage(data.stage || "idle");
        if (data.build_status && data.build_status !== "idle") {
          setBuildStatus(data.build_status);
          setBuildMessage(data.message || "");
        }
        setPreviewAvailable(!!data.previewable);
      })
      .catch(() => {});
  }, [activeProjectName]);

  // Load preview runtime status on mount / project change (refresh recovery)
  useEffect(() => {
    if (!activeProjectName) return;
    fetch(`/api/projects/${encodeURIComponent(activeProjectName)}/preview/status`)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "running" && data.url) {
          setPreviewUrl(data.url);
          setPreviewStatus("success");
        } else if (data.status === "failed") {
          setPreviewStatus("failed");
          setPreviewMessage(data.message || "Preview failed");
        }
      })
      .catch(() => {});
  }, [activeProjectName]);

  // Poll build status ONLY when pipeline stage indicates an active build
  useEffect(() => {
    if (!activeProjectName || pipelineStage !== "prototype_building") return;

    const poll = () => {
      fetch(`/api/projects/${encodeURIComponent(activeProjectName)}/build/status`)
        .then((r) => r.json())
        .then((data) => {
          setBuildStatus(data.status);
          setBuildMessage(data.message || "");
          setPreviewAvailable(!!data.previewable);
          // Once build leaves building, refresh pipeline stage to know the terminal state
          if (data.status !== "building") {
            fetch(`/api/projects/${encodeURIComponent(activeProjectName)}/prototype/pipeline-status`)
              .then((r) => r.json())
              .then((pipe) => setPipelineStage(pipe.stage || "idle"))
              .catch(() => {});
          }
        })
        .catch(() => {});
    };

    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [activeProjectName, pipelineStage]);

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
      const hasActivePrototype =
        protoStatus.is_active === true ||
        protoStatus.is_buildable === true ||
        protoStatus.mode === "single_chapter" ||
        protoStatus.mode === "multi_chapter";

      const buildUrl = hasActivePrototype
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
        if (hasActivePrototype) {
          setPipelineStage("prototype_preview_ready");
        }
      } else {
        setBuildStatus("failed");
        setBuildMessage(data.error || "Build failed");
        setPreviewAvailable(false);
        if (hasActivePrototype) {
          setPipelineStage("prototype_build_failed");
        }
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

  const handleFreezeBlueprint = async () => {
    if (!activeProjectName) return;
    setActiveTab("blueprint");
    setPostFreezeFlow({ status: "running", step: "freezing", message: "Freezing blueprint..." });
    try {
      await runFreezeAutoGenerationChain({
        projectName: activeProjectName,
        freezeBlueprint,
        refreshProjectData: loadProjectData,
        request: (url, init) => fetch(url, init),
        onProgress: (event) => {
          setPostFreezeFlow({
            status: event.status,
            step: event.step,
            message: event.message,
          });
        },
      });
      setBuildMessage("Scene packages and prototype scripts are ready. Next step: Build the game. Preview unlocks after a successful build.");
      setBuildStatus("idle");
      setPreviewAvailable(false);
      setPreviewMessage("");
    } catch (e) {
      setPostFreezeFlow({
        status: "failed",
        step: "failed",
        message: e instanceof Error ? e.message : "Automatic generation failed after freeze.",
      });
    }
  };

  const handlePromoteBriefDraft = async () => {
    if (!activeProjectName) return;
    setActiveTab("brief");
    await promoteBriefDraft(activeProjectName);
  };

  const handlePromoteOutlineDraft = async () => {
    if (!activeProjectName) return;
    setOutlineReviewFlow({
      status: "running",
      step: "outline_promote",
      message: "Generating Chapter Outline review...",
    });
    setActiveTab("outline");
    try {
      await promoteOutlineDraft(activeProjectName);
      setOutlineReviewFlow({ status: "success", step: "outline_ready", message: "Chapter Outline review is ready." });
    } catch (e) {
      setOutlineReviewFlow({
        status: "failed",
        step: "outline_failed",
        message: e instanceof Error ? e.message : "Failed to enter Chapter Outline review.",
      });
    }
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
          {canRunBuildPreview && (
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={handleBuild}
                disabled={buildStatus === "running" || postFreezeFlow.status === "running"}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium disabled:cursor-not-allowed ${
                  buildStatus === "failed"
                    ? "bg-red-600 text-white"
                    : buildStatus === "success"
                    ? "bg-green-600 text-white"
                    : "bg-gray-900 text-white"
                }`}
              >
                {buildStatus === "running" || postFreezeFlow.status === "running" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Hammer className="h-3.5 w-3.5" />
                )}
                {postFreezeFlow.status === "running"
                  ? "Preparing..."
                  : buildStatus === "running"
                  ? "Building..."
                  : buildStatus === "success"
                  ? "Build OK"
                  : buildStatus === "failed"
                  ? "Retry Build"
                  : "Build"}
              </button>
              <button
                onClick={handlePreview}
                disabled={previewLoading || postFreezeFlow.status === "running" || (!previewAvailable && !previewUrl)}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {previewLoading || postFreezeFlow.status === "running" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {postFreezeFlow.status === "running" ? "Preparing..." : previewLoading ? "Starting..." : "Preview"}
              </button>
            </div>
          )}
        </div>

        <div className="mt-3">
          <RefinementStatusPanel
            status={refinementStatus}
            error={refinementStatusError}
            onFreeze={handleFreezeBlueprint}
          />
        </div>
        {postFreezeFlow.status !== "idle" && (
          <div
            data-testid="post-freeze-status"
            className={`mt-2 rounded-md p-2 text-xs ${
              postFreezeFlow.status === "failed"
                ? "bg-red-50 text-red-700"
                : postFreezeFlow.status === "success"
                ? "bg-green-50 text-green-700"
                : "bg-blue-50 text-blue-700"
            }`}
          >
            {postFreezeFlow.message}
          </div>
        )}
        {canRunBuildPreview && buildMessage && (
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
        {canRunBuildPreview && previewMessage && (
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
        {canRunBuildPreview && previewUrl && (
          <div className="mt-2 rounded-md border border-gray-200 bg-white p-2 text-xs">
            <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-green-50 text-green-700 text-xs font-medium mr-2">
              Preview Running
            </span>
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
        {/* Left: Chapter/Scene navigation */}
        <div data-testid="workspace-sidebar" className="w-60 flex-shrink-0 bg-gray-50/50 border-r border-gray-200">
          <WorkspaceSidebar
            chapters={chapters}
            selectedSceneId={selectedSceneId}
            onSelectScene={handleSelectScene}
          />
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0 flex flex-col bg-white">
          <WorkspaceTabs
            activeTab={activeTab}
            onChange={setActiveTab}
            hasSceneSelected={!!selectedSceneId}
            onBackToOverview={() => setActiveTab("blueprint")}
          />
          <div className="flex-1 overflow-hidden">
            {activeTab === "intake" && (
              <IntakeWorkspaceView
                intake={refinementIntake}
                error={refinementIntakeError}
                projectName={activeProjectName}
                onPromoteBriefDraft={handlePromoteBriefDraft}
                onPromoteOutlineDraft={handlePromoteOutlineDraft}
                onStartAI={() => {
                  startBlueprintCollection("start_refinement_intake", activeProjectName);
                  window.dispatchEvent(new CustomEvent("open-chat-drawer"));
                }}
              />
            )}
            {activeTab === "brief" && (
              !brief && refinementStatus?.intake_required ? (
                <div className="h-full overflow-auto p-6">
                  <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 p-6">
                    <h2 className="text-base font-semibold text-blue-900">Start in Intake first</h2>
                    <p className="mt-2 text-sm text-blue-800">
                      The agent needs to collect project-level inputs and prepare a Project Brief draft before full
                      Brief review starts.
                    </p>
                    <button
                      type="button"
                      onClick={() => setActiveTab("intake")}
                      className="mt-4 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Go to Intake
                    </button>
                  </div>
                </div>
              ) : (
                <BriefWorkspaceView
                  brief={brief}
                  projectName={activeProjectName}
                  onSave={saveBrief}
                  onConfirmCard={confirmCard}
                  outlineDraftReady={!!refinementIntake?.outline_draft_ready}
                  onContinueChapterIntake={() => setActiveTab("intake")}
                  onProceedToOutline={() => {
                    void handlePromoteOutlineDraft();
                  }}
                  error={briefError}
                />
              )
            )}
            {activeTab === "outline" && (
              outlineReviewFlow.status === "running" && !chapterOutline ? (
                <div className="h-full overflow-auto p-6">
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-6">
                    <h2 className="text-base font-semibold text-blue-900">Preparing Outline Review</h2>
                    <p className="mt-2 text-sm text-blue-800">{outlineReviewFlow.message}</p>
                    <div
                      data-testid="outline-review-progress"
                      className="mt-4 h-2 w-full overflow-hidden rounded-full bg-blue-100"
                    >
                      <div className="h-full w-1/2 animate-pulse rounded-full bg-blue-600" />
                    </div>
                  </div>
                </div>
              ) : outlineReviewFlow.status === "failed" && !chapterOutline ? (
                <div className="h-full overflow-auto p-6">
                  <div className="rounded-lg border border-red-200 bg-red-50 p-6">
                    <h2 className="text-base font-semibold text-red-900">Failed to enter Outline Review</h2>
                    <p className="mt-2 text-sm text-red-800">{outlineReviewFlow.message}</p>
                    <button
                      type="button"
                      onClick={() => setActiveTab("intake")}
                      className="mt-4 rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700"
                    >
                      Go to Intake
                    </button>
                  </div>
                </div>
              ) : !chapterOutline && refinementStatus?.chapter_intake_required ? (
                <div className="h-full overflow-auto p-6">
                  <div className="rounded-lg border border-dashed border-blue-200 bg-blue-50 p-6">
                    <h2 className="text-base font-semibold text-blue-900">Chapter Intake First</h2>
                    <p className="mt-2 text-sm text-blue-800">
                      The agent needs to collect chapter-level inputs and prepare a Chapter Outline draft before full
                      Outline review starts.
                    </p>
                    <button
                      type="button"
                      onClick={() => setActiveTab("intake")}
                      className="mt-4 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      Go to Intake
                    </button>
                  </div>
                </div>
              ) : (
                <ChapterOutlineWorkspaceView
                  outline={chapterOutline}
                  projectName={activeProjectName}
                  onSave={saveChapterOutline}
                  onConfirmChapter={confirmChapter}
                  onFreezeBlueprint={handleFreezeBlueprint}
                  error={chapterOutlineError}
                />
              )
            )}
            {activeTab === "blueprint" && (
              !blueprint &&
              blueprintPhase !== "editing" &&
              !refinementStatus?.freeze_allowed &&
              refinementStatus?.blueprint_freeze_status !== "stale" ? (
                <div data-testid="workspace-onboarding-view" className="h-full overflow-hidden">
                  <WorkspaceOnboardingView
                    phase={blueprintPhase}
                    generationProgress={generationProgress}
                    onStartAI={() => {
                      startBlueprintCollection("start_blueprint_collection", activeProjectName);
                      window.dispatchEvent(new CustomEvent("open-chat-drawer"));
                    }}
                  />
                </div>
              ) : (
                <BlueprintWorkspaceView
                  blueprint={blueprint}
                  chapters={chapters}
                  refinementStatus={refinementStatus}
                  onFreeze={handleFreezeBlueprint}
                />
              )
            )}
            {activeTab === "storymap" && (
              <StoryMapWorkspaceView
                storymap={storymap}
                chapters={chapters}
                onSelectScene={(sceneId) => {
                  void handleSelectScene(sceneId);
                }}
              />
            )}
            {activeTab === "scene" && (
              <SceneWorkspaceView
                script={selectedSceneScript}
                scriptError={scriptError}
                chapters={chapters}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
