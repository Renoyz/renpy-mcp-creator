import { useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import { Loader2, Play, Hammer, Map, FileCode, Images } from "lucide-react";

export function ProjectWorkspacePage() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { currentProject, loading, selectProject } = useProject();

  useEffect(() => {
    if (!name) return;
    if (currentProject?.name !== name) {
      selectProject(name).catch(() => {
        navigate("/projects");
      });
    }
  }, [name, currentProject, selectProject, navigate]);

  if (loading || currentProject?.name !== name) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!currentProject) {
    return null;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{currentProject.name}</h1>
        <p className="text-sm text-muted-foreground">{currentProject.path}</p>
      </header>

      <div className="flex flex-wrap gap-3">
        <button
          disabled
          title="Build 功能即将上线"
          className="inline-flex items-center gap-2 rounded-md bg-primary/60 px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed"
        >
          <Hammer className="h-4 w-4" />
          Build（未实现）
        </button>
        <button
          disabled
          title="Preview 功能即将上线"
          className="inline-flex items-center gap-2 rounded-md border bg-muted px-4 py-2 text-sm font-medium text-muted-foreground disabled:cursor-not-allowed"
        >
          <Play className="h-4 w-4" />
          Preview（未实现）
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          to="/story-map"
          className="rounded-lg border bg-card p-4 transition-shadow hover:shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
              <Map className="h-5 w-5 text-secondary-foreground" />
            </div>
            <div>
              <h4 className="font-medium">Story Map</h4>
              <p className="text-xs text-muted-foreground">查看故事流程图</p>
            </div>
          </div>
        </Link>

        <Link
          to="/script-editor"
          className="rounded-lg border bg-card p-4 transition-shadow hover:shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
              <FileCode className="h-5 w-5 text-secondary-foreground" />
            </div>
            <div>
              <h4 className="font-medium">脚本编辑</h4>
              <p className="text-xs text-muted-foreground">编辑 Ren'Py 脚本</p>
            </div>
          </div>
        </Link>

        <Link
          to="/assets"
          className="rounded-lg border bg-card p-4 transition-shadow hover:shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-secondary">
              <Images className="h-5 w-5 text-secondary-foreground" />
            </div>
            <div>
              <h4 className="font-medium">资源管理</h4>
              <p className="text-xs text-muted-foreground">管理项目资源</p>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
