import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  ReactNode,
} from "react";
import { flushSync } from "react-dom";

export interface CurrentProject {
  name: string;
  path: string;
}

export interface ProjectMeta {
  name: string;
  status: string;
  pipeline_stage: string;
  description?: string | null;
  genre?: string | null;
  chapter_count?: number;
  scene_count?: number;
  confirmed_scenes?: number;
  updated_at?: string;
}

export interface DialogueBeat {
  speaker: string;
  intent: string;
  content_brief: string;
}

export interface SpritePlanItem {
  character_name: string;
  character_id: string;
  sprite_path: string | null;
  sprite_placeholder: boolean;
  sprite_renderable?: boolean;
  sprite_quality_reason?: string;
  position: string;
  expression: string;
}

export interface Scene {
  id: string;
  name: string;
  order: number;
  characters?: string[];
  backgrounds?: string[];
  music?: string | null;
  choices?: { text: string; next_scene_id: string }[] | null;
  status?: string;
  type?: string;
  is_ending?: boolean | null;
  location?: string | null;
  location_visual_brief?: string | null;
  mood?: string | null;
  dialogue_beats?: DialogueBeat[];
  summary?: string | null;
  background_placeholder?: boolean;
  sprite_plan?: SpritePlanItem[];
}

export interface Chapter {
  id: string;
  name: string;
  order: number;
  scenes: Scene[];
}

export interface Blueprint {
  title: string;
  genre: string;
  worldview: string;
  themes?: string[];
  target_audience?: string;
  estimated_play_time?: string;
  art_style?: string;
  audio_style?: string;
  characters?: { name: string; role: string; personality: string; variants?: string[] | null }[];
  chapters?: Chapter[];
}

export interface StoryMap {
  nodes: { id: string; chapter_id: string; scene_id: string; type: string; label?: string | null }[];
  edges: {
    from_chapter_id: string;
    from_scene_id: string;
    to_chapter_id: string;
    to_scene_id: string;
    type: string;
    label?: string | null;
  }[];
}

export interface SceneScript {
  scene_id: string;
  chapter_id: string;
  label: string;
  content: string;
  file_path: string;
}

export type BlueprintPhase = "idle" | "collecting" | "reviewing" | "generating" | "editing";

export interface InterviewMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface GenerationProgress {
  step: string;
  percent: number;
}

