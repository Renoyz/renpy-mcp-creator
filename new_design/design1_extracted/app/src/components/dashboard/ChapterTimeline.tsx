import { ChevronDown, ChevronRight, Play, Loader2, CheckCircle2, Circle, AlertCircle, GitFork, Flag, Ghost, FileText } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import type { SceneStatus, Chapter, Scene } from '@/types';
import { cn } from '@/lib/utils';

const statusIcons: Record<SceneStatus, React.ReactNode> = {
  pending: <Circle className="w-4 h-4 text-gray-400" />,
  generating: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
  generated: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  confirmed: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
  audit_fail: <AlertCircle className="w-4 h-4 text-red-500" />,
};

export function ChapterTimeline() {
  const { chapters, selectedChapterId, selectedSceneId, toggleChapter, setSelectedScene } = useAppStore();

  return (
    <div className="w-full h-full bg-gray-50/50 dark:bg-gray-900/50 border-r border-gray-200 dark:border-gray-800 overflow-y-auto">
      <div className="p-4">
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
          CHAPTERS
        </h3>

        {chapters.length === 0 && (
          <div className="px-3 py-6 text-center">
            <FileText className="w-8 h-8 mx-auto text-gray-300 mb-2" />
            <p className="text-xs text-gray-400">暂无章节</p>
            <p className="text-[10px] text-gray-400 mt-1">先生成蓝图吧</p>
          </div>
        )}

        <div className="space-y-1">
          {chapters.map((chapter: Chapter) => (
            <div key={chapter.id} className="">
              {/* Chapter Header */}
              <button
                onClick={() => toggleChapter(chapter.id)}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors group",
                  selectedChapterId === chapter.id && !selectedSceneId
                    ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
                )}
              >
                {chapter.expanded ? (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                )}
                <span className="flex-1 text-left">{chapter.name}</span>

                {/* Play button on hover */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    alert(`试玩 ${chapter.name}`);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-opacity"
                  title="试玩本章"
                >
                  <Play className="w-3 h-3" />
                </button>
              </button>

              {/* Scene List */}
              {chapter.expanded && (
                <div className="ml-4 mt-1 space-y-1">
                  {chapter.scenes.map((scene: Scene) => (
                    <button
                      key={scene.id}
                      onClick={() => setSelectedScene(scene.id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                        selectedSceneId === scene.id
                          ? "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                          : "hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
                      )}
                    >
                      <span className="flex-shrink-0">
                        {statusIcons[scene.status]}
                      </span>
                      <span className="flex-1 text-left truncate">
                        {scene.name}
                      </span>
                      {scene.type === 'branch_point' && (
                        <span title="分支点">
                          <GitFork className="w-3.5 h-3.5 text-purple-500" />
                        </span>
                      )}
                      {(scene.type === 'ending' || scene.isEnding) && (
                        <span title="结局">
                          <Flag className="w-3.5 h-3.5 text-amber-500" />
                        </span>
                      )}
                      {scene.type === 'hidden' && (
                        <span title="隐藏">
                          <Ghost className="w-3.5 h-3.5 text-gray-400" />
                        </span>
                      )}
                      <span className="text-xs text-gray-400">
                        {scene.order}
                      </span>
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
