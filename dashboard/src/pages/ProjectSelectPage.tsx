import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FolderPlus,
  FolderOpen,
  Loader2,
  Search,
  Sparkles,
  Film,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { useProject } from "../context/ProjectContext";

interface Project {
  name: string;
  path: string;
}

interface ProjectMeta {
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

export function ProjectSelectPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectMetas, setProjectMetas] = useState<Record<string, ProjectMeta>>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
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
      const projList: Project[] = data.projects || [];
      setProjects(projList);
      setErrors(data.errors || []);
      setError(null);

      // Fetch meta for each project to enrich cards (best-effort)
      const metaMap: Record<string, ProjectMeta> = {};
      await Promise.all(
        projList.map(async (p) => {
          try {
            const mresp = await fetch(`/api/projects/${encodeURIComponent(p.name)}/meta`);
            if (mresp.ok) {
              const meta = await mresp.json();
              metaMap[p.name] = meta;
            }
          } catch {
            // ignore individual meta failures
          }
        })
      );
      if (requestId === requestIdRef.current) {
        setProjectMetas(metaMap);
      }
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
      await selectProject(name);
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setCreating(false);
    }
  };

  const filteredProjects = projects.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  );

  const totalScenes = Object.values(projectMetas).reduce(
    (acc, m) => acc + (m.scene_count || 0),
    0
  );
  const completedProjects = projects.filter((p) => {
    const m = projectMetas[p.name];
    return m && m.confirmed_scenes && m.scene_count && m.confirmed_scenes === m.scene_count && m.scene_count > 0;
  }).length;

  return (
    <div className="h-full bg-gray-50 overflow-auto">
      {/* Sticky Header */}
      <div
        data-testid="dashboard-header"
        className="sticky top-0 z-10 border-b bg-white"
      >
        <div className="mx-auto max-w-7xl px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                RenPy MCP Creator
              </h1>
              <p className="text-xs text-gray-500">
                本地优先的 Ren'Py 视觉小说创作工具
              </p>
            </div>
          </div>

          <button
            data-testid="new-project-cta"
            onClick={() => setDialogOpen(true)}
            className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 transition-colors"
          >
            <FolderPlus className="h-4 w-4" />
            新建项目
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-6 py-6">
        {/* Search */}
        <div className="relative max-w-md mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索项目..."
            className="w-full rounded-md border bg-white pl-9 pr-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="rounded-lg border bg-white p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
              <FolderOpen className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{projects.length}</p>
              <p className="text-xs text-gray-500">项目总数</p>
            </div>
          </div>
          <div className="rounded-lg border bg-white p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{completedProjects}</p>
              <p className="text-xs text-gray-500">已完成项目</p>
            </div>
          </div>
          <div className="rounded-lg border bg-white p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center">
              <Film className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{totalScenes}</p>
              <p className="text-xs text-gray-500">总场景数</p>
            </div>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
            {error}
          </div>
        )}

        {/* Corrupt warnings */}
        {!loading && errors.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-800 mb-6">
            <h4 className="mb-2 font-medium">部分项目元数据损坏</h4>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {errors.map((err, idx) => (
                <li key={idx}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Project List Area */}
        <div data-testid="project-list-area">
          {!loading && !error && filteredProjects.length === 0 && errors.length === 0 && (
            <div
              data-testid="project-empty-state"
              className="text-center py-20"
            >
              <FolderOpen className="w-16 h-16 mx-auto text-gray-300 mb-4" />
              <p className="text-gray-500 text-lg font-medium">
                {search ? "没有找到符合条件的项目" : "还没有项目"}
              </p>
              {!search && (
                <p className="text-sm text-gray-400 mt-1">
                  点击右上角"新建项目"开始创建你的第一个视觉小说。
                </p>
              )}
            </div>
          )}

          {!loading && !error && filteredProjects.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {filteredProjects.map((proj) => {
                const meta = projectMetas[proj.name];
                const progress =
                  meta && meta.scene_count && meta.scene_count > 0
                    ? Math.round(
                        ((meta.confirmed_scenes || 0) / meta.scene_count) * 100
                      )
                    : 0;
                return (
                  <ProjectCard
                    key={proj.name}
                    project={proj}
                    meta={meta}
                    progress={progress}
                    onOpen={async () => {
                      await selectProject(proj.name);
                      navigate(`/projects/${encodeURIComponent(proj.name)}`);
                    }}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Create Project Dialog */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div
            data-testid="create-project-dialog"
            className="w-full max-w-md rounded-lg border bg-white p-6 shadow-lg"
          >
            <h2 className="text-lg font-semibold text-gray-900">新建项目</h2>
            <p className="text-sm text-gray-500 mt-1">
              创建一个新的视觉小说项目，AI 将协助你生成蓝图和脚本。
            </p>
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  项目名称
                </label>
                <input
                  data-testid="create-project-name-input"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  placeholder="例如：樱花树下的约定"
                  className="mt-1 w-full rounded-md border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                  autoFocus
                />
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setDialogOpen(false)}
                className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-gray-50"
              >
                取消
              </button>
              <button
                data-testid="create-project-submit"
                onClick={handleCreate}
                disabled={creating || !newName.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  meta,
  progress,
  onOpen,
}: {
  project: Project;
  meta?: ProjectMeta;
  progress: number;
  onOpen: () => void;
}) {
  const statusLabel = meta?.status || "草稿";
  const genre = meta?.genre || "未分类";
  const description = meta?.description || "";
  const chapterCount = meta?.chapter_count || 0;
  const sceneCount = meta?.scene_count || 0;
  const updatedAt = meta?.updated_at
    ? new Date(meta.updated_at).toLocaleDateString("zh-CN")
    : "";

  const statusClass =
    progress === 100
      ? "bg-green-100 text-green-700"
      : progress > 0
      ? "bg-blue-100 text-blue-700"
      : "bg-gray-100 text-gray-600";

  return (
    <div
      data-testid="project-card"
      onClick={onOpen}
      className="group cursor-pointer rounded-lg border bg-white overflow-hidden hover:shadow-md transition-shadow"
    >
      <div className="h-24 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 relative" />
      <div className="p-5">
        <div className="flex items-start justify-between mb-2">
          <div>
            <h3 className="font-bold text-gray-900 text-lg">{project.name}</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                {genre}
              </span>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusClass}`}
              >
                {statusLabel}
              </span>
            </div>
          </div>
        </div>

        {description && (
          <p className="text-sm text-gray-500 line-clamp-2 mb-4">
            {description}
          </p>
        )}

        <div className="flex items-center gap-4 text-sm text-gray-500 mb-4">
          <div className="flex items-center gap-1">
            <Film className="w-4 h-4" />
            <span>{chapterCount} 章</span>
          </div>
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" />
            <span>
              {meta?.confirmed_scenes || 0}/{sceneCount} 场景
            </span>
          </div>
          {updatedAt && (
            <div className="flex items-center gap-1">
              <Clock className="w-4 h-4" />
              <span>{updatedAt}</span>
            </div>
          )}
        </div>

        {/* Progress */}
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-500">完成度</span>
            <span
              className={`font-medium ${
                progress === 100
                  ? "text-green-600"
                  : sceneCount === 0
                  ? "text-gray-400"
                  : "text-blue-600"
              }`}
            >
              {sceneCount === 0 ? "尚未开始" : `${progress}%`}
            </span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${
                progress === 100
                  ? "bg-green-500"
                  : sceneCount === 0
                  ? "bg-gray-300"
                  : "bg-blue-500"
              }`}
              style={{
                width: sceneCount === 0 ? "0%" : `${progress}%`,
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
