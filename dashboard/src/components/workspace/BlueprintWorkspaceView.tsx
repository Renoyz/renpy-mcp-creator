import { FileText, Download, Edit3, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import type { Blueprint, RefinementStatus, Chapter } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";
import { useMemo, useState } from "react";

interface Props {
  blueprint: Blueprint | null;
  chapters?: Chapter[];
  refinementStatus?: RefinementStatus | null;
  onFreeze?: (() => Promise<void>) | null;
}

export function BlueprintWorkspaceView({ blueprint, chapters = [], refinementStatus, onFreeze }: Props) {
  const [freezePending, setFreezePending] = useState(false);
  const displayChapters = useMemo(() => {
    if (chapters.length > 0) return chapters;
    return blueprint?.chapters ?? [];
  }, [blueprint, chapters]);

  const flatScenes = useMemo(() => {
    return displayChapters.flatMap((ch) => ch.scenes);
  }, [displayChapters]);

  const stats = useMemo(() => {
    const confirmed = flatScenes.filter((s) => s.status === "confirmed").length;
    const total = flatScenes.length;
    return { confirmed, total };
  }, [flatScenes]);

  const freezeStatus = refinementStatus?.blueprint_freeze_status ?? null;
  const showFreezePrompt =
    !blueprint &&
    !!refinementStatus &&
    (refinementStatus.freeze_allowed || freezeStatus === "stale");

  if (!blueprint) {
    if (showFreezePrompt) {
      const title = freezeStatus === "stale" ? "已冻结的蓝图已过期" : "可以冻结蓝图";
      const message =
        freezeStatus === "stale"
          ? "项目简报或章节大纲在上次冻结后已变更，请重新冻结以刷新权威蓝图。"
          : "项目简报与章节大纲已全部确认，冻结蓝图以生成下游权威输入。";
      return (
        <div className="h-full flex items-center justify-center bg-gray-50 p-8">
          <div className="max-w-lg rounded-2xl border border-blue-200 bg-white p-8 text-center shadow-sm">
            <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center mx-auto mb-4">
              <FileText className="w-8 h-8 text-blue-500" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
            <p className="text-sm text-gray-500 max-w-md mx-auto mb-6">{message}</p>
            {onFreeze && (
              <button
                type="button"
                onClick={async () => {
                  setFreezePending(true);
                  try {
                    await onFreeze();
                  } finally {
                    setFreezePending(false);
                  }
                }}
                disabled={freezePending}
                className="inline-flex items-center gap-2 rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {freezePending ? "正在冻结..." : "冻结蓝图"}
              </button>
            )}
          </div>
        </div>
      );
    }
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <FileText className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">暂无项目蓝图</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto mb-6">
            请先通过对话创建项目蓝图，或手动上传已有 YAML 文件。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-gray-200 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-xl font-bold text-gray-900">
                {blueprint.title || "项目蓝图"}
              </h2>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">
                {blueprint.genre || "未分类"}
              </span>
            </div>
            <p className="text-sm text-gray-500">
              {displayChapters.length || 0} 章节 · {stats.total} 场景 · 已确认 {stats.confirmed} 个
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              disabled
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 opacity-50 cursor-not-allowed"
            >
              <Download className="w-3.5 h-3.5" />
              导出 YAML
            </button>
            <button
              disabled
              className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white opacity-50 cursor-not-allowed"
            >
              <Edit3 className="w-3.5 h-3.5" />
              编辑
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 space-y-10">
        {/* Metadata */}
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-blue-500 rounded-full" />
            项目信息
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <InfoCard label="世界观 / 背景" value={blueprint.worldview} />
            <InfoCard label="核心主题" value={blueprint.themes?.join("、")} />
            <InfoCard label="目标玩家" value={blueprint.target_audience} />
            <InfoCard label="预计游戏时长" value={blueprint.estimated_play_time} />
            <InfoCard label="视觉风格" value={blueprint.art_style} />
            <InfoCard label="音频风格" value={blueprint.audio_style} />
          </div>
        </section>

        {/* Characters */}
        {blueprint.characters && blueprint.characters.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <span className="w-1 h-4 bg-purple-500 rounded-full" />
              角色设计
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {blueprint.characters.map((char, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl border border-gray-200 bg-gray-50/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-gray-900">{char.name}</p>
                      <p className="text-xs text-gray-500">{char.role}</p>
                    </div>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border border-gray-200 bg-white text-gray-600">
                      {char.variants?.length || 0} 表情变体
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mt-2">{char.personality}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Chapters */}
        <section>
          <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-green-500 rounded-full" />
            章节结构
          </h3>
          <div className="space-y-4">
            {displayChapters.map((chapter, idx) => (
              <div
                key={chapter.id}
                className="rounded-xl border border-gray-200 overflow-hidden"
              >
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-semibold text-sm">
                      {idx + 1}
                    </div>
                    <p className="font-semibold text-gray-900">{chapter.name}</p>
                  </div>
                  <p className="text-xs text-gray-500">{chapter.scenes.length} 个场景</p>
                </div>
                <div className="p-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {chapter.scenes.map((scene) => {
                      const isConfirmed = scene.status === "confirmed";
                      const isFail = scene.status === "audit_fail";
                      const isGenerating = scene.status === "generating";
                      return (
                        <div
                          key={scene.id}
                          className={cn(
                            "p-3 rounded-lg border flex items-start gap-3 transition-colors",
                            isConfirmed
                              ? "bg-green-50 border-green-200"
                              : isFail
                              ? "bg-red-50 border-red-200"
                              : isGenerating
                              ? "bg-yellow-50 border-yellow-200"
                              : "bg-gray-50 border-gray-200"
                          )}
                        >
                          <div className="mt-0.5">
                            {isConfirmed && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                            {isFail && <AlertCircle className="w-4 h-4 text-red-500" />}
                            {isGenerating && <Loader2 className="w-4 h-4 text-yellow-500 animate-spin" />}
                            {!isConfirmed && !isFail && !isGenerating && (
                              <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {scene.name}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              {scene.characters?.join("、") || "无角色"}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value?: string | string[] }) {
  const display = Array.isArray(value) ? value.join("、") : value;
  return (
    <div className="p-3 rounded-lg border border-gray-200 bg-gray-50/50">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-sm text-gray-900">{display || "-"}</p>
    </div>
  );
}
