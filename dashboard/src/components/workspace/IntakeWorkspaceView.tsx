import type { RefinementIntake } from "@/context/ProjectContext";
import { AlertCircle, Bot, CheckCircle2, MessageSquarePlus } from "lucide-react";

interface Props {
  intake: RefinementIntake | null;
  error?: string | null;
  projectName: string;
  onPromoteBriefDraft: (projectName: string) => Promise<void>;
  onStartAI?: () => void;
}

function formatSlotLabel(key: string): string {
  return key
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function IntakeWorkspaceView({
  intake,
  error,
  projectName,
  onPromoteBriefDraft,
  onStartAI,
}: Props) {
  if (error) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
            <div>
              <h2 className="text-sm font-semibold">Failed to load refinement intake</h2>
              <p className="mt-1 text-sm opacity-90">{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!intake) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-6">
          <div className="flex items-start gap-3">
            <Bot className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600" />
            <div className="flex-1">
              <h2 className="text-base font-semibold text-gray-900">Start Project Intake</h2>
              <p className="mt-1 text-sm text-gray-600">
                Let the agent ask a few project-level questions first. This intake step builds the first Project Brief
                draft before you enter structured review.
              </p>
              <button
                type="button"
                onClick={onStartAI}
                className="mt-4 inline-flex items-center gap-2 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                <MessageSquarePlus className="h-4 w-4" />
                Start Intake with AI
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-4xl space-y-6">
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900">Agent Intake</h2>
              <p className="mt-1 text-sm text-gray-500">
                Phase: <span className="font-medium text-gray-700">{intake.phase}</span>
              </p>
            </div>
            {intake.brief_draft_ready && (
              <button
                type="button"
                onClick={() => void onPromoteBriefDraft(projectName)}
                data-testid="promote-brief-draft"
                className="inline-flex items-center gap-2 rounded-md bg-green-600 px-3 py-2 text-sm font-medium text-white hover:bg-green-700"
              >
                <CheckCircle2 className="h-4 w-4" />
                Enter Brief Review
              </button>
            )}
          </div>
          <div className="mt-4 rounded-md bg-gray-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Current understanding</div>
            <p className="mt-2 text-sm text-gray-700">
              {intake.current_summary || "The agent has started intake but has not assembled a usable summary yet."}
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-900">Missing slots</h3>
          {intake.missing_slots.length === 0 ? (
            <p className="mt-2 text-sm text-green-700">No required slots are currently missing.</p>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              {intake.missing_slots.map((slot) => (
                <span
                  key={slot}
                  className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800"
                >
                  {formatSlotLabel(slot)}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-900">Draft slots</h3>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {Object.entries(intake.slots).map(([key, slot]) => (
              <div key={key} className="rounded-md border border-gray-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-gray-900">{formatSlotLabel(key)}</div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      slot.complete ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {slot.complete ? "Complete" : "Missing"}
                  </span>
                </div>
                <div className="mt-2 text-sm text-gray-600 break-words">
                  {slot.value == null || slot.value === ""
                    ? "No value collected yet."
                    : typeof slot.value === "string"
                    ? slot.value
                    : JSON.stringify(slot.value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
