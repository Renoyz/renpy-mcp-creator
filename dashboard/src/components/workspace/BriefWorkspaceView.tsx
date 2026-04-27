import { useState, useCallback } from "react";
import type {
  ProjectBrief,
  CharacterIdentity,
  CharacterIdentityContent,
  RelationshipBaseline,
} from "@/context/ProjectContext";
import { CheckCircle2, Circle, Edit3, Save, AlertTriangle, Plus, Trash2, ArrowRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  brief: ProjectBrief | null;
  projectName: string;
  onSave: (name: string, brief: ProjectBrief) => Promise<void>;
  onConfirmCard: (name: string, cardKey: string) => Promise<void>;
  onProceedToOutline?: () => void;
  outlineDraftReady?: boolean;
  onContinueChapterIntake?: () => void;
  error?: string | null;
}

const TEXT_CARD_KEYS = [
  "core_premise",
  "audience_genre",
  "tone_themes",
  "visual_style",
  "world_rules",
  "core_cast",
  "constraints",
];

const ALL_CARD_KEYS = [
  ...TEXT_CARD_KEYS,
  "character_identity",
  "relationship_baselines",
];

const CARD_LABELS: Record<string, string> = {
  core_premise: "Core Premise",
  audience_genre: "Audience / Genre",
  tone_themes: "Tone / Themes",
  visual_style: "Visual Style",
  world_rules: "World Rules",
  core_cast: "Core Cast",
  character_identity: "Character Identity",
  relationship_baselines: "Relationship Baselines",
  constraints: "Constraints",
};

function isCharacterIdentityContent(
  content: unknown
): content is CharacterIdentityContent {
  return typeof content === "object" && content !== null && "characters" in content;
}

interface RelationshipBaselineContent {
  relationships: RelationshipBaseline[];
  [key: string]: unknown;
}

function isRelationshipBaselineContent(
  content: unknown
): content is RelationshipBaselineContent {
  return typeof content === "object" && content !== null && "relationships" in content;
}

function isAllCardsConfirmed(brief: ProjectBrief | null): boolean {
  if (!brief || !brief.cards) return false;
  return ALL_CARD_KEYS.every((key) => brief.cards[key]?.confirmed);
}

