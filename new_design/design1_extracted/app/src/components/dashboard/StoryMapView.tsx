import { useAppStore } from '@/store/useAppStore';
import { Map as MapIcon, Play, Flag, GitFork, Ghost } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { Chapter, Scene, FlowEdge } from '@/types';
import { cn } from '@/lib/utils';
import { useRef, useEffect, useState, useMemo } from 'react';

interface NodePos {
  x: number;
  y: number;
  width: number;
  height: number;
}

export function StoryMapView() {
  const { chapters, flowEdges, jumpToScene } = useAppStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [positions, setPositions] = useState<Record<string, NodePos>>({});

  // Measure node positions after render and on resize (deferred to avoid synchronous setState in effect)
  useEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const next: Record<string, NodePos> = {};
      for (const sceneId of Object.keys(nodeRefs.current)) {
        const el = nodeRefs.current[sceneId];
        if (el) {
          const rect = el.getBoundingClientRect();
          next[sceneId] = {
            x: rect.left - containerRect.left + container.scrollLeft,
            y: rect.top - containerRect.top + container.scrollTop,
            width: rect.width,
            height: rect.height,
          };
        }
      }
      requestAnimationFrame(() => setPositions(next));
    };

    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [chapters]);

  // Build edges with source/target in same view coordinates
  const renderedEdges = useMemo(() => {
    const list: {
      edge: FlowEdge;
      sx: number;
      sy: number;
      tx: number;
      ty: number;
      color: string;
    }[] = [];
    const palette = ['#3b82f6', '#a855f7', '#ec4899', '#f59e0b', '#10b981'];
    for (let i = 0; i < flowEdges.length; i++) {
      const edge = flowEdges[i];
      const src = positions[edge.fromSceneId];
      const tgt = positions[edge.toSceneId];
      if (src && tgt) {
        list.push({
          edge,
          sx: src.x + src.width / 2,
          sy: src.y + src.height / 2,
          tx: tgt.x + tgt.width / 2,
          ty: tgt.y + tgt.height / 2,
          color: palette[i % palette.length],
        });
      }
    }
    return list;
  }, [positions, flowEdges]);

  return (
    <div className="h-full overflow-hidden flex flex-col bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <MapIcon className="w-5 h-5 text-blue-500" />
          Story Map
        </h3>
        <Button variant="outline" size="sm" className="gap-2" disabled title="功能开发中">
          <Play className="w-4 h-4" />
          从头试玩
        </Button>
      </div>

      {/* Graph Area */}
      <div ref={containerRef} className="flex-1 overflow-auto relative">
        <div className="p-8 min-w-max">
          <div className="space-y-10">
            {chapters.map((chapter: Chapter, chIndex: number) => (
              <ChapterRow
                key={chapter.id}
                chapter={chapter}
                chIndex={chIndex}
                onSceneClick={(sceneId) => jumpToScene(sceneId)}
                registerRef={(sceneId, el) => {
                  nodeRefs.current[sceneId] = el;
                }}
              />
            ))}
          </div>

          {/* SVG Edge Layer */}
          <svg className="absolute inset-0 pointer-events-none overflow-visible" style={{ width: '100%', height: '100%' }}>
            {renderedEdges.map((e, idx) => {
              const midX = (e.sx + e.tx) / 2;
              const d = `M ${e.sx} ${e.sy} Q ${midX} ${e.sy} ${midX} ${(e.sy + e.ty) / 2} T ${e.tx} ${e.ty}`;
              return (
                <g key={idx}>
                  <path
                    d={d}
                    fill="none"
                    stroke={e.color}
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    opacity={0.7}
                  />
                  {/* Arrowhead */}
                  <circle cx={e.tx} cy={e.ty} r={3} fill={e.color} />
                </g>
              );
            })}
          </svg>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 px-3 py-2 rounded-lg bg-white/90 dark:bg-gray-900/90 border border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-400 flex items-center gap-4 shadow-sm">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-blue-500" />
            <span>主线</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-0 border-t-2 border-dashed border-purple-500" />
            <span>分支</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rotate-45 bg-purple-500 rounded-sm" />
            <span>分支点</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Flag className="w-3 h-3 text-amber-500" />
            <span>结局</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ChapterRow({
  chapter,
  chIndex,
  onSceneClick,
  registerRef,
}: {
  chapter: Chapter;
  chIndex: number;
  onSceneClick: (sceneId: string) => void;
  registerRef: (sceneId: string, el: HTMLDivElement | null) => void;
}) {
  // Group scenes by order into columns
  const columns = useMemo(() => {
    const map = new globalThis.Map<number, Scene[]>();
    for (const scene of chapter.scenes) {
      const col = map.get(scene.order) || [];
      col.push(scene);
      map.set(scene.order, col);
    }
    return Array.from(map.entries()).sort((a: [number, Scene[]], b: [number, Scene[]]) => a[0] - b[0]);
  }, [chapter.scenes]);

  return (
    <div className="flex items-start gap-6">
      {/* Chapter Header */}
      <div className="w-44 shrink-0 pt-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white font-bold shadow-sm">
            {chIndex + 1}
          </div>
          <div>
            <h4 className="font-semibold text-gray-900 dark:text-white">
              {chapter.name}
            </h4>
            <p className="text-xs text-gray-500">
              {chapter.scenes.length} 个场景
            </p>
          </div>
        </div>
      </div>

      {/* Scene Columns */}
      <div className="flex items-start gap-6">
        {columns.map(([order, scenes]) => (
          <div key={order} className="w-40 flex flex-col gap-4">
            {scenes.map((scene) => (
              <SceneNode
                key={scene.id}
                scene={scene}
                onClick={() => onSceneClick(scene.id)}
                ref={(el) => registerRef(scene.id, el)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function SceneNode({
  scene,
  onClick,
  ref,
}: {
  scene: Scene;
  onClick: () => void;
  ref: (el: HTMLDivElement | null) => void;
}) {
  if (scene.type === 'branch_point') {
    return (
      <div className="flex flex-col items-center">
        <div
          ref={ref}
          onClick={onClick}
          className="w-24 h-24 rotate-45 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 shadow-md flex items-center justify-center cursor-pointer hover:scale-105 transition-transform"
        >
          <div className="-rotate-45 text-center px-2">
            <GitFork className="w-4 h-4 text-white mx-auto mb-1" />
            <p className="font-semibold text-white text-xs leading-tight">
              {scene.name}
            </p>
          </div>
        </div>
        <Badge className="mt-4 text-[10px] px-1.5 py-0 border-0 bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
          分支点
        </Badge>
      </div>
    );
  }

  if (scene.type === 'ending' || scene.isEnding) {
    return (
      <div
        ref={ref}
        onClick={onClick}
        className={cn(
          "w-36 p-3 rounded-xl border shadow-sm cursor-pointer hover:shadow-md transition-all flex flex-col items-center text-center",
          "bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-800"
        )}
      >
        <Flag className="w-5 h-5 text-amber-500 mb-1" />
        <p className="font-semibold text-gray-900 dark:text-white text-sm">
          {scene.name}
        </p>
        <Badge className="mt-2 text-[10px] px-1.5 py-0 border-0 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          结局
        </Badge>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      onClick={onClick}
      className={cn(
        "w-36 p-3 rounded-xl border shadow-sm cursor-pointer hover:shadow-md transition-all",
        scene.status === 'confirmed' && "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800",
        scene.status === 'generated' && "bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800",
        scene.status === 'audit_fail' && "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800",
        scene.status === 'pending' && "bg-gray-50 dark:bg-gray-900/10 border-gray-200 dark:border-gray-700 opacity-70",
        scene.status === 'generating' && "bg-yellow-50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-gray-900 dark:text-white text-sm">
          {scene.name}
        </p>
        {scene.type === 'hidden' && <Ghost className="w-3.5 h-3.5 text-gray-400" />}
      </div>
      <Badge
        className={cn(
          'mt-2 text-[10px] px-1.5 py-0 border-0',
          scene.status === 'confirmed' && 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
          scene.status === 'generated' && 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
          scene.status === 'audit_fail' && 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
          scene.status === 'pending' && 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
          scene.status === 'generating' && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
        )}
      >
        {scene.status === 'confirmed' && '已确认'}
        {scene.status === 'generated' && '已生成'}
        {scene.status === 'audit_fail' && '审计失败'}
        {scene.status === 'pending' && '待生成'}
        {scene.status === 'generating' && '生成中'}
      </Badge>
    </div>
  );
}
