import { Code, AlertCircle } from "lucide-react";
import type { SceneScript } from "@/context/ProjectContext";

interface Props {
  script: SceneScript | null;
  error: string | null;
}

export function SceneScriptPanel({ script, error }: Props) {
  if (error) {
    return (
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center gap-2 text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span className="font-medium">脚本加载失败</span>
        </div>
        <p className="text-sm text-muted-foreground mt-2">{error}</p>
      </div>
    );
  }

  if (!script) {
    return (
      <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-2 mb-2">
          <Code className="h-4 w-4" />
          <span className="font-medium">场景脚本</span>
        </div>
        <p>请选择一个场景</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card flex flex-col h-full">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Code className="h-4 w-4 text-primary" />
          <h3 className="font-semibold">{script.label || script.scene_id}</h3>
        </div>
        <span className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
          {script.file_path}
        </span>
      </div>
      <div className="flex-1 overflow-auto p-4">
        <pre className="text-sm font-mono text-foreground whitespace-pre-wrap bg-muted/50 rounded p-3">
          {script.content}
        </pre>
      </div>
    </div>
  );
}
