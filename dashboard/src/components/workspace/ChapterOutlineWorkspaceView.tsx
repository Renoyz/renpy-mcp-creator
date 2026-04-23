import { useState, useCallback } from "react";
import type { ChapterOutline, ChapterOutlineEntry } from "@/context/ProjectContext";
import { CheckCircle2, Circle, Edit3, Save, AlertTriangle, Plus, Trash2, ArrowUp, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  outline: ChapterOutline | null;
  projectName: string;
  onSave: (name: string, outline: ChapterOutline) => Promise<void>;
  onConfirmChapter: (name: string, chapterId: string) => Promise<void>;
  error?: string | null;
}

const EMPTY_CHAPTER = (): ChapterOutlineEntry => ({
  chapter_id: `ch_${Date.now()}`,
  order: 1,
  chapter_name: "New Chapter",
  chapter_goal: "",
  key_conflict: "",
  emotional_arc: "",
  reveals: "",
  end_state: "",
  mood_or_pacing_bias: "",
  character_focus: [],
  relationship_shift: "",
  character_presentation_notes: "",
  confirmed: false,
});

export function ChapterOutlineWorkspaceView({ outline, projectName, onSave, onConfirmChapter, error }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ChapterOutline | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  const startEdit = useCallback(() => {
    setDraft(outline ? JSON.parse(JSON.stringify(outline)) : { chapters: [], updated_at: "" });
    setEditing(true);
  }, [outline]);

  const cancelEdit = useCallback(() => {
    setDraft(null);
    setEditing(false);
  }, []);

  const handleSave = useCallback(async () => {
    if (!draft) return;
    setSaving(true);
    try {
      await onSave(projectName, draft);
      setEditing(false);
      setDraft(null);
    } finally {
      setSaving(false);
    }
  }, [draft, projectName, onSave]);

  const handleConfirm = useCallback(
    async (chapterId: string) => {
      setConfirming(chapterId);
      try {
        await onConfirmChapter(projectName, chapterId);
      } finally {
        setConfirming(null);
      }
    },
    [projectName, onConfirmChapter]
  );

  const updateChapter = useCallback((idx: number, chapter: ChapterOutlineEntry) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = [...prev.chapters];
      next[idx] = chapter;
      return { ...prev, chapters: next };
    });
  }, []);

  const addChapter = useCallback(() => {
    setDraft((prev) => {
      if (!prev) return prev;
      const ch = EMPTY_CHAPTER();
      ch.order = prev.chapters.length + 1;
      return { ...prev, chapters: [...prev.chapters, ch] };
    });
  }, []);

  const removeChapter = useCallback((idx: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = prev.chapters.filter((_, i) => i !== idx);
      // Re-number
      next.forEach((ch, i) => {
        ch.order = i + 1;
      });
      return { ...prev, chapters: next };
    });
  }, []);

  const moveChapter = useCallback((idx: number, direction: -1 | 1) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = [...prev.chapters];
      const target = idx + direction;
      if (target < 0 || target >= next.length) return prev;
      [next[idx], next[target]] = [next[target], next[idx]];
      next.forEach((ch, i) => {
        ch.order = i + 1;
      });
      return { ...prev, chapters: next };
    });
  }, []);

  const working = editing && draft ? draft : outline;

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Failed to load Chapter Outline</h3>
          <p className="text-sm text-red-600 max-w-xs mx-auto">{error}</p>
        </div>
      </div>
    );
  }

  if (!working) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <Edit3 className="w-8 h-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No Chapter Outline yet</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">
            Chapter outline will be available after the Project Brief is confirmed.
          </p>
          {!editing && (
            <button
              onClick={startEdit}
              className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-4 py-2 text-xs font-medium text-white hover:bg-gray-800"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Create Outline
            </button>
          )}
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
            <h2 className="text-xl font-bold text-gray-900">Chapter Outline</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {working.chapters.length} chapter{working.chapters.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {editing ? (
              <>
                <button
                  onClick={cancelEdit}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {saving ? (
                    <span className="animate-spin">⏳</span>
                  ) : (
                    <Save className="w-3.5 h-3.5" />
                  )}
                  Save
                </button>
              </>
            ) : (
              <button
                onClick={startEdit}
                className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800"
              >
                <Edit3 className="w-3.5 h-3.5" />
                Edit
              </button>
            )}
          </div>
        </div>
        {editing && (
          <div className="mt-2 flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>Saving will reset all chapter confirmation flags — you will need to re-confirm each chapter.</span>
          </div>
        )}
      </div>

      {/* Chapters */}
      <div className="px-6 py-6 space-y-6 max-w-3xl">
        {working.chapters.map((chapter, idx) => (
          <ChapterCard
            key={chapter.chapter_id}
            chapter={chapter}
            index={idx}
            total={working.chapters.length}
            editing={editing}
            confirming={confirming === chapter.chapter_id}
            onUpdate={(ch) => updateChapter(idx, ch)}
            onConfirm={() => handleConfirm(chapter.chapter_id)}
            onRemove={() => removeChapter(idx)}
            onMoveUp={() => moveChapter(idx, -1)}
            onMoveDown={() => moveChapter(idx, 1)}
          />
        ))}
        {editing && (
          <button
            onClick={addChapter}
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-dashed border-gray-300 px-3 py-3 text-xs font-medium text-gray-600 hover:border-gray-400 hover:text-gray-800"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Chapter
          </button>
        )}
      </div>
    </div>
  );
}

