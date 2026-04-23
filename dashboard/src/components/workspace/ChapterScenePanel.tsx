import { ChevronDown, ChevronRight, Circle } from "lucide-react";
import { useState } from "react";
import type { Chapter, Scene } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";

interface Props {
  chapters: Chapter[];
  selectedSceneId: string | null;
  onSelectScene: (sceneId: string) => void;
}

export function ChapterScenePanel({ chapters, selectedSceneId, onSelectScene }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    chapters.forEach((ch) => {
      init[ch.id] = true;
    });
    return init;
  });

  const toggle = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="h-full overflow-y-auto border-r bg-card">
      <div className="p-3 border-b">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          章节
        </h3>
      </div>
      <div className="p-2 space-y-1">
        {chapters.length === 0 && (
          <p className="text-sm text-muted-foreground px-2 py-4 text-center">暂无章节</p>
        )}
        {chapters.map((chapter) => (
          <div key={chapter.id}>
            <button
              onClick={() => toggle(chapter.id)}
              className="w-full flex items-center gap-1 px-2 py-1.5 text-sm font-medium rounded hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {expanded[chapter.id] ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
              <span className="flex-1 text-left truncate">{chapter.name}</span>
              <span className="text-xs text-muted-foreground">{chapter.scenes.length}</span>
            </button>
            {expanded[chapter.id] && (
              <div className="ml-5 space-y-0.5">
                {chapter.scenes.map((scene: Scene) => (
                  <button
                    key={scene.id}
                    onClick={() => onSelectScene(scene.id)}
                    className={cn(
                      "w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded transition-colors",
                      selectedSceneId === scene.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    )}
                  >
                    <Circle className="h-3 w-3 flex-shrink-0" />
                    <span className="flex-1 text-left truncate">{scene.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
