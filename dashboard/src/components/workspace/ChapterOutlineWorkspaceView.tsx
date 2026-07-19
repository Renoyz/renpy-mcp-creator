import { useState, useCallback } from "react";
import type { ChapterOutline, ChapterOutlineEntry } from "@/context/ProjectContext";
import { CheckCircle2, Circle, Edit3, Save, AlertTriangle, Plus, Trash2, ArrowUp, ArrowDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  outline: ChapterOutline | null;
  projectName: string;
  onSave: (name: string, outline: ChapterOutline) => Promise<void>;
  onConfirmChapter: (name: string, chapterId: string) => Promise<void>;
  onFreezeBlueprint?: () => void;
  error?: string | null;
}

const EMPTY_CHAPTER = (): ChapterOutlineEntry => ({
  chapter_id: `ch_${Date.now()}`,
  order: 1,
  chapter_name: "新章节",
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

export function ChapterOutlineWorkspaceView({ outline, projectName, onSave, onConfirmChapter, onFreezeBlueprint, error }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ChapterOutline | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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
    setActionError(null);
    try {
      await onSave(projectName, draft);
      setEditing(false);
      setDraft(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "保存章节大纲失败。");
    } finally {
      setSaving(false);
    }
  }, [draft, projectName, onSave]);

  const handleConfirm = useCallback(
    async (chapterId: string) => {
      setConfirming(chapterId);
      setActionError(null);
      try {
        await onConfirmChapter(projectName, chapterId);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "确认章节失败。");
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
  const confirmedCount = working?.chapters.filter((chapter) => chapter.confirmed).length ?? 0;
  const totalCount = working?.chapters.length ?? 0;
  const remainingCount = Math.max(totalCount - confirmedCount, 0);
  const progressPercent = totalCount > 0 ? (confirmedCount / totalCount) * 100 : 0;

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">加载章节大纲失败</h3>
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
          <h3 className="text-lg font-semibold text-gray-900 mb-2">还没有章节大纲</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">
            项目简报确认后，即可查看章节大纲。
          </p>
          {!editing && (
            <button
              onClick={startEdit}
              className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-4 py-2 text-xs font-medium text-white hover:bg-gray-800"
            >
              <Edit3 className="w-3.5 h-3.5" />
              创建大纲
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
            <h2 className="text-xl font-bold text-gray-900">章节大纲</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {working.chapters.length} 个章节
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
                  取消
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="w-3.5 h-3.5" />
                  )}
                  保存
                </button>
              </>
            ) : (
              <button
                onClick={startEdit}
                className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-800"
              >
                <Edit3 className="w-3.5 h-3.5" />
                编辑
              </button>
            )}
          </div>
        </div>
        {editing && (
          <div className="mt-2 flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>保存将重置所有章节确认标记，你需要重新确认每个章节。</span>
          </div>
        )}
        {actionError && (
          <div data-testid="outline-action-error" className="mt-2 flex items-start gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>{actionError}</span>
          </div>
        )}
        <div
          data-testid="outline-review-header"
          className="mt-4 grid gap-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_220px_160px]"
        >
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">确认进度</p>
            <p className="mt-1 text-sm text-gray-700">
              冻结蓝图并开始生成前，请先确认每个章节。
            </p>
          </div>
          <div>
            <p className="text-lg font-semibold text-gray-900">
              {confirmedCount} / {totalCount} 个章节已确认
            </p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
          <div className="flex items-center justify-start lg:justify-end">
            <span className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-700">
              剩余 {remainingCount} 章
            </span>
          </div>
        </div>
      </div>

      {/* Chapters */}
      <div className="px-6 py-6 space-y-5 max-w-5xl">
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
            添加章节
          </button>
        )}
        {!editing && onFreezeBlueprint && working.chapters.length > 0 && working.chapters.every((ch) => ch.confirmed) && (
          <div className="rounded-xl border border-green-200 bg-green-50 p-5 text-center">
            <p className="text-sm font-medium text-green-800 mb-3">
              所有章节已确认，可以冻结蓝图并开始生成。
            </p>
            <button
              onClick={onFreezeBlueprint}
              className="inline-flex items-center gap-1.5 rounded-md bg-green-700 px-4 py-2 text-xs font-medium text-white hover:bg-green-800"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              冻结蓝图
            </button>
          </div>
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
                title="上移"
              >
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={onMoveDown}
                disabled={index === total - 1}
                className="rounded-md p-1 text-gray-500 hover:bg-gray-200 disabled:opacity-30"
                title="下移"
              >
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={onRemove}
                className="rounded-md p-1 text-red-500 hover:bg-red-50"
                title="移除"
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
              {confirming ? "..." : chapter.confirmed ? "已确认" : "确认"}
            </button>
          )}
        </div>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <TextField label="章节目标" value={chapter.chapter_goal} editing={editing} onChange={(v) => updateField("chapter_goal", v)} />
        <TextField label="核心冲突" value={chapter.key_conflict} editing={editing} onChange={(v) => updateField("key_conflict", v)} />
        <TextField label="情感弧线" value={chapter.emotional_arc} editing={editing} onChange={(v) => updateField("emotional_arc", v)} />
        <TextField label="揭示信息" value={chapter.reveals} editing={editing} onChange={(v) => updateField("reveals", v)} />
        <TextField label="结束状态" value={chapter.end_state} editing={editing} onChange={(v) => updateField("end_state", v)} />
        <TextField label="情绪 / 节奏偏好" value={chapter.mood_or_pacing_bias} editing={editing} onChange={(v) => updateField("mood_or_pacing_bias", v)} />
        <TextField label="关系变化" value={chapter.relationship_shift} editing={editing} onChange={(v) => updateField("relationship_shift", v)} />
        <TextField label="角色呈现备注" value={chapter.character_presentation_notes} editing={editing} onChange={(v) => updateField("character_presentation_notes", v)} />
        <div className="md:col-span-2">
          <TagField label="角色焦点" tags={chapter.character_focus} editing={editing} onChange={(v) => updateField("character_focus", v)} />
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
        <p className="text-sm text-gray-700">{value || <span className="text-gray-400 italic">未填写</span>}</p>
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
            placeholder="+ 添加"
            className="w-20 rounded-md border border-gray-300 px-2 py-0.5 text-xs text-gray-900 focus:border-blue-500 outline-none"
          />
        )}
      </div>
    </div>
  );
}