function ChapterCard({
  chapter,
  index,
  total,
  editing,
  confirming,
  onUpdate,
  onConfirm,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  chapter: ChapterOutlineEntry;
  index: number;
  total: number;
  editing: boolean;
  confirming: boolean;
  onUpdate: (ch: ChapterOutlineEntry) => void;
  onConfirm: () => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}) {
  const updateField = useCallback(
    (field: keyof ChapterOutlineEntry, value: string | string[]) => {
      onUpdate({ ...chapter, [field]: value });
    },
    [chapter, onUpdate]
  );

  return (
    <div className={cn("rounded-xl border overflow-hidden", chapter.confirmed ? "border-green-200" : "border-gray-200")}>
      <div className={cn("px-4 py-3 border-b flex items-center justify-between", chapter.confirmed ? "bg-green-50/50" : "bg-gray-50")}>
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center font-semibold text-sm">
            {chapter.order}
          </div>
          {chapter.confirmed ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Circle className="h-4 w-4 text-gray-400" />
          )}
          {editing ? (
            <input
              type="text"
              value={chapter.chapter_name}
              onChange={(e) => updateField("chapter_name", e.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1 text-sm font-semibold text-gray-900 focus:border-blue-500 outline-none"
            />
          ) : (
            <h3 className="text-sm font-semibold text-gray-900">{chapter.chapter_name}</h3>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {editing && (
            <>
              <button
                onClick={onMoveUp}
                disabled={index === 0}
                className="rounded-md p-1 text-gray-500 hover:bg-gray-200 disabled:opacity-30"
                title="Move up"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={onMoveDown}
                disabled={index === total - 1}
                className="rounded-md p-1 text-gray-500 hover:bg-gray-200 disabled:opacity-30"
                title="Move down"
              >
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={onRemove}
                className="rounded-md p-1 text-red-500 hover:bg-red-50"
                title="Remove"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          {!editing && (
            <button
              onClick={onConfirm}
              disabled={confirming || chapter.confirmed}
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                chapter.confirmed
                  ? "bg-green-100 text-green-700 cursor-default"
                  : "bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
              )}
            >
              {confirming ? "..." : chapter.confirmed ? "Confirmed" : "Confirm"}
            </button>
          )}
        </div>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <TextField label="Chapter Goal" value={chapter.chapter_goal} editing={editing} onChange={(v) => updateField("chapter_goal", v)} />
        <TextField label="Key Conflict" value={chapter.key_conflict} editing={editing} onChange={(v) => updateField("key_conflict", v)} />
        <TextField label="Emotional Arc" value={chapter.emotional_arc} editing={editing} onChange={(v) => updateField("emotional_arc", v)} />
        <TextField label="Reveals" value={chapter.reveals} editing={editing} onChange={(v) => updateField("reveals", v)} />
        <TextField label="End State" value={chapter.end_state} editing={editing} onChange={(v) => updateField("end_state", v)} />
        <TextField label="Mood / Pacing Bias" value={chapter.mood_or_pacing_bias} editing={editing} onChange={(v) => updateField("mood_or_pacing_bias", v)} />
        <TextField label="Relationship Shift" value={chapter.relationship_shift} editing={editing} onChange={(v) => updateField("relationship_shift", v)} />
        <TextField label="Character Presentation Notes" value={chapter.character_presentation_notes} editing={editing} onChange={(v) => updateField("character_presentation_notes", v)} />
        <div className="md:col-span-2">
          <TagField label="Character Focus" tags={chapter.character_focus} editing={editing} onChange={(v) => updateField("character_focus", v)} />
        </div>
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  editing,
  onChange,
}: {
  label: string;
  value: string;
  editing: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {editing ? (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
        />
      ) : (
        <p className="text-sm text-gray-700">{value || <span className="text-gray-400 italic">Not set</span>}</p>
      )}
    </div>
  );
}

function TagField({
  label,
  tags,
  editing,
  onChange,
}: {
  label: string;
  tags: string[];
  editing: boolean;
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("");

  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag, i) => (
          <span key={i} className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
            {tag}
            {editing && (
              <button onClick={() => onChange(tags.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500">
                ×
              </button>
            )}
          </span>
        ))}
        {editing && (
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && input.trim()) {
                onChange([...tags, input.trim()]);
                setInput("");
              }
            }}
            placeholder="+ Add"
            className="w-20 rounded-md border border-gray-300 px-2 py-0.5 text-xs text-gray-900 focus:border-blue-500 outline-none"
          />
        )}
      </div>
    </div>
  );
}
