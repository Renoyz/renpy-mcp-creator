import { Map } from "lucide-react";
import type { StoryMap } from "@/context/ProjectContext";

interface Props {
  storymap: StoryMap | null;
}

export function StoryMapSummaryPanel({ storymap }: Props) {
  if (!storymap) {
    return (
      <div className="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-2 mb-2">
          <Map className="h-4 w-4" />
          <span className="font-medium">Story Map</span>
        </div>
        <p>暂无 Story Map 数据</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Map className="h-4 w-4 text-primary" />
        <h3 className="font-semibold">Story Map</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-muted-foreground">节点:</span>{" "}
          <span className="font-medium">{storymap.nodes.length}</span>
        </div>
        <div>
          <span className="text-muted-foreground">边:</span>{" "}
          <span className="font-medium">{storymap.edges.length}</span>
        </div>
      </div>
      {storymap.edges.length > 0 && (
        <div className="text-xs text-muted-foreground space-y-1 max-h-24 overflow-y-auto">
          {storymap.edges.slice(0, 5).map((edge, idx) => (
            <div key={idx} className="truncate">
              {edge.from_scene_id} → {edge.to_scene_id}
              {edge.label ? ` (${edge.label})` : ""}
              <span className="ml-1 text-[10px] px-1 py-0.5 rounded bg-muted">
                {edge.type}
              </span>
            </div>
          ))}
          {storymap.edges.length > 5 && (
            <p>... 还有 {storymap.edges.length - 5} 条边</p>
          )}
        </div>
      )}
    </div>
  );
}