interface ProjectContextValue {
  currentProject: CurrentProject | null;
  meta: ProjectMeta | null;
  blueprint: Blueprint | null;
  chapters: Chapter[];
  storymap: StoryMap | null;
  selectedSceneId: string | null;
  selectedSceneScript: SceneScript | null;
  scriptError: string | null;
  loading: boolean;
  error: string | null;
  blueprintPhase: BlueprintPhase;
  blueprintDraft: Blueprint | null;
  blueprintConfirmationId: string | null;
  workflowConfirmation: {
    confirmationId: string;
    message: string;
    candidates: { type: string; path: string }[];
    projectName?: string;
  } | null;
  interviewMessages: InterviewMessage[];
  generationProgress: GenerationProgress | null;
  refresh: () => Promise<void>;
  selectProject: (name: string) => Promise<CurrentProject | null>;
  loadProjectData: (name: string) => Promise<void>;
  selectScene: (sceneId: string, projectName?: string) => Promise<void>;
  setBlueprintPhase: (phase: BlueprintPhase) => void;
  startBlueprintCollection: () => void;
  sendBlueprintConfirmation: (approved: boolean) => void;
  registerBlueprintConfirmationSender: (sender: (approved: boolean) => boolean) => (() => void);
  registerBlueprintStartSender: (sender: () => void) => (() => void);
  handleBlueprintEvent: (event: any) => void;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [currentProject, setCurrentProject] = useState<CurrentProject | null>(null);
  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [storymap, setStorymap] = useState<StoryMap | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedSceneScript, setSelectedSceneScript] = useState<SceneScript | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [blueprintPhase, setBlueprintPhaseState] = useState<BlueprintPhase>("idle");
  const [blueprintDraft, setBlueprintDraft] = useState<Blueprint | null>(null);
  const [blueprintConfirmationId, setBlueprintConfirmationId] = useState<string | null>(null);
  const [workflowConfirmation, setWorkflowConfirmation] = useState<{
    confirmationId: string;
    message: string;
    candidates: { type: string; path: string }[];
    projectName?: string;
  } | null>(null);
  const [interviewMessages, setInterviewMessages] = useState<InterviewMessage[]>([]);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgress | null>(null);
  const blueprintConfirmationSenderRef = useRef<((approved: boolean) => boolean) | null>(null);
  const blueprintStartSenderRef = useRef<(() => void) | null>(null);
  const pendingStartRef = useRef(false);

  const requestVersionRef = useRef(0);
  const selectProjectVersionRef = useRef(0);
  const loadingTokenRef = useRef(0);
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    try {
      const resp = await fetch("/api/projects/current");
      if (!resp.ok) throw new Error("Failed to fetch current project");
      const data = await resp.json();
      const next = data.current_project ?? null;

      if (requestVersion !== requestVersionRef.current) return;

      setCurrentProject((prev) => {
        // If a concurrent selectProject already set a valid project, don't
        // overwrite it with null from a stale /api/projects/current response.
        if (next === null && prev !== null) {
          return prev;
        }
        if (
          prev?.name === next?.name &&
          prev?.path === next?.path
        ) {
          return prev;
        }
        return next;
      });
      setError(null);
    } catch (e) {
      if (requestVersion === requestVersionRef.current) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    }
  }, []);

  const selectProject = useCallback(async (name: string) => {
    const requestVersion = ++selectProjectVersionRef.current;
    try {
      const resp = await fetch("/api/projects/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        const error = new Error(err.detail || "Failed to select project") as Error & { status?: number };
        error.status = resp.status;
        throw error;
      }
      const data = await resp.json();
      const selectedProject = data.current_project ?? null;
      if (requestVersion === selectProjectVersionRef.current) {
        setCurrentProject(selectedProject);
        setError(null);
        window.dispatchEvent(new CustomEvent("project-changed"));
      }
      return selectedProject;
    } catch (e) {
      if (requestVersion === selectProjectVersionRef.current) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
      throw e;
    }
  }, []);

  const loadProjectData = useCallback(async (name: string) => {
    const requestVersion = ++requestVersionRef.current;
    const loadingToken = ++loadingTokenRef.current;
    setLoading(true);
    setError(null);
    setMeta(null);
    setBlueprint(null);
    setChapters([]);
    setStorymap(null);
    setSelectedSceneId(null);
    setSelectedSceneScript(null);
    setScriptError(null);
    setBlueprintDraft(null);
    setBlueprintConfirmationId(null);
    setWorkflowConfirmation(null);
    setInterviewMessages([]);
    setGenerationProgress(null);
    if (genTimerRef.current) {
      clearInterval(genTimerRef.current);
      genTimerRef.current = null;
    }

    try {
      const [metaResp, bpResp, scenesResp, mapResp, sessionResp] = await Promise.all([
        fetch(`/api/projects/${encodeURIComponent(name)}/meta`),
        fetch(`/api/projects/${encodeURIComponent(name)}/blueprint`),
        fetch(`/api/projects/${encodeURIComponent(name)}/scenes`),
        fetch(`/api/projects/${encodeURIComponent(name)}/storymap`),
        fetch(`/api/projects/${encodeURIComponent(name)}/blueprint-session`),
      ]);

      if (requestVersion !== requestVersionRef.current) return;

      if (metaResp.status === 404 && sessionResp.status === 404) {
        throw new Error("Project not found");
      }

      let metaData: ProjectMeta | null = null;
      if (metaResp.ok) {
        metaData = await metaResp.json();
        setMeta(metaData);
      }

      let bpData: Blueprint | null = null;
      if (bpResp.ok) {
        bpData = await bpResp.json();
        setBlueprint(bpData);
      } else if (bpResp.status === 404) {
        setBlueprint(null);
      } else {
        const err = await bpResp.json().catch(() => ({}));
        throw new Error(err.detail || `Blueprint error: ${bpResp.status}`);
      }

      let chaptersData: Chapter[] = [];
      if (scenesResp.ok) {
        const scenesJson = await scenesResp.json();
        chaptersData = scenesJson.chapters || [];
        setChapters(chaptersData);
      } else if (scenesResp.status === 404) {
        setChapters([]);
      } else {
        const err = await scenesResp.json().catch(() => ({}));
        throw new Error(err.detail || `Scenes error: ${scenesResp.status}`);
      }

      if (mapResp.ok) {
        const mapJson = await mapResp.json();
        setStorymap(mapJson);
      } else if (mapResp.status === 404) {
        setStorymap(null);
      }

      let sessionData: any = null;
      if (sessionResp.ok) {
        sessionData = await sessionResp.json();
      }

      // Restore state: blueprint data takes priority for workspace shell;
      // side workflow state (tool confirmation / progress) is restored independently.
      if (bpData) {
        // Project has real blueprint data → always editing workspace,
        // regardless of any side workflow session.
        setBlueprintPhaseState("editing");
        setBlueprintDraft(null);
        setBlueprintConfirmationId(null);
      } else if (sessionData && sessionData.pipeline_stage && sessionData.pipeline_stage !== "idle" && sessionData.pipeline_stage !== "editing") {
        // Active blueprint workflow without real blueprint yet
        setBlueprintPhaseState(sessionData.pipeline_stage as BlueprintPhase);
        if (sessionData.draft) {
          setBlueprintDraft(sessionData.draft);
        }
        setBlueprintConfirmationId(sessionData.confirmation_id ?? null);
      } else {
        setBlueprintPhaseState("idle");
        setBlueprintDraft(null);
        setBlueprintConfirmationId(null);
      }

      // Restore side workflow state independently (tool workflow)
      if (sessionData && sessionData.active_workflow === "tool") {
        if (sessionData.awaiting_confirmation) {
          setWorkflowConfirmation({
            confirmationId: sessionData.confirmation_id ?? "",
            message: sessionData.confirmation_message ?? "",
            candidates: sessionData.confirmation_candidates ?? [],
            projectName: sessionData.project_name ?? undefined,
          });
        } else {
          setWorkflowConfirmation(null);
        }
        if (sessionData.latest_progress) {
          setGenerationProgress({
            step: sessionData.latest_progress.step,
            percent: sessionData.latest_progress.percent,
          });
        } else {
          setGenerationProgress(null);
        }
      } else {
        setWorkflowConfirmation(null);
        if (sessionData && sessionData.latest_progress) {
          setGenerationProgress({
            step: sessionData.latest_progress.step,
            percent: sessionData.latest_progress.percent,
          });
        } else {
          setGenerationProgress(null);
        }
      }

      // Auto-select first scene
      const firstScene = chaptersData.flatMap((ch) => ch.scenes)[0];
      if (firstScene) {
        setSelectedSceneId(firstScene.id);
        const scriptResp = await fetch(
          `/api/projects/${encodeURIComponent(name)}/scenes/${encodeURIComponent(firstScene.id)}/script`
        );
        if (requestVersion !== requestVersionRef.current) return;
        if (scriptResp.ok) {
          const scriptData = await scriptResp.json();
          setSelectedSceneScript(scriptData);
          setScriptError(null);
        } else {
          setSelectedSceneScript(null);
          setScriptError("Failed to load scene script");
        }
      }

      setError(null);
    } catch (e) {
      if (requestVersion === requestVersionRef.current) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    } finally {
      if (loadingToken === loadingTokenRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const selectScene = useCallback(async (sceneId: string, projectName?: string) => {
    const requestVersion = ++requestVersionRef.current;
    setSelectedSceneId(sceneId);
    setSelectedSceneScript(null);
    setScriptError(null);

    const name = projectName || currentProject?.name;
    if (!name) {
      setScriptError("No current project");
      return;
    }

    try {
      const resp = await fetch(
        `/api/projects/${encodeURIComponent(name)}/scenes/${encodeURIComponent(sceneId)}/script`
      );
      if (requestVersion !== requestVersionRef.current) return;
      if (resp.ok) {
        const data = await resp.json();
        setSelectedSceneScript(data);
      } else {
        const err = await resp.json().catch(() => ({}));
        setScriptError(err.detail || `Script error: ${resp.status}`);
      }
    } catch (e) {
      if (requestVersion === requestVersionRef.current) {
        setScriptError(e instanceof Error ? e.message : "Unknown error");
      }
    }
  }, [currentProject]);

  const setBlueprintPhase = useCallback((phase: BlueprintPhase) => {
    setBlueprintPhaseState(phase);
  }, []);

  const requestBlueprintCollectionStart = useCallback(() => {
    if (blueprintStartSenderRef.current) {
      blueprintStartSenderRef.current();
    } else {
      pendingStartRef.current = true;
    }
  }, []);

  const registerBlueprintStartSender = useCallback((sender: () => void) => {
    blueprintStartSenderRef.current = sender;
    // Flush any start request that arrived before the sender was registered.
    if (pendingStartRef.current) {
      pendingStartRef.current = false;
      sender();
    }
    return () => {
      blueprintStartSenderRef.current = null;
    };
  }, []);

  const startBlueprintCollection = useCallback(() => {
    setBlueprintPhaseState("collecting");
    setInterviewMessages([]);
    setBlueprintDraft(null);
    setBlueprintConfirmationId(null);
    setGenerationProgress(null);
    requestBlueprintCollectionStart();
  }, [currentProject, requestBlueprintCollectionStart]);

  const handleBlueprintEvent = useCallback((event: any) => {
    if (!event || typeof event !== "object") return;

    const updatePhase = (phase: string) => {
      if (["idle", "collecting", "reviewing", "generating", "editing"].includes(phase)) {
        flushSync(() => {
          setBlueprintPhaseState(phase as BlueprintPhase);
        });
      }
    };

    if (event.type === "message") {
      if (event.message_kind === "blueprint_draft") {
        if (event.draft) {
          setBlueprintDraft(event.draft as Blueprint);
        }
        updatePhase(event.pipeline_stage ?? "reviewing");
      } else if (event.role === "user") {
        setInterviewMessages((prev) => [
          ...prev,
          { id: `${Date.now()}_u`, role: "user", content: String(event.content ?? "") },
        ]);
        if (event.pipeline_stage) updatePhase(event.pipeline_stage);
      } else if (event.role === "assistant") {
        setInterviewMessages((prev) => [
          ...prev,
          { id: `${Date.now()}_a`, role: "assistant", content: String(event.content ?? "") },
        ]);
        if (event.pipeline_stage) {
          updatePhase(event.pipeline_stage);
          if (event.pipeline_stage === "editing" && currentProject?.name) {
            loadProjectData(currentProject.name);
          }
        }
      }
    } else if (event.type === "blueprint_draft") {
      if (event.draft) {
        setBlueprintDraft(event.draft as Blueprint);
      }
      updatePhase(event.pipeline_stage ?? "reviewing");
    } else if (event.type === "confirmation_request") {
      if (event.draft) {
        setBlueprintDraft(event.draft as Blueprint);
      }
      if (event.confirmation_id) {
        setBlueprintConfirmationId(event.confirmation_id);
      }
      updatePhase(event.pipeline_stage ?? "reviewing");
    } else if (event.type === "progress") {
      setGenerationProgress({
        step: String(event.step ?? ""),
        percent: Number(event.percent ?? 0),
      });
      updatePhase(event.pipeline_stage ?? "generating");
    } else if (event.type === "error") {
      if (event.pipeline_stage) {
        updatePhase(event.pipeline_stage);
      }
    }
  }, [currentProject?.name, loadProjectData]);

  const sendBlueprintConfirmation = useCallback((approved: boolean) => {
    let sent = false;
    if (blueprintConfirmationSenderRef.current) {
      sent = blueprintConfirmationSenderRef.current(approved);
    }
    if (!sent) {
      window.dispatchEvent(new CustomEvent("open-chat-drawer"));
    }
  }, []);

  const registerBlueprintConfirmationSender = useCallback((sender: (approved: boolean) => boolean) => {
    blueprintConfirmationSenderRef.current = sender;
    return () => {
      blueprintConfirmationSenderRef.current = null;
    };
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <ProjectContext.Provider
      value={{
        currentProject,
        meta,
        blueprint,
        chapters,
        storymap,
        selectedSceneId,
        selectedSceneScript,
        scriptError,
        loading,
        error,
        blueprintPhase,
        blueprintDraft,
        blueprintConfirmationId,
        workflowConfirmation,
        interviewMessages,
        generationProgress,
        refresh,
        selectProject,
        loadProjectData,
        selectScene,
        setBlueprintPhase,
        startBlueprintCollection,
        sendBlueprintConfirmation,
        registerBlueprintConfirmationSender,
        registerBlueprintStartSender,
        handleBlueprintEvent,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProject must be used within a ProjectProvider");
  }
  return ctx;
}
