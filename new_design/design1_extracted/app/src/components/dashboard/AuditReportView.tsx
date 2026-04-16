import { useAppStore } from '@/store/useAppStore';
import { AlertTriangle, AlertCircle, CheckCircle2, FileWarning, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { AuditIssue } from '@/types';

export function AuditReportView() {
  const { auditReport, setSelectedScene } = useAppStore();

  if (!auditReport) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500">
        <CheckCircle2 className="w-16 h-16 mb-4 text-green-400" />
        <p>暂无审计报告</p>
        <p className="text-sm">所有章节已通过审计</p>
      </div>
    );
  }

  const blockingIssues = auditReport.issues.filter((i: AuditIssue) => i.severity === 'high');
  const warningIssues = auditReport.issues.filter((i: AuditIssue) => i.severity === 'medium' || i.severity === 'low');

  const handleJumpToScene = (sceneId: string) => {
    setSelectedScene(sceneId);
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className={cn(
            "w-12 h-12 rounded-xl flex items-center justify-center",
            auditReport.status === 'passed'
              ? "bg-green-100 dark:bg-green-900/30"
              : "bg-red-100 dark:bg-red-900/30"
          )}>
            {auditReport.status === 'passed' ? (
              <CheckCircle2 className="w-6 h-6 text-green-600 dark:text-green-400" />
            ) : (
              <AlertTriangle className="w-6 h-6 text-red-600 dark:text-red-400" />
            )}
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              审计报告
            </h2>
            <p className="text-sm text-gray-500">
              第一章 · 总分 {auditReport.overallScore}/100
            </p>
          </div>
        </div>

        {/* Score Bar */}
        <div className="w-full h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all duration-500",
              auditReport.overallScore >= 90 ? "bg-green-500" :
              auditReport.overallScore >= 70 ? "bg-yellow-500" : "bg-red-500"
            )}
            style={{ width: `${auditReport.overallScore}%` }}
          />
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <span className="font-semibold text-red-700 dark:text-red-400">
              阻塞问题
            </span>
          </div>
          <p className="text-2xl font-bold text-red-700 dark:text-red-400">
            {blockingIssues.length}
          </p>
        </div>

        <div className="p-4 rounded-xl bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800">
          <div className="flex items-center gap-2 mb-2">
            <FileWarning className="w-5 h-5 text-yellow-500" />
            <span className="font-semibold text-yellow-700 dark:text-yellow-400">
              警告
            </span>
          </div>
          <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-400">
            {warningIssues.length}
          </p>
        </div>
      </div>

      {/* Issues List */}
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          问题列表
        </h3>

        {auditReport.issues.map((issue: AuditIssue) => (
          <div
            key={issue.id}
            className={cn(
              "p-4 rounded-xl border shadow-sm",
              issue.severity === 'high'
                ? "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800"
                : "bg-yellow-50 dark:bg-yellow-900/10 border-yellow-200 dark:border-yellow-800"
            )}
          >
            <div className="flex items-start gap-3">
              {issue.severity === 'high' ? (
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              ) : (
                <FileWarning className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <p className={cn(
                  "text-sm font-medium",
                  issue.severity === 'high'
                    ? "text-red-700 dark:text-red-400"
                    : "text-yellow-700 dark:text-yellow-400"
                )}>
                  {issue.severity === 'high' ? '阻塞问题' : '警告'}
                  {issue.type && ` · ${issue.type}`}
                </p>
                <p className="text-gray-700 dark:text-gray-300 mt-1">
                  {issue.description}
                </p>
                {issue.suggestion && (
                  <p className="text-sm text-gray-500 mt-1">
                    建议：{issue.suggestion}
                  </p>
                )}
                {issue.sceneId && (
                  <div className="mt-3 flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleJumpToScene(issue.sceneId!)}
                      className="gap-1"
                    >
                      跳转脚本
                      <ArrowRight className="w-3 h-3" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
