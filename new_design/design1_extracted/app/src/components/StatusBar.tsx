import { useAppStore } from '@/store/useAppStore';
import { Heart, CheckCircle2, Image, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Chapter, Scene, AuditIssue } from '@/types';

export function StatusBar() {
  const { auditReport, chapters } = useAppStore();

  // 计算统计数据
  const totalScenes = chapters.reduce((acc: number, ch: Chapter) => acc + ch.scenes.length, 0);
  const confirmedScenes = chapters.reduce(
    (acc: number, ch: Chapter) => acc + ch.scenes.filter((s: Scene) => s.status === 'confirmed').length,
    0
  );
  const pendingResources = 3; // 模拟数据

  // 视觉健康度（模拟）
  const healthScore = 92;

  return (
    <div className="h-10 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 px-4 flex items-center justify-between text-sm">
      {/* Left - Health Score */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Heart className={cn(
            "w-4 h-4",
            healthScore >= 90 ? "text-green-500" :
            healthScore >= 70 ? "text-yellow-500" : "text-red-500"
          )} />
          <span className="text-gray-600 dark:text-gray-400">
            视觉健康度
          </span>
          <span className={cn(
            "font-semibold",
            healthScore >= 90 ? "text-green-600" :
            healthScore >= 70 ? "text-yellow-600" : "text-red-600"
          )}>
            {healthScore}%
          </span>
        </div>

        <div className="h-4 w-px bg-gray-300 dark:bg-gray-700" />

        {/* Audit Status */}
        <div className="flex items-center gap-2">
          {auditReport?.status === 'failed' ? (
            <>
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <span className="text-red-600 dark:text-red-400">
                审计状态: {auditReport.issues.filter((i: AuditIssue) => i.severity === 'high').length} 个阻塞问题
              </span>
            </>
          ) : (
            <>
              <CheckCircle2 className="w-4 h-4 text-green-500" />
              <span className="text-green-600 dark:text-green-400">
                审计通过
              </span>
            </>
          )}
        </div>
      </div>

      {/* Right - Stats */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-blue-500" />
          <span className="text-gray-600 dark:text-gray-400">
            进度
          </span>
          <span className="font-semibold text-gray-900 dark:text-white">
            {confirmedScenes}/{totalScenes} 场景
          </span>
        </div>

        <div className="h-4 w-px bg-gray-300 dark:bg-gray-700" />

        <div className="flex items-center gap-2">
          <Image className="w-4 h-4 text-purple-500" />
          <span className="text-gray-600 dark:text-gray-400">
            待生成资源
          </span>
          <span className="font-semibold text-gray-900 dark:text-white">
            {pendingResources}
          </span>
        </div>
      </div>
    </div>
  );
}
