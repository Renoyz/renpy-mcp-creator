import { Code, AlertCircle, GitFork, ArrowRight, MapPin, Sparkles, Users, Image } from "lucide-react";
import type { SceneScript, Chapter } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";
import { useMemo, useState } from "react";

interface Props {
  script: SceneScript | null;
  scriptError: string | null;
  chapters: Chapter[];
}

export function SceneWorkspaceView({ script, scriptError, chapters }: Props) {
  const sceneMeta = useMemo(() => {
    if (!script) return null;
    for (const ch of chapters) {
      const s = ch.scenes.find((sc) => sc.id === script.scene_id);
      if (s) return { chapter: ch, scene: s };
    }
    return null;
  }, [script, chapters]);

  if (scriptError) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-red-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">脚本加载失败</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">{scriptError}</p>
        </div>
      </div>
    );
  }

  if (!script) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Code className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">未选择场景</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">
            请在左侧 Timeline 中选择一个 Scene 查看详情
          </p>
        </div>
      </div>
    );
  }

  const s = sceneMeta?.scene;
  const ch = sceneMeta?.chapter;

  const statusLabel =
    s?.status === "confirmed"
      ? "已确认"
      : s?.status === "generated"
      ? "已生成"
      : s?.status === "audit_fail"
      ? "审计失败"
      : s?.status === "generating"
      ? "生成中"
      : "待生成";

  const statusClass =
    s?.status === "confirmed"
      ? "bg-emerald-100 text-emerald-700"
      : s?.status === "generated"
      ? "bg-blue-100 text-blue-700"
      : s?.status === "audit_fail"
      ? "bg-red-100 text-red-700"
      : s?.status === "generating"
      ? "bg-yellow-100 text-yellow-700"
      : "bg-gray-100 text-gray-600";

  const typeLabel =
    s?.type === "branch_point"
      ? "分支点"
      : s?.type === "ending" || s?.is_ending
      ? "结局"
      : s?.type === "hidden"
      ? "隐藏"
      : "普通场景";

  const typeClass =
    s?.type === "branch_point"
      ? "bg-purple-100 text-purple-700"
      : s?.type === "ending" || s?.is_ending
      ? "bg-amber-100 text-amber-700"
      : s?.type === "hidden"
      ? "bg-gray-100 text-gray-600"
      : "bg-gray-100 text-gray-600";

  const [showRawScript, setShowRawScript] = useState(true);

  return (
    <div className="h-full overflow-auto bg-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-gray-200 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-xl font-bold text-gray-900">
                {ch?.name ? `${ch.name} · ` : ""}
                {s?.name || script.label || script.scene_id}
              </h2>
              <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", statusClass)}>
                {statusLabel}
              </span>
              <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-xs font-medium", typeClass)}>
                {typeLabel}
              </span>
            </div>
            <p className="text-sm text-gray-500 font-mono truncate max-w-lg">
              {script.file_path}
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 space-y-6">
        {/* Readable Scene View */}
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 bg-gray-50/50">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-500" />
              场景概览
            </h3>
          </div>
          <div className="px-5 py-4 space-y-4">
            {/* Location & Mood */}
            <div className="flex flex-wrap items-center gap-3">
              {s?.location && (
                <span data-testid="scene-location-badge" className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
                  <MapPin className="w-3 h-3" />
                  {s.location}
                </span>
              )}
              {s?.mood && (
                <span data-testid="scene-mood-badge" className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 text-xs font-medium">
                  <Sparkles className="w-3 h-3" />
                  {s.mood}
                </span>
              )}
              {s?.background_placeholder === false && (
                <span data-testid="scene-bg-ready" className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium">
                  <Image className="w-3 h-3" />
                  背景已生成
                </span>
              )}
              {s?.background_placeholder === true && (
                <span data-testid="scene-bg-placeholder" className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 text-xs font-medium">
                  <Image className="w-3 h-3" />
                  背景占位
                </span>
              )}
            </div>

            {/* Visual Brief */}
            {s?.location_visual_brief && (
              <div className="text-sm text-gray-600 leading-relaxed">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">视觉摘要</span>
                <p className="mt-1">{s.location_visual_brief}</p>
              </div>
            )}

            {/* Summary */}
            {s?.summary && (
              <div className="text-sm text-gray-700 leading-relaxed">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">剧情摘要</span>
                <p className="mt-1">{s.summary}</p>
              </div>
            )}

            {/* Characters */}
            {s?.characters && s.characters.length > 0 && (
              <div className="flex items-center gap-2 text-sm">
                <Users className="w-4 h-4 text-gray-400" />
                <span className="text-gray-500">登场角色:</span>
                <span className="text-gray-900">{s.characters.join("、")}</span>
              </div>
            )}

            {/* Sprite Plan */}
            {s?.sprite_plan && s.sprite_plan.length > 0 && (
              <div className="space-y-2">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">角色 Sprite</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  {s.sprite_plan.map((sp, idx) => {
                    const status = sp.sprite_placeholder
                      ? "placeholder"
                      : sp.sprite_renderable
                      ? "renderable"
                      : "suppressed";
                    const statusClass =
                      status === "renderable"
                        ? "bg-emerald-50 text-emerald-700"
                        : status === "suppressed"
                        ? "bg-amber-50 text-amber-700"
                        : "bg-gray-100 text-gray-500";
                    const dotColor =
                      status === "renderable"
                        ? "#10b981"
                        : status === "suppressed"
                        ? "#f59e0b"
                        : "#9ca3af";
                    const statusLabel =
                      status === "renderable"
                        ? "已上屏"
                        : status === "suppressed"
                        ? "未上屏"
                        : "占位";
                    return (
                      <span
                        key={idx}
                        data-testid={`sprite-badge-${sp.character_id}`}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium",
                          statusClass
                        )}
                        title={sp.sprite_quality_reason || ""}
                      >
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
                        {sp.character_name}
                        <span className="text-[10px] opacity-70">{sp.position}</span>
                        <span className="text-[10px] opacity-60">({statusLabel})</span>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Dialogue Beats */}
            {s?.dialogue_beats && s.dialogue_beats.length > 0 && (
              <div className="space-y-2">
                <span className="text-gray-400 text-xs font-medium uppercase tracking-wider">对话节拍</span>
                <div className="space-y-2 mt-1">
                  {s.dialogue_beats.map((beat, idx) => (
                    <div key={idx} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100">
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold shrink-0">
                        {beat.speaker.charAt(0)}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900">{beat.speaker}</div>
                        <div className="text-xs text-gray-500 mt-0.5">{beat.intent}</div>
                        <div className="text-sm text-gray-700 mt-1">{beat.content_brief}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Raw Script Toggle */}
        <div>
          <button
            onClick={() => setShowRawScript((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
          >
            <Code className="w-3.5 h-3.5" />
            {showRawScript ? "隐藏脚本源码" : "查看脚本源码"}
          </button>
          {showRawScript && (
            <div className="mt-3 rounded-xl border border-gray-200 bg-gray-950 p-5 overflow-x-auto">
              <pre className="text-sm font-mono text-gray-300 whitespace-pre">
                {script.content}
              </pre>
            </div>
          )}
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Characters / Backgrounds */}
          <div className="p-4 rounded-xl border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-900 mb-3">场景信息</h4>
            <div className="space-y-2 text-sm">
              <div className="flex gap-2">
                <span className="text-gray-500 shrink-0">章节:</span>
                <span className="text-gray-900">{ch?.name || script.chapter_id}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-gray-500 shrink-0">Label:</span>
                <span className="text-gray-900 font-mono">{script.label}</span>
              </div>
              {s?.characters && s.characters.length > 0 && (
                <div className="flex gap-2">
                  <span className="text-gray-500 shrink-0">角色:</span>
                  <span className="text-gray-900">{s.characters.join("、")}</span>
                </div>
              )}
              {s?.backgrounds && s.backgrounds.length > 0 && (
                <div className="flex gap-2">
                  <span className="text-gray-500 shrink-0">背景:</span>
                  <span className="text-gray-900">{s.backgrounds.join("、")}</span>
                </div>
              )}
              {s?.music && (
                <div className="flex gap-2">
                  <span className="text-gray-500 shrink-0">音乐:</span>
                  <span className="text-gray-900">{s.music}</span>
                </div>
              )}
            </div>
          </div>

          {/* Choices / Flow */}
          <div className="p-4 rounded-xl border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-900 mb-3">剧情流向</h4>
            {s?.choices && s.choices.length > 0 ? (
              <div className="space-y-2">
                {s.choices.map((choice, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 p-2 rounded-lg bg-purple-50 border border-purple-200"
                  >
                    <GitFork className="w-4 h-4 text-purple-500 shrink-0" />
                    <span className="text-sm text-purple-700 flex-1">{choice.text}</span>
                    <span className="flex items-center gap-1 text-xs text-gray-500">
                      {choice.next_scene_id}
                      <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-gray-50 text-center text-sm text-gray-500">
                无分支选项
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
