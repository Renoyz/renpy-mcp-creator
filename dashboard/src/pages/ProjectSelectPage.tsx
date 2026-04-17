import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FolderPlus, FolderOpen, Loader2 } from "lucide-react";
import { useProject } from "../context/ProjectContext";

interface Project {
  name: string;
  path: string;
}

export function ProjectSelectPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const { selectProject } = useProject();
  const requestIdRef = useRef(0);

  const fetchProjects = async () => {
    const requestId = ++requestIdRef.current;
    try {
      setLoading(true);
      const resp = await fetch("/api/projects");
      if (!resp.ok) throw new Error("Failed to fetch projects");
      const data = await resp.json();
      if (requestId !== requestIdRef.current) return;
      setProjects(data.projects || []);
      setErrors(data.errors || []);
      setError(null);
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      setProjects([]);
      setErrors([]);
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      setCreating(true);
      const resp = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!resp.ok) throw new Error("Failed to create project");
      setDialogOpen(false);
      setNewName("");
      await fetchProjects();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">项目列表</h1>
        <button
          onClick={() => setDialogOpen(true)}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <FolderPlus className="h-4 w-4" />
          新建项目
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
          {error}
        </div>
      )}

      {!loading && errors.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-800">
          <h4 className="mb-2 font-medium">部分项目元数据损坏</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {errors.map((err, idx) => (
              <li key={idx}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {!loading && !error && projects.length === 0 && errors.length === 0 && (
        <div className="rounded-lg border bg-card p-8 text-center">
          <FolderOpen className="mx-auto h-10 w-10 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-medium">还没有项目</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            点击右上角"新建项目"开始创建你的第一个视觉小说。
          </p>
        </div>
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((proj) => (
            <button
              key={proj.name}
              onClick={async () => {
                await selectProject(proj.name);
                navigate(`/projects/${encodeURIComponent(proj.name)}`);
              }}
              className="rounded-lg border bg-card p-4 text-left transition-shadow hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
                  <FolderOpen className="h-5 w-5 text-secondary-foreground" />
                </div>
                <div className="min-w-0">
                  <h4 className="truncate font-medium">{proj.name}</h4>
                  <p className="truncate text-xs text-muted-foreground">{proj.path}</p>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
            <h2 className="text-lg font-semibold">新建项目</h2>
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium">项目名称</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="my_visual_novel"
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setDialogOpen(false)}
                  className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
                >
                  取消
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                  创建
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
