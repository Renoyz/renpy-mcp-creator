import { Loader2, CheckCircle2 } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface ProgressCardProps {
  data: {
    chapterId: string;
    sceneId: string;
    sceneName: string;
    step: string;
    percent: number;
  };
}

export function ProgressCard({ data }: ProgressCardProps) {
  const isComplete = data.percent >= 100;

  return (
    <div className={cn(
      "rounded-xl border shadow-sm overflow-hidden",
      isComplete
        ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800"
        : "bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-800"
    )}>
      {/* Header */}
      <div className={cn(
        "px-4 py-2 flex items-center gap-2",
        isComplete
          ? "bg-green-100 dark:bg-green-900/20"
          : "bg-blue-100 dark:bg-blue-900/20"
      )}>
        {isComplete ? (
          <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />
        ) : (
          <Loader2 className="w-4 h-4 text-blue-600 dark:text-blue-400 animate-spin" />
        )}
        <span className={cn(
          "text-sm font-medium",
          isComplete
            ? "text-green-700 dark:text-green-400"
            : "text-blue-700 dark:text-blue-400"
        )}>
          {isComplete ? '生成完成' : '生成中...'}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-600 dark:text-gray-400">
            当前场景
          </span>
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            {data.sceneName}
          </span>
        </div>

        <div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
            {data.step}
          </p>
          <Progress
            value={data.percent}
            className={cn(
              "h-2",
              isComplete && "[&>div]:bg-green-500"
            )}
          />
          <div className="flex justify-end mt-1">
            <span className="text-xs text-gray-500">
              {data.percent}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
