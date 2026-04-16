import { useAppStore } from '@/store/useAppStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { FileText, Edit3, Download, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMemo } from 'react';

export function BlueprintView() {
  const { blueprint, setBlueprintPhase } = useAppStore();

  const flatScenes = useMemo(() => {
    if (!blueprint?.chapters) return [];
    return blueprint.chapters.flatMap((ch: { scenes: { status: string }[] }) => ch.scenes);
  }, [blueprint]);

  const stats = useMemo(() => {
    const confirmed = flatScenes.filter((s: { status: string }) => s.status === 'confirmed').length;
    const total = flatScenes.length;
    return { confirmed, total };
  }, [flatScenes]);

  if (!blueprint) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-900 flex items-center justify-center mx-auto mb-4">
            <FileText className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
            暂无项目蓝图
          </h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto mb-6">
            请先通过对话创建项目蓝图，或手动上传已有 YAML 文件。
          </p>
          <Button onClick={() => setBlueprintPhase('collecting')}>
            开始创建蓝图
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white dark:bg-gray-950">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/90 dark:bg-gray-950/90 backdrop-blur border-b border-gray-200 dark:border-gray-800 px-6 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                {blueprint.title || '项目蓝图'}
              </h2>
              <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-0">
                {blueprint.genre || '校园恋爱'}
              </Badge>
            </div>
            <p className="text-sm text-gray-500">
              {blueprint.chapters?.length || 0} 章节 · {stats.total} 场景 · 已确认 {stats.confirmed} 个
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button variant="outline" size="sm" className="gap-2" disabled title="功能开发中">
              <Download className="w-4 h-4" />
              导出 YAML
            </Button>
            <Button
              size="sm"
              className="gap-2"
              onClick={() => setBlueprintPhase('editing')}
            >
              <Edit3 className="w-4 h-4" />
              编辑
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 space-y-10">
        {/* Metadata */}
        <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-blue-500 rounded-full" />
            项目信息
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <InfoCard label="世界观 / 背景" value={blueprint.worldview} />
            <InfoCard label="核心主题" value={blueprint.themes?.join('、')} />
            <InfoCard label="目标玩家" value={blueprint.targetAudience} />
            <InfoCard label="预计游戏时长" value={blueprint.estimatedPlayTime} />
            <InfoCard label="视觉风格" value={blueprint.artStyle} />
            <InfoCard label="音频风格" value={blueprint.audioStyle} />
          </div>
        </section>

        {/* Characters */}
        <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-purple-500 rounded-full" />
            角色设计
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {blueprint.characters?.map((char: { name: string; role: string; personality: string; variants?: string[] }, idx: number) => (
              <div
                key={idx}
                className="p-4 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-gray-900 dark:text-white">{char.name}</p>
                    <p className="text-xs text-gray-500">{char.role}</p>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {char.variants?.length || 0} 表情变体
                  </Badge>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                  {char.personality}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Chapters */}
        <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-1 h-4 bg-green-500 rounded-full" />
            章节结构
          </h3>
          <div className="space-y-4">
            {blueprint.chapters?.map((chapter: { id: string; name: string; scenes: { id: string; name: string; characters?: string[]; status: string }[] }, idx: number) => (
              <div
                key={chapter.id}
                className="rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden"
              >
                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-7 h-7 rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 flex items-center justify-center font-semibold text-sm">
                      {idx + 1}
                    </div>
                    <p className="font-semibold text-gray-900 dark:text-white">{chapter.name}</p>
                  </div>
                  <p className="text-xs text-gray-500">{chapter.scenes.length} 个场景</p>
                </div>
                <div className="p-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {chapter.scenes.map((scene: { id: string; name: string; characters?: string[]; status: string }) => {
                      const isConfirmed = scene.status === 'confirmed';
                      const isFail = scene.status === 'audit_fail';
                      const isGenerating = scene.status === 'generating';
                      return (
                        <div
                          key={scene.id}
                          className={cn(
                            "p-3 rounded-lg border flex items-start gap-3 transition-colors",
                            isConfirmed
                              ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800"
                              : isFail
                              ? "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800"
                              : isGenerating
                              ? "bg-yellow-50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800"
                              : "bg-gray-50 dark:bg-gray-900/30 border-gray-200 dark:border-gray-700"
                          )}
                        >
                          <div className="mt-0.5">
                            {isConfirmed && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                            {isFail && <AlertCircle className="w-4 h-4 text-red-500" />}
                            {isGenerating && <Loader2 className="w-4 h-4 text-yellow-500 animate-spin" />}
                            {!isConfirmed && !isFail && !isGenerating && <div className="w-4 h-4 rounded-full border-2 border-gray-300" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {scene.name}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              {scene.characters?.join('、') || '无角色'}
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
  const display = Array.isArray(value) ? value.join('、') : value;
  return (
    <div className="p-3 rounded-lg border border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-sm text-gray-900 dark:text-white">
        {display || '-'}
      </p>
    </div>
  );
}
