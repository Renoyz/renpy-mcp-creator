import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { CurrentProject, useProject } from "../context/ProjectContext";
import { Loader2, Play, Hammer, Map, FileCode, Images } from "lucide-react";

type Status = "idle" | "running" | "success" | "failed";

export function ProjectWorkspacePage() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { currentProject, loading, selectProject } = useProject();
  const [resolvedProject, setResolvedProject] = useState<CurrentProject | null>(null);
  const [buildStatus, setBuildStatus] = useState<Status>("idle");
  const [buildMessage, setBuildMessage] = useState<string>("");
  const [previewStatus, setPreviewStatus] = useState<Status>("idle");
  const [previewMessage, setPreviewMessage] = useState<string>("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewAvailable, setPreviewAvailable] = useState(false);

  const activeProject =
    currentProject?.name === name
      ? currentProject
      : resolvedProject?.name === name
      ? resolvedProject
      : null;

  useEffect(() => {
    if (!name) return;
    if (currentProject?.name === name) {
      setResolvedProject(currentProject);
      return;
    }
    if (currentProject?.name !== name) {
      selectProject(name)
        .then((project) => {
          setResolvedProject(project);
        })
        .catch(() => {
          navigate("/projects");
        });
    }
  }, [name, currentProject, selectProject, navigate]);

  useEffect(() => {
    if (!activeProject) return;
    fetch("/api/projects/build/status")
      .then((r) => r.json())
      .then((data) => {
        if (data.status && data.status !== "idle") {
          setBuildStatus(data.status);
          setBuildMessage(data.message || "");
          setPreviewAvailable(!!data.previewable);
        }
      })
      .catch(() => {
        // ignore
      });
  }, [activeProject]);

  const handleBuild = async () => {
    if (!activeProject) return;
    setBuildStatus("running");
    setBuildMessage("");
    setPreviewUrl(null);
    try {
      const resp = await fetch("/api/projects/build", {
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
    if (!activeProject) return;
    setPreviewLoading(true);
    setPreviewStatus("running");
    setPreviewMessage("");
    try {
      const resp = await fetch("/api/projects/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
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

  if (!name) {
    return null;
  }

  if (loading || !activeProject) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{activeProject.name}</h1>
        <p className="text-sm text-muted-foreground">{activeProject.path}</p>
      </header>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleBuild}
          disabled={buildStatus === "running"}
          className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed ${
            buildStatus === "failed"
              ? "bg-destructive"
              : buildStatus === "success"
              ? "bg-green-600"
              : "bg-primary"
          }`}
        >
          {buildStatus === "running" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Hammer className="h-4 w-4" />
          )}
          {buildStatus === "running"
            ? "Building..."
            : buildStatus === "success"
            ? "Build Success"
            : buildStatus === "failed"
            ? "Build Failed"
            : "Build"}
        </button>
        <button
          onClick={handlePreview}
          disabled={previewLoading}
          className="inline-flex items-center gap-2 rounded-md border bg-muted px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-accent disabled:cursor-not-allowed"
        >
          {previewLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {previewLoading ? "Starting..." : "Preview"}
        </button>
      </div>

      {buildMessage && (
        <div
          className={`rounded-md p-3 text-sm ${
            buildStatus === "failed"
              ? "bg-destructive/10 text-destructive"
              : buildStatus === "success"
              ? "bg-green-50 text-green-700"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {buildMessage}
          {previewAvailable && (
            <div className="mt-1 text-xs text-green-600">Preview available</div>
          )}
        </div>
      )}

      {previewMessage && (
        <div
          className={`rounded-md p-3 text-sm ${
            previewStatus === "failed"
              ? "bg-destructive/10 text-destructive"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {previewMessage}
        </div>
      )}

      {previewUrl && (
        <div className="rounded-md border bg-card p-3 text-sm">
          <span className="text-muted-foreground">Preview URL: </span>
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-primary underline"
          >
            {previewUrl}
          </a>
        </div>
      )}

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