export function BriefWorkspaceView({
  brief,
  projectName,
  onSave,
  onConfirmCard,
  onProceedToOutline,
  outlineDraftReady = false,
  onContinueChapterIntake,
  error,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<ProjectBrief | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  const startEdit = useCallback(() => {
    setDraft(brief ? JSON.parse(JSON.stringify(brief)) : { cards: {}, updated_at: "" });
    setEditing(true);
  }, [brief]);

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
    async (cardKey: string) => {
      setConfirming(cardKey);
      try {
        await onConfirmCard(projectName, cardKey);
      } finally {
        setConfirming(null);
      }
    },
    [projectName, onConfirmCard]
  );

  const updateTextCard = useCallback((cardKey: string, value: string) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        cards: {
          ...prev.cards,
          [cardKey]: { ...(prev.cards[cardKey] || { confirmed: false }), content: value },
        },
      };
    });
  }, []);

  const updateCharacterIdentity = useCallback((content: CharacterIdentityContent) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        cards: {
          ...prev.cards,
          character_identity: {
            ...(prev.cards.character_identity || { confirmed: false }),
            content,
          },
        },
      };
    });
  }, []);

  const updateRelationshipBaselines = useCallback((content: RelationshipBaselineContent) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        cards: {
          ...prev.cards,
          relationship_baselines: {
            ...(prev.cards.relationship_baselines || { confirmed: false }),
            content,
          },
        },
      };
    });
  }, []);

  const working = editing && draft ? draft : brief;
  const confirmedCount = working ? ALL_CARD_KEYS.filter((key) => working.cards[key]?.confirmed).length : 0;
  const totalCount = ALL_CARD_KEYS.length;
  const remainingCount = Math.max(totalCount - confirmedCount, 0);
  const progressPercent = totalCount > 0 ? (confirmedCount / totalCount) * 100 : 0;

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-16 h-16 rounded-2xl bg-red-100 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Failed to load Project Brief</h3>
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
          <h3 className="text-lg font-semibold text-gray-900 mb-2">No Project Brief yet</h3>
          <p className="text-sm text-gray-500 max-w-xs mx-auto">
            Start by editing and saving your first project brief.
          </p>
          {!editing && (
            <button
              onClick={startEdit}
              className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-4 py-2 text-xs font-medium text-white hover:bg-gray-800"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Create Brief
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
            <h2 className="text-xl font-bold text-gray-900">Project Brief</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Define project-level requirements before chapter planning.
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
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
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
            <span>Saving will reset all confirmation flags. You will need to re-confirm each card.</span>
          </div>
        )}
        <div
          data-testid="brief-review-header"
          className="mt-4 grid gap-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 lg:grid-cols-[minmax(220px,1fr)_180px_160px]"
        >
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Review progress</p>
            <p className="mt-1 text-sm text-gray-700">
              Confirm the stable requirements before chapter outline review.
            </p>
          </div>
          <div>
            <p className="text-lg font-semibold text-gray-900">
              {confirmedCount} / {totalCount} confirmed
            </p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
          <div className="flex items-center justify-start lg:justify-end">
            <span className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-700">
              {remainingCount} remaining
            </span>
          </div>
        </div>
      </div>

      {/* Cards */}
      <div className="px-6 py-6 space-y-5 max-w-5xl">
        {/* Text cards */}
        {TEXT_CARD_KEYS.map((key) => {
          const card = working.cards[key];
          const content = typeof card?.content === "string" ? card.content : "";
          const confirmed = !!card?.confirmed;
          return (
            <CardSection
              key={key}
              label={CARD_LABELS[key] || key}
              confirmed={confirmed}
              editing={editing}
              onConfirm={() => handleConfirm(key)}
              confirming={confirming === key}
            >
              {editing ? (
                <textarea
                  value={content}
                  onChange={(e) => updateTextCard(key, e.target.value)}
                  rows={4}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-y"
                  placeholder={`Enter ${CARD_LABELS[key] || key}...`}
                />
              ) : (
                <p className="text-sm text-gray-700 whitespace-pre-wrap">
                  {content || <span className="text-gray-400 italic">Not set</span>}
                </p>
              )}
            </CardSection>
          );
        })}

        {/* Character Identity structured card */}
        <CharacterIdentityCard
          card={working.cards.character_identity}
          editing={editing}
          onConfirm={() => handleConfirm("character_identity")}
          confirming={confirming === "character_identity"}
          onUpdate={updateCharacterIdentity}
        />

        {/* Relationship Baselines structured card */}
        <RelationshipBaselinesCard
          card={working.cards.relationship_baselines}
          editing={editing}
          onConfirm={() => handleConfirm("relationship_baselines")}
          confirming={confirming === "relationship_baselines"}
          onUpdate={updateRelationshipBaselines}
        />

        {/* Next-step CTA when all cards are confirmed */}
        {isAllCardsConfirmed(working) && onProceedToOutline && !editing && (
          outlineDraftReady ? (
          <div className="rounded-lg border border-green-200 bg-green-50 p-5 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <h3 className="text-sm font-semibold text-green-800">
                Project Brief 已全部确认
              </h3>
            </div>
            <p className="text-xs text-green-700 mb-3">
              接下来请进入 Chapter Outline Review 确认章节大纲
            </p>
            <button
              onClick={onProceedToOutline}
              className="inline-flex items-center gap-1.5 rounded-md bg-green-700 px-4 py-2 text-xs font-medium text-white hover:bg-green-800"
            >
              <ArrowRight className="w-3.5 h-3.5" />
              Enter Chapter Outline Review
            </button>
          </div>
          ) : (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-5 text-center">
              <div className="flex items-center justify-center gap-2 mb-2">
                <CheckCircle2 className="h-5 w-5 text-blue-600" />
                <h3 className="text-sm font-semibold text-blue-800">Chapter Intake in progress</h3>
              </div>
              <p className="text-xs text-blue-700 mb-3">
                The Chapter Outline draft is not ready yet. Continue chapter intake until review can begin.
              </p>
              <div
                data-testid="outline-draft-progress"
                className="mx-auto mb-3 h-2 w-full max-w-xs overflow-hidden rounded-full bg-blue-100"
              >
                <div className="h-full w-1/2 animate-pulse rounded-full bg-blue-600" />
              </div>
              {onContinueChapterIntake && (
                <button
                  onClick={onContinueChapterIntake}
                  className="inline-flex items-center gap-1.5 rounded-md bg-blue-700 px-4 py-2 text-xs font-medium text-white hover:bg-blue-800"
                >
                  <ArrowRight className="w-3.5 h-3.5" />
                  Continue Chapter Intake
                </button>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
}

function CardSection({
  label,
  confirmed,
  editing,
  onConfirm,
  confirming,
  children,
}: {
  label: string;
  confirmed: boolean;
  editing: boolean;
  onConfirm: () => void;
  confirming: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-xl border overflow-hidden", confirmed ? "border-green-200" : "border-gray-200")}>
      <div className={cn("px-4 py-3 border-b flex items-center justify-between", confirmed ? "bg-green-50/50" : "bg-gray-50")}>
        <div className="flex items-center gap-2">
          {confirmed ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Circle className="h-4 w-4 text-gray-400" />
          )}
          <h3 className="text-sm font-semibold text-gray-900">{label}</h3>
        </div>
        {!editing && (
          <button
            onClick={onConfirm}
            disabled={confirming || confirmed}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              confirmed
                ? "bg-green-100 text-green-700 cursor-default"
                : "bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
            )}
          >
            {confirming ? "..." : confirmed ? "Confirmed" : "Confirm"}
          </button>
        )}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function CharacterIdentityCard({
  card,
  editing,
  onConfirm,
  confirming,
  onUpdate,
}: {
  card?: { content: unknown; confirmed?: boolean };
  editing: boolean;
  onConfirm: () => void;
  confirming: boolean;
  onUpdate: (content: CharacterIdentityContent) => void;
}) {
  const content = isCharacterIdentityContent(card?.content)
    ? card.content
    : { characters: [] };
  const confirmed = !!card?.confirmed;

  const updateCharacter = (idx: number, char: CharacterIdentity) => {
    const next = [...content.characters];
    next[idx] = char;
    onUpdate({ ...content, characters: next });
  };

  const addCharacter = () => {
    onUpdate({
      ...content,
      characters: [
        ...content.characters,
        {
          character_id: `char_${Date.now()}`,
          name: "",
          story_role: "",
          core_motivation: "",
          personality_anchors: [],
          visual_identity_anchors: [],
          forbidden_drift: [],
        },
      ],
    });
  };

  const removeCharacter = (idx: number) => {
    const next = content.characters.filter((_, i) => i !== idx);
    onUpdate({ ...content, characters: next });
  };

  return (
    <div className={cn("rounded-xl border overflow-hidden", confirmed ? "border-green-200" : "border-gray-200")}>
      <div className={cn("px-4 py-3 border-b flex items-center justify-between", confirmed ? "bg-green-50/50" : "bg-gray-50")}>
        <div className="flex items-center gap-2">
          {confirmed ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Circle className="h-4 w-4 text-gray-400" />
          )}
          <h3 className="text-sm font-semibold text-gray-900">Character Identity</h3>
        </div>
        {!editing && (
          <button
            onClick={onConfirm}
            disabled={confirming || confirmed}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              confirmed
                ? "bg-green-100 text-green-700 cursor-default"
                : "bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
            )}
          >
            {confirming ? "..." : confirmed ? "Confirmed" : "Confirm"}
          </button>
        )}
      </div>
      <div className="p-4 space-y-4">
        {content.characters.length === 0 && !editing && (
          <p className="text-sm text-gray-400 italic">No characters defined.</p>
        )}
        {content.characters.map((char, idx) => (
          <div key={char.character_id} className="rounded-lg border border-gray-200 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Character {idx + 1}</p>
              {editing && (
                <button
                  onClick={() => removeCharacter(idx)}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="h-3 w-3" />
                  Remove
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field
                label="Name"
                value={char.name}
                editing={editing}
                onChange={(v) => updateCharacter(idx, { ...char, name: v })}
              />
              <Field
                label="Story Role"
                value={char.story_role}
                editing={editing}
                onChange={(v) => updateCharacter(idx, { ...char, story_role: v })}
              />
              <Field
                label="Core Motivation"
                value={char.core_motivation}
                editing={editing}
                onChange={(v) => updateCharacter(idx, { ...char, core_motivation: v })}
              />
            </div>
            <TagList
              label="Personality Anchors"
              tags={char.personality_anchors}
              editing={editing}
              onChange={(tags) => updateCharacter(idx, { ...char, personality_anchors: tags })}
            />
            <TagList
              label="Visual Identity Anchors"
              tags={char.visual_identity_anchors}
              editing={editing}
              onChange={(tags) => updateCharacter(idx, { ...char, visual_identity_anchors: tags })}
            />
            <TagList
              label="Forbidden Drift"
              tags={char.forbidden_drift}
              editing={editing}
              onChange={(tags) => updateCharacter(idx, { ...char, forbidden_drift: tags })}
            />
          </div>
        ))}
        {editing && (
          <button
            onClick={addCharacter}
            className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-gray-300 px-3 py-2 text-xs font-medium text-gray-600 hover:border-gray-400 hover:text-gray-800"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Character
          </button>
        )}
      </div>
    </div>
  );
}

function RelationshipBaselinesCard({
  card,
  editing,
  onConfirm,
  confirming,
  onUpdate,
}: {
  card?: { content: unknown; confirmed?: boolean };
  editing: boolean;
  onConfirm: () => void;
  confirming: boolean;
  onUpdate: (content: RelationshipBaselineContent) => void;
}) {
  const content = isRelationshipBaselineContent(card?.content)
    ? card.content
    : { relationships: [] };
  const confirmed = !!card?.confirmed;

  const updateRelationship = (idx: number, rel: RelationshipBaseline) => {
    const next = [...content.relationships];
    next[idx] = rel;
    onUpdate({ ...content, relationships: next });
  };

  const addRelationship = () => {
    onUpdate({
      ...content,
      relationships: [
        ...content.relationships,
        { pair: ["", ""], baseline: "", must_preserve: [] },
      ],
    });
  };

  const removeRelationship = (idx: number) => {
    const next = content.relationships.filter((_, i) => i !== idx);
    onUpdate({ ...content, relationships: next });
  };

  return (
    <div data-testid="relationship-baselines-card" className={cn("rounded-xl border overflow-hidden", confirmed ? "border-green-200" : "border-gray-200")}>
      <div className={cn("px-4 py-3 border-b flex items-center justify-between", confirmed ? "bg-green-50/50" : "bg-gray-50")}>
        <div className="flex items-center gap-2">
          {confirmed ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Circle className="h-4 w-4 text-gray-400" />
          )}
          <h3 className="text-sm font-semibold text-gray-900">Relationship Baselines</h3>
        </div>
        {!editing && (
          <button
            onClick={onConfirm}
            disabled={confirming || confirmed}
            data-testid="confirm-relationship-baselines"
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              confirmed
                ? "bg-green-100 text-green-700 cursor-default"
                : "bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
            )}
          >
            {confirming ? "..." : confirmed ? "Confirmed" : "Confirm"}
          </button>
        )}
      </div>
      <div className="p-4 space-y-4">
        {content.relationships.length === 0 && !editing && (
          <p className="text-sm text-gray-400 italic">No relationship baselines defined.</p>
        )}
        {content.relationships.map((rel, idx) => (
          <div key={idx} className="rounded-lg border border-gray-200 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Relationship {idx + 1}</p>
              {editing && (
                <button
                  onClick={() => removeRelationship(idx)}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50"
                >
                  <Trash2 className="h-3 w-3" />
                  Remove
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field
                label="Character A"
                value={rel.pair[0] || ""}
                editing={editing}
                onChange={(v) => updateRelationship(idx, { ...rel, pair: [v, rel.pair[1] || ""] })}
              />
              <Field
                label="Character B"
                value={rel.pair[1] || ""}
                editing={editing}
                onChange={(v) => updateRelationship(idx, { ...rel, pair: [rel.pair[0] || "", v] })}
              />
            </div>
            <Field
              label="Baseline"
              value={rel.baseline}
              editing={editing}
              onChange={(v) => updateRelationship(idx, { ...rel, baseline: v })}
              dataTestId="baseline-input"
            />
            <TagList
              label="Must Preserve"
              tags={rel.must_preserve}
              editing={editing}
              onChange={(tags) => updateRelationship(idx, { ...rel, must_preserve: tags })}
            />
          </div>
        ))}
        {editing && (
          <button
            onClick={addRelationship}
            className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-gray-300 px-3 py-2 text-xs font-medium text-gray-600 hover:border-gray-400 hover:text-gray-800"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Relationship
          </button>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  editing,
  onChange,
  dataTestId,
}: {
  label: string;
  value: string;
  editing: boolean;
  onChange: (v: string) => void;
  dataTestId?: string;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {editing ? (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={dataTestId}
          className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
        />
      ) : (
        <p className="text-sm text-gray-900">{value || <span className="text-gray-400">Not set</span>}</p>
      )}
    </div>
  );
}

function TagList({
  label,
  tags,
  editing,
  onChange,
}: {
  label: string;
  tags: string[];
  editing: boolean;
  onChange: (tags: string[]) => void;
}) {
  const [input, setInput] = useState("");

  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
          >
            {tag}
            {editing && (
              <button
                onClick={() => onChange(tags.filter((_, j) => j !== i))}
                className="text-gray-400 hover:text-red-500"
              >
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
