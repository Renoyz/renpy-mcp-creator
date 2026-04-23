import type { RefinementStatus } from "@/context/ProjectContext";
import { AlertCircle, CheckCircle2, Lock, Unlock } from "lucide-react";
import { useState } from "react";

interface Props {
  status: RefinementStatus | null;
  error?: string | null;
  onFreeze?: (() => Promise<void>) | null;
}

export function RefinementStatusPanel({ status, error, onFreeze }: Props) {
  const [freezePending, setFreezePending] = useState(false);

  if (error) {
    return (
      <div className="rounded-md border px-4 py-3 text-sm bg-red-50 text-red-700 border-red-200">
        <div className="flex items-center gap-3">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <div className="flex-1">
            <div className="font-medium">Failed to load refinement status</div>
            <p className="text-xs mt-0.5 opacity-80">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!status) {
    return null;
  }

  const {
    refinement_state,
    brief_fully_confirmed,
    outline_fully_confirmed,
    blueprint_ready,
    freeze_allowed,
    blueprint_freeze_status,
    generation_allowed,
  } = status;

  // Legacy: no brief/outline but generation_allowed (has blueprint)
  const isLegacy =
    !refinement_state && generation_allowed;

  let blockedMessage: string | null = null;
  let statusLabel = "";
  let statusColor = "";

  if (isLegacy) {
    statusLabel = "Legacy blueprint";
    statusColor = "bg-green-50 text-green-700 border-green-200";
  } else if (blueprint_ready && blueprint_freeze_status === "frozen") {
    statusLabel = "Ready for generation";
    statusColor = "bg-green-50 text-green-700 border-green-200";
  } else if (blueprint_freeze_status === "stale") {
    statusLabel = "Blueprint stale";
    statusColor = "bg-amber-50 text-amber-700 border-amber-200";
    blockedMessage = "Project Brief or Chapter Outline changed. Freeze Blueprint again.";
  } else if (blueprint_ready) {
    statusLabel = "Ready to freeze";
    statusColor = "bg-blue-50 text-blue-700 border-blue-200";
    blockedMessage = "Freeze the blueprint to unlock generation";
  } else if (!brief_fully_confirmed) {
    statusLabel = "Planning";
    statusColor = "bg-amber-50 text-amber-700 border-amber-200";
    blockedMessage = "Complete all Project Brief cards first";
  } else if (!outline_fully_confirmed) {
    statusLabel = "Reviewing chapters";
    statusColor = "bg-amber-50 text-amber-700 border-amber-200";
    blockedMessage = "Complete all Chapter Outline cards first";
  } else {
    statusLabel = "Reviewing";
    statusColor = "bg-gray-50 text-gray-700 border-gray-200";
  }

  const canFreeze = !!onFreeze && !isLegacy && freeze_allowed && blueprint_freeze_status !== "frozen";

  return (
    <div className={`rounded-md border px-4 py-3 text-sm ${statusColor}`}>
      <div className="flex items-center gap-3">
        {blueprint_ready || generation_allowed ? (
          <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
        ) : (
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
        )}
        <div className="flex-1">
          <div className="flex items-center gap-2 font-medium">
            <span>{statusLabel}</span>
            {refinement_state && (
              <span className="text-xs opacity-70">({refinement_state})</span>
            )}
            {isLegacy && (
              <span className="text-xs opacity-70">(legacy blueprint)</span>
            )}
          </div>
          {blockedMessage && (
            <p className="text-xs mt-0.5 opacity-80">{blockedMessage}</p>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs">
          {canFreeze && (
            <button
              type="button"
              onClick={async () => {
                if (!onFreeze) return;
                setFreezePending(true);
                try {
                  await onFreeze();
                } finally {
                  setFreezePending(false);
                }
              }}
              disabled={freezePending}
              className="rounded-md border border-current px-2 py-1 font-medium disabled:opacity-60"
            >
              {freezePending ? "Freezing..." : "Freeze Blueprint"}
            </button>
          )}
          <div className="flex items-center gap-1">
            {brief_fully_confirmed ? (
              <Unlock className="h-3 w-3" />
            ) : (
              <Lock className="h-3 w-3" />
            )}
            <span>Brief</span>
          </div>
          <div className="flex items-center gap-1">
            {outline_fully_confirmed ? (
              <Unlock className="h-3 w-3" />
            ) : (
              <Lock className="h-3 w-3" />
            )}
            <span>Outline</span>
          </div>
        </div>
      </div>
    </div>
  );
}
