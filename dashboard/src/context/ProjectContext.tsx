import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from "react";

export interface CurrentProject {
  name: string;
  path: string;
}

interface ProjectContextValue {
  currentProject: CurrentProject | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  selectProject: (name: string) => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [currentProject, setCurrentProject] = useState<CurrentProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const resp = await fetch("/api/projects/current");
      if (!resp.ok) throw new Error("Failed to fetch current project");
      const data = await resp.json();
      setCurrentProject(data.current_project ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  const selectProject = useCallback(async (name: string) => {
    const resp = await fetch("/api/projects/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to select project");
    }
    const data = await resp.json();
    setCurrentProject(data.current_project ?? null);
    window.dispatchEvent(new CustomEvent("project-changed"));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <ProjectContext.Provider
      value={{ currentProject, loading, error, refresh, selectProject }}
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
