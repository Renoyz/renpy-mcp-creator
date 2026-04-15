import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import { Loader2 } from "lucide-react";

export function ProjectHomePage() {
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

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4">
      <h1 className="text-2xl font-bold tracking-tight">{currentProject.name}</h1>
      <p className="text-muted-foreground">项目主页建设中…</p>
    </div>
  );
}
