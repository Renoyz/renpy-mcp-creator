import { AlertCircle, ArrowRight, CheckCircle2, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { WorkflowAction, WorkflowDashboardState } from "./workflowState"

interface Props {
  workflow: WorkflowDashboardState
  projectName: string
  metaLine?: React.ReactNode
  statusNote?: React.ReactNode
  secondaryActions?: React.ReactNode
  onAction: (action: WorkflowAction) => void
}

const statusTone = {
  locked: "border-gray-200 bg-white text-gray-700",
  ready: "border-indigo-200 bg-indigo-50 text-indigo-950",
  running: "border-blue-200 bg-blue-50 text-blue-950",
  needs_review: "border-amber-200 bg-amber-50 text-amber-950",
  done: "border-emerald-200 bg-emerald-50 text-emerald-950",
  failed: "border-red-200 bg-red-50 text-red-950",
}

function StatusIcon({ status }: { status: WorkflowDashboardState["status"] }) {
  if (status === "running") return <Loader2 className="h-5 w-5 animate-spin" />
  if (status === "failed") return <AlertCircle className="h-5 w-5" />
  return <CheckCircle2 className="h-5 w-5" />
}

export function WorkflowStatusHeader({
  workflow,
  projectName,
  metaLine,
  statusNote,
  secondaryActions,
  onAction,
}: Props) {
  return (
    <section
      data-testid="workflow-status-header"
      className={cn("rounded-lg border px-4 py-3", statusTone[workflow.status])}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide opacity-70">
            <span>
              第 {workflow.currentStep} 步 / 共 {workflow.totalSteps} 步
            </span>
            <span>/</span>
            <span>{projectName}</span>
          </div>
          <div className="mt-2 flex items-start gap-2.5">
            <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-white/75">
              <StatusIcon status={workflow.status} />
            </span>
            <div className="min-w-0">
              <h2 className="text-lg font-semibold tracking-tight">{workflow.title}</h2>
              <p className="mt-1 max-w-3xl text-sm opacity-80">{workflow.subtitle}</p>
              {(metaLine || statusNote) && (
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs opacity-85">
                  {statusNote}
                  {metaLine && <span>{metaLine}</span>}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {secondaryActions}
          <button
            type="button"
            aria-label={`Primary action: ${workflow.primaryAction.label}`}
            disabled={workflow.primaryAction.disabled}
            onClick={() => onAction(workflow.primaryAction.action)}
            className="inline-flex items-center gap-2 rounded-md bg-gray-950 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {workflow.primaryAction.label}
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/70">
        <div
          className="h-full rounded-full bg-indigo-600 transition-all"
          style={{ width: `${workflow.progressPercent}%` }}
        />
      </div>
    </section>
  )
}
