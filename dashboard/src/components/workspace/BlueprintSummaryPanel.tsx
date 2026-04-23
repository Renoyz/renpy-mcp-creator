import { FileText } from "lucide-react";
import type { Blueprint } from "@/context/ProjectContext";

interface Props {
  blueprint: Blueprint | null;
}

export function BlueprintSummaryPanel({ blueprint }: Props) {
  if (!blueprint) {
    return (
      <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-2 mb-2">
          <FileText className="h-4 w-4" />
          <span className="font-medium">蓝图</span>
        </div>
        <p>暂无蓝图数据</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-primary" />
        <h3 className="font-semibold">{blueprint.title || "项目蓝图"}</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-muted-foreground">类型:</span>{" "}
          <span>{blueprint.genre || "-"}</span>
        </div>
        <div>
          <span className="text-muted-foreground">世界观:</span>{" "}
          <span>{blueprint.worldview || "-"}</span>
        </div>
        {blueprint.themes && blueprint.themes.length > 0 && (
          <div className="col-span-2">
            <span className="text-muted-foreground">主题:</span>{" "}
            <span>{blueprint.themes.join("、")}</span>
          </div>
        )}
      </div>
    </div>
  );
}
