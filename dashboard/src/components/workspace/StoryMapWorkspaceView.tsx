import { Map as MapIcon, Flag, GitFork, Ghost, ArrowRight } from "lucide-react";
import type { StoryMap, Chapter } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";
import { useMemo } from "react";

interface Props {
  storymap: StoryMap | null;
  chapters: Chapter[];
}

export function StoryMapWorkspaceView({ storymap, chapters }: Props) {
  const sceneMap = useMemo(() => {
    const map = new Map<string, { chapterId: string; name: string; type?: string; is_ending?: boolean | null }>();
    for (const ch of chapters) {
      for (const sc of ch.scenes) {
        map.set(sc.id, { chapterId: ch.id, name: sc.name, type: sc.type, is_ending: sc.is_ending });
      }
    }
    return map;
  }, [chapters]);

  const edgesByFrom = useMemo(() => {
    if (!storymap) return new Map<string, { to: string; label?: string | null; type: string }[]>();
    const map = new Map<string, { to: string; label?: string | null; type: string }[]>();
    for (const edge of storymap.edges) {
      const list = map.get(edge.from_scene_id) || [];
      list.push({ to: edge.to_scene_id, label: edge.label, type: edge.type });
      map.set(edge.from_scene_id, list);
    }
    return map;
  }, [storymap]);

  if (!storymap) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <MapIcon className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">暂无 Story Map</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">
            请先创建项目蓝图以生成故事地图。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
        <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
          <MapIcon className="w-5 h-5 text-blue-500" />
          Story Map
        </h3>
        <span className="text-xs text-gray-500">
          {storymap.nodes.length} 节点 · {storymap.edges.length} 连线
        </span>
      </div>

      {/* Board */}
      <div data-testid="story-map-board" className="p-6 space-y-8">
        {chapters.map((chapter, chIndex) => (
          <ChapterBoard
            key={chapter.id}
            chapter={chapter}
            chIndex={chIndex}
            sceneMap={sceneMap}
            edgesByFrom={edgesByFrom}
          />
        ))}
      </div>
    </div>
  );
}

function ChapterBoard({
  chapter,
  chIndex,
  sceneMap,
  edgesByFrom,
}: {
  chapter: Chapter;
  chIndex: number;
  sceneMap: Map<string, { chapterId: string; name: string; type?: string; is_ending?: boolean | null }>;
  edgesByFrom: Map<string, { to: string; label?: string | null; type: string }[]>;
}) {
  return (
    <div data-testid="story-map-chapter" className="rounded-xl border border-gray-200 overflow-hidden">
      {/* Chapter header */}
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold text-sm shadow-sm">
          {chIndex + 1}
        </div>
        <div>
          <h4 className="font-semibold text-gray-900">{chapter.name}</h4>
          <p className="text-xs text-gray-500">{chapter.scenes.length} 个场景</p>
        </div>
      </div>

      {/* Scenes flow */}
      <div className="p-4">
        <div className="flex flex-wrap items-start gap-6">
          {chapter.scenes.map((scene, sIdx) => {
            const outgoing = edgesByFrom.get(scene.id) || [];
            const branches = outgoing.filter((e) => e.type === "branch");
            const isLast = sIdx === chapter.scenes.length - 1;

            return (
              <div key={scene.id} className="flex flex-col items-center gap-2">
                {/* Node row with main flow arrow */}
                <div className="flex items-center gap-3">
                  <SceneNode scene={scene} />
                  {!isLast && (
                    <ArrowRight className="w-4 h-4 text-gray-300 flex-shrink-0" />
                  )}
                </div>

                {/* Branch list below node */}
                {branches.length > 0 && (
                  <div className="flex flex-col gap-1">
                    {branches.map((edge, eIdx) => {
                      const target = sceneMap.get(edge.to);
                      return (
                        <div key={eIdx} className="flex items-center gap-1.5">
                          <ArrowRight className="w-3 h-3 text-purple-400 flex-shrink-0" />
                          <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-purple-50 border border-purple-200 text-[10px] text-purple-700">
                            <GitFork className="w-3 h-3" />
                            <span>{edge.label || target?.name || edge.to}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SceneNode({ scene }: { scene: Chapter["scenes"][0] }) {
  if (scene.type === "branch_point") {
    return (
      <div data-testid="story-map-scene-node" className="flex flex-col items-center">
        <div className="w-20 h-20 rotate-45 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 shadow-md flex items-center justify-center">
          <div className="-rotate-45 text-center px-1">
            <GitFork className="w-4 h-4 text-white mx-auto mb-0.5" />
            <p className="font-semibold text-white text-[10px] leading-tight truncate max-w-[72px]">
              {scene.name}
            </p>
          </div>
        </div>
        <span className="mt-3 text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium">
          分支点
        </span>
      </div>
    );
  }

  if (scene.type === "ending" || scene.is_ending) {
    return (
      <div
        data-testid="story-map-scene-node"
        className={cn(
          "w-32 p-3 rounded-xl border shadow-sm flex flex-col items-center text-center",
          "bg-amber-50 border-amber-200"
        )}
      >
        <Flag className="w-5 h-5 text-amber-500 mb-1" />
        <p className="font-semibold text-gray-900 text-sm">{scene.name}</p>
        <span className="mt-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">
          结局
        </span>
      </div>
    );
  }

  return (
    <div
      data-testid="story-map-scene-node"
      className={cn(
        "w-32 p-3 rounded-xl border shadow-sm flex flex-col items-center text-center transition-all hover:shadow-md",
        scene.status === "confirmed" && "bg-green-50 border-green-200",
        scene.status === "generated" && "bg-blue-50 border-blue-200",
        scene.status === "audit_fail" && "bg-red-50 border-red-200",
        scene.status === "pending" && "bg-gray-50 border-gray-200 opacity-70",
        scene.status === "generating" && "bg-yellow-50 border-yellow-200",
        !scene.status && "bg-gray-50 border-gray-200"
      )}
    >
      <p className="font-medium text-gray-900 text-sm">{scene.name}</p>
      {scene.type === "hidden" && <Ghost className="w-3.5 h-3.5 text-gray-400 mt-1" />}
      <span
        className={cn(
          "mt-2 text-[10px] px-1.5 py-0.5 rounded font-medium",
          scene.status === "confirmed" && "bg-green-100 text-green-700",
          scene.status === "generated" && "bg-blue-100 text-blue-700",
          scene.status === "audit_fail" && "bg-red-100 text-red-700",
          scene.status === "pending" && "bg-gray-100 text-gray-600",
          scene.status === "generating" && "bg-yellow-100 text-yellow-700",
          !scene.status && "bg-gray-100 text-gray-600"
        )}
      >
        {scene.status === "confirmed" && "已确认"}
        {scene.status === "generated" && "已生成"}
        {scene.status === "audit_fail" && "审计失败"}
        {scene.status === "pending" && "待生成"}
        {scene.status === "generating" && "生成中"}
        {!scene.status && "待生成"}
      </span>
    </div>
  );
}
