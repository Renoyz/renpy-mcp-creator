import { useAppStore } from '@/store/useAppStore';
import { Button } from '@/components/ui/button';
import { Loader2, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';

const logs = [
  '初始化 Spec Parser...',
  '调用 LLM 分析创作意图...',
  '生成角色设定（2 人）...',
  '构建章节大纲（3 章）...',
  '编排场景结构（8 场景）...',
  '检测分支点与结局...',
  '校验 Blueprint 一致性...',
];

export function GeneratingView() {
  const { generationProgress, isGenerating } = useAppStore();
  const percent = generationProgress?.percent ?? 0;

  return (
    <div className="h-full flex flex-col items-center justify-center bg-gray-50/50 dark:bg-gray-900/50 p-8">
      <div className="max-w-md w-full text-center">
        {/* Icon */}
        <div className="relative w-20 h-20 mx-auto mb-6">
          <div className="absolute inset-0 rounded-full bg-blue-100 dark:bg-blue-900/30 animate-ping opacity-30" />
          <div className="relative w-full h-full rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
            <Loader2 className="w-10 h-10 text-blue-600 dark:text-blue-400 animate-spin" />
          </div>
        </div>

        {/* Title */}
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
          {isGenerating ? '正在生成蓝图...' : '处理中...'}
        </h2>

        {/* Step */}
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 min-h-[1.25rem]">
          {generationProgress?.step || '请稍候...'}
        </p>

        {/* Progress Bar */}
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden mb-8">
          <div
            className={cn(
              'h-full transition-all duration-500 ease-out bg-blue-500'
            )}
            style={{ width: `${percent}%` }}
          />
        </div>

        {/* Pseudo Logs */}
        <div className="text-left bg-gray-900 rounded-xl p-4 mb-6 overflow-hidden">
          <div className="flex items-center gap-2 mb-3 text-gray-400">
            <Terminal className="w-4 h-4" />
            <span className="text-xs font-medium">生成日志</span>
          </div>
          <div className="space-y-2">
            {logs.slice(0, Math.max(1, Math.ceil((percent / 100) * logs.length))).map((log, idx) => (
              <div key={idx} className="text-xs text-gray-300 font-mono flex items-center gap-2">
                <span className="text-green-500">✓</span>
                {log}
              </div>
            ))}
            {percent < 100 && (
              <div className="text-xs text-gray-500 font-mono flex items-center gap-2">
                <span className="text-blue-400 animate-pulse">▸</span>
                等待中...
              </div>
            )}
          </div>
        </div>

        {/* Cancel */}
        <Button variant="outline" onClick={() => window.location.reload()}>
          取消生成
        </Button>
      </div>
    </div>
  );
}
