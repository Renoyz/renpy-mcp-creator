import { ChevronDown, ChevronRight, Circle, Loader2, CheckCircle2, AlertCircle, GitFork, Flag, Ghost, FileText } from "lucide-react";
import { useState, useEffect } from "react";
import type { Chapter, Scene } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";

interface Props {
  chapters: Chapter[];
  selectedSceneId: string | null;
  onSelectScene: (sceneId: string) => void;
}

const statusIcons: Record<string, React.ReactNode> = {
  pending: <Circle className="w-3.5 h-3.5 text-gray-400" />,
  generating: <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />,
  generated: <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />,
  confirmed: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
  audit_fail: <AlertCircle className="w-3.5 h-3.5 text-red-500" />,
};

export function WorkspaceSidebar({ chapters, selectedSceneId, onSelectScene }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(chapters.map((chapter) => [chapter.id, true]))
  );

  // Re-sync expansion state when chapters change (e.g., project switch)
  useEffect(() => {
    const init: Record<string, boolean> = {};
    chapters.forEach((ch) => {
      init[ch.id] = true;
    });
    setExpanded(init);
  }, [chapters]);

  const toggle = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="w-full h-full bg-gray-50/50 border-r border-gray-200 overflow-y-auto">
      <div className="p-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
          章节
        </h3>

        {chapters.length === 0 && (
          <div className="px-3 py-6 text-center">
            <FileText className="w-8 h-8 mx-auto text-gray-300 mb-2" />
            <p className="text-xs text-gray-400">暂无章节</p>
            <p className="text-[10px] text-gray-400 mt-1">先生成蓝图吧</p>
          </div>
        )}

        <div className="space-y-1">
          {chapters.map((chapter) => (
            <div key={chapter.id}>
              {/* Chapter Header */}
              <button
                onClick={() => toggle(chapter.id)}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  "hover:bg-gray-100 text-gray-700"
                )}
              >
                {expanded[chapter.id] ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
                <span className="flex-1 text-left truncate">{chapter.name}</span>
                <span className="text-xs text-gray-400">{chapter.scenes.length}</span>
              </button>

              {/* Scene List */}
              {expanded[chapter.id] && (
                <div className="ml-4 mt-1 space-y-1">
                  {chapter.scenes.map((scene: Scene) => (
                    <button
                      key={scene.id}
                      onClick={() => onSelectScene(scene.id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                        selectedSceneId === scene.id
                          ? "bg-blue-100 text-blue-700"
                          : "hover:bg-gray-100 text-gray-600"
                      )}
                    >
                      <span className="flex-shrink-0">
                        {statusIcons[scene.status || "pending"] ?? statusIcons.pending}
                      </span>
                      <span className="flex-1 text-left truncate">{scene.name}</span>
                      {scene.type === "branch_point" && (
                        <span title="分支点">
                          <GitFork className="w-3.5 h-3.5 text-purple-500" />
                        </span>
                      )}
                      {(scene.type === "ending" || scene.is_ending) && (
                        <span title="结局">
                          <Flag className="w-3.5 h-3.5 text-amber-500" />
                        </span>
                      )}
                      {scene.type === "hidden" && (
                        <span title="隐藏">
                          <Ghost className="w-3.5 h-3.5 text-gray-400" />
                        </span>
                      )}
                      <span className="text-xs text-gray-400">{scene.order}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
