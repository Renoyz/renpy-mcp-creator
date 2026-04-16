import { useAppStore } from '@/store/useAppStore';
import { useChatStore } from '@/store/useChatStore';
import { AlertTriangle, AlertCircle, CheckCircle2, ChevronDown, ChevronUp, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { AuditIssue } from '@/types';

interface AuditReportCardProps {
  data: {
    status: 'passed' | 'failed';
    score: number;
    issues: AuditIssue[];
  };
}

export function AuditReportCard({ data }: AuditReportCardProps) {
  const [expanded, setExpanded] = useState(true);
  const { setActiveTab } = useAppStore();
  const { addAssistantMessage } = useChatStore();

  const blockingCount = data.issues.filter((i: AuditIssue) => i.severity === 'high').length;
  const warningCount = data.issues.filter((i: AuditIssue) => i.severity !== 'high').length;

  const handleViewDetails = () => {
    setActiveTab('audit');
    addAssistantMessage('已切换到审计报告标签页，你可以查看详细问题列表。');
  };

  return (
    <div className={cn(
      "rounded-xl border shadow-sm overflow-hidden",
      data.status === 'passed'
        ? "bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800"
        : "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800"
    )}>
      {/* Header */}
      <div className={cn(
        "px-4 py-3 flex items-center justify-between",
        data.status === 'passed'
          ? "bg-green-100 dark:bg-green-900/20"
          : "bg-red-100 dark:bg-red-900/20"
      )}>
        <div className="flex items-center gap-2">
          {data.status === 'passed' ? (
            <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
          )}
          <span className={cn(
            "font-semibold",
            data.status === 'passed'
              ? "text-green-700 dark:text-green-400"
              : "text-red-700 dark:text-red-400"
          )}>
            {data.status === 'passed' ? '审计通过' : `发现 ${blockingCount} 个阻塞问题`}
          </span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 rounded hover:bg-black/5 dark:hover:bg-white/5"
        >
          {expanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Content */}
      {expanded && (
        <div className="p-4 space-y-4">
          {/* Score */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-gray-600 dark:text-gray-400">
                质量评分
              </span>
              <span className={cn(
                "font-bold",
                data.score >= 90 ? "text-green-600" :
                data.score >= 70 ? "text-yellow-600" : "text-red-600"
              )}>
                {data.score}/100
              </span>
            </div>
            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full transition-all",
                  data.score >= 90 ? "bg-green-500" :
                  data.score >= 70 ? "bg-yellow-500" : "bg-red-500"
                )}
                style={{ width: `${data.score}%` }}
              />
            </div>
          </div>

          {/* Issues Summary */}
          <div className="flex gap-3">
            <div className="flex-1 p-2 rounded-lg bg-red-100 dark:bg-red-900/20 text-center">
              <p className="text-lg font-bold text-red-700 dark:text-red-400">
                {blockingCount}
              </p>
              <p className="text-xs text-red-600 dark:text-red-400">阻塞</p>
            </div>
            <div className="flex-1 p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/20 text-center">
              <p className="text-lg font-bold text-yellow-700 dark:text-yellow-400">
                {warningCount}
              </p>
              <p className="text-xs text-yellow-600 dark:text-yellow-400">警告</p>
            </div>
          </div>

          {/* Issues List */}
          {data.issues.length > 0 && (
            <div className="space-y-2">
              {data.issues.slice(0, 2).map((issue: AuditIssue) => (
                <div
                  key={issue.id}
                  className={cn(
                    "p-2 rounded-lg text-sm flex items-start gap-2",
                    issue.severity === 'high'
                      ? "bg-red-100/50 dark:bg-red-900/10"
                      : "bg-yellow-100/50 dark:bg-yellow-900/10"
                  )}
                >
                  {issue.severity === 'high' ? (
                    <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                  )}
                  <span className="text-gray-700 dark:text-gray-300 line-clamp-2">
                    {issue.description}
                  </span>
                </div>
              ))}
              {data.issues.length > 2 && (
                <p className="text-xs text-gray-500 text-center">
                  还有 {data.issues.length - 2} 个问题...
                </p>
              )}
            </div>
          )}

          {/* Actions */}
          <Button
            onClick={handleViewDetails}
            variant="outline"
            className="w-full gap-2"
          >
            在 Dashboard 查看详情
            <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
