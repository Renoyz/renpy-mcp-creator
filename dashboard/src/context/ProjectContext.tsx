import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
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
  selectProject: (name: string) => Promise<CurrentProject | null>;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [currentProject, setCurrentProject] = useState<CurrentProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestVersionRef = useRef(0);

  const refresh = useCallback(async () => {
    const requestVersion = ++requestVersionRef.current;
    try {
      setLoading(true);
      const resp = await fetch("/api/projects/current");
      if (!resp.ok) throw new Error("Failed to fetch current project");
      const data = await resp.json();
      if (requestVersion === requestVersionRef.current) {
        setCurrentProject(data.current_project ?? null);
        setError(null);
      }
    } catch (e) {
      if (requestVersion === requestVersionRef.current) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    } finally {
      if (requestVersion === requestVersionRef.current) {
        setLoading(false);
      }
    }
  }, []);

  const selectProject = useCallback(async (name: string) => {
    const requestVersion = ++requestVersionRef.current;
    try {
      setLoading(true);
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
      const selectedProject = data.current_project ?? null;
      if (requestVersion === requestVersionRef.current) {
        setCurrentProject(selectedProject);
        setError(null);
        setLoading(false);
      }
      window.dispatchEvent(new CustomEvent("project-changed"));
      return selectedProject;
    } catch (e) {
      if (requestVersion === requestVersionRef.current) {
        setError(e instanceof Error ? e.message : "Unknown error");
        setLoading(false);
      }
      throw e;
    }
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
