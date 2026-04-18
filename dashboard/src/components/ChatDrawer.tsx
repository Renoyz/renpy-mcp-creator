import { useEffect, useRef, useState } from "react";
import { Send, X, Bot, User, Loader2, Wrench, CheckCircle2, CheckCircle, RefreshCw, Sparkles } from "lucide-react";
import { useProject } from "../context/ProjectContext";

export type MessageType =
  | "user"
  | "assistant"
  | "tool_start"
  | "tool_result"
  | "error"
  | "blueprint_draft"
  | "confirmation_request"
  | "progress";

export interface ChatMessage {
  id: string;
  type: MessageType;
  content: string;
  toolName?: string;
  imageUrl?: string;
  draft?: any;
  confirmationId?: string;
  step?: string;
  percent?: number;
  timestamp: number;
}

export interface PendingConfirmation {
  confirmationId: string;
  message: string;
  candidates: { type: string; path: string }[];
  projectName?: string;
}

interface ChatDrawerProps {
  open?: boolean;
  onClose?: () => void;
  wsUrl?: string;
  mode?: "overlay" | "docked";
}

const summarizeToolResult = (content: string): string | null => {
  try {
    const parsed = JSON.parse(content);
    if (parsed?.success && typeof parsed?.message === "string" && parsed.message.trim()) {
      return parsed.message;
    }
    if (parsed?.image_type === "background") {
      const first =
        parsed.relative_files?.[0] ?? parsed.files?.[0] ?? parsed.primary_file ?? null;
      return first ? `Background saved to ${first}` : "Background saved.";
    }
    if (parsed?.image_type === "character") {
      const first =
        parsed.transparent_files?.[0] ??
        parsed.relative_files?.[0] ??
        parsed.files?.[0] ??
        parsed.primary_file ??
        null;
      return first ? `Character sprite saved to ${first}` : "Character sprite saved.";
    }
  } catch {
    return null;
  }
  return null;
};

function convertHistoryToMessages(history: any[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  const genId = () => `${Date.now()}_${Math.random()}`;
  for (const msg of history) {
    const role = msg.role;
    const content = msg.content;
    if (role === "user") {
      if (typeof content === "string" && content.trim()) {
        result.push({ id: genId(), type: "user", content, timestamp: Date.now() });
      } else if (Array.isArray(content)) {
        for (const block of content) {
          if (block.type === "tool_result") {
            const toolContent = block.content || "";
            let parsed: any = null;
            try {
              parsed = JSON.parse(toolContent);
            } catch {
              parsed = null;
            }
            if (parsed?.primary_preview_url) {
              const label =
                parsed.image_type === "background"
                  ? "Background generated"
                  : "Character sprite generated";
              result.push({
                id: genId(),
                type: "assistant",
                content: label,
                imageUrl: parsed.primary_preview_url,
                timestamp: Date.now(),
              });
            } else {
              const summary = summarizeToolResult(toolContent);
              if (summary) {
                result.push({ id: genId(), type: "assistant", content: summary, timestamp: Date.now() });
              }
            }
          }
        }
      }
    } else if (role === "assistant") {
      if (Array.isArray(content)) {
        const textParts: string[] = [];
        for (const block of content) {
          if (block.type === "text") {
            textParts.push(block.text || "");
          }
        }
        const joined = textParts.join("");
        if (joined.trim()) {
          result.push({ id: genId(), type: "assistant", content: joined, timestamp: Date.now() });
        }
      } else if (typeof content === "string" && content.trim()) {
        result.push({ id: genId(), type: "assistant", content, timestamp: Date.now() });
      }
    }
  }
  return result;
}

function convertEventToChatMessage(event: any): ChatMessage | null {
  const id = `${Date.now()}_${Math.random()}`;
  const ts = Date.now();

  if (["message", "blueprint_draft", "confirmation_request", "progress", "error"].includes(event.type)) {
    if (event.type === "message") {
      const msgKind = event.message_kind;
      if (msgKind === "blueprint_draft") {
        return {
          id,
          type: "blueprint_draft",
          content: event.content || "蓝图草案已生成，请查看并确认。",
          draft: event.draft,
          timestamp: ts,
        };
      }
      return {
        id,
        type: event.role === "user" ? "user" : "assistant",
        content: String(event.content ?? ""),
        timestamp: ts,
      };
    }
    if (event.type === "blueprint_draft") {
      return {
        id,
        type: "blueprint_draft",
        content: "蓝图草案已生成，请查看并确认。",
        draft: event.draft,
        timestamp: ts,
      };
    }
    if (event.type === "confirmation_request") {
      return {
        id,
        type: "confirmation_request",
        content: event.message || "请确认以下蓝图草案。",
        draft: event.draft,
        confirmationId: event.confirmation_id,
        timestamp: ts,
      };
    }
    if (event.type === "progress") {
      return {
        id,
        type: "progress",
        content: event.step || "",
        step: event.step,
        percent: event.percent,
        timestamp: ts,
      };
    }
    if (event.type === "error") {
      return { id, type: "error", content: event.message || "Error", timestamp: ts };
    }
  }

  if (event.type === "assistant_delta") {
    return { id, type: "assistant", content: event.content || event.delta || "", timestamp: ts };
  }

  if (event.type === "tool_start") {
    return null; // tool_start is not displayed as a separate message
  }

  if (event.type === "tool_result") {
    if (event.result?.success) {
      let parsed: any = null;
      try {
        parsed = JSON.parse(event.result.content || "{}");
      } catch {
        parsed = null;
      }
      if (parsed?.primary_preview_url) {
        const label =
          parsed.image_type === "background"
            ? "Background generated"
            : "Character sprite generated";
        return { id, type: "assistant", content: label, imageUrl: parsed.primary_preview_url, timestamp: ts };
      } else {
        const summary = summarizeToolResult(event.result.content || "");
        if (summary) {
          return { id, type: "assistant", content: summary, timestamp: ts };
        }
      }
    }
    return null;
  }

  return null;
}

export function ChatDrawer({ open, onClose, wsUrl, mode = "overlay" }: ChatDrawerProps) {
  const isDocked = mode === "docked";
  const effectiveOpen = isDocked ? true : (open ?? false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [blueprintConfirmationId, setBlueprintConfirmationId] = useState<string | null>(null);
  const [reconnectKey, setReconnectKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const historyRequestIdRef = useRef(0);
  const { currentProject, blueprintPhase, blueprintDraft, handleBlueprintEvent, sendBlueprintConfirmation, registerBlueprintConfirmationSender, registerBlueprintStartSender } = useProject();
  const isInterviewMode = blueprintPhase === "collecting" || blueprintPhase === "reviewing";
  const isReviewing = blueprintPhase === "reviewing";

  const displayMessages = messages;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages]);

  useEffect(() => {
    if (!effectiveOpen || !currentProject?.name) {
      if (!currentProject?.name) setMessages([]);
      return;
    }
    historyRequestIdRef.current += 1;
    const requestId = historyRequestIdRef.current;
    setMessages([]);
    const controller = new AbortController();
    fetch(`/api/projects/${encodeURIComponent(currentProject.name)}/chat/history`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.resolve({ messages: [] })))
      .then((data) => {
        if (historyRequestIdRef.current !== requestId) return;
        const history = Array.isArray(data.messages) ? data.messages : [];
        setMessages(convertHistoryToMessages(history));
      })
      .catch((err) => {
        if (historyRequestIdRef.current !== requestId) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setMessages([]);
      });
    return () => {
      controller.abort();
    };
  }, [open, currentProject?.name]);

  useEffect(() => {
    const handleProjectChange = () => {
      if (effectiveOpen && wsRef.current) {
        wsRef.current.close();
        setReconnectKey((k) => k + 1);
      }
    };
    window.addEventListener("project-changed", handleProjectChange);
    return () => {
      window.removeEventListener("project-changed", handleProjectChange);
    };
  }, [effectiveOpen]);

  const pendingWsConfirmationRef = useRef<boolean | null>(null);
  const blueprintConfirmationIdRef = useRef<string | null>(null);

  useEffect(() => {
    blueprintConfirmationIdRef.current = blueprintConfirmationId;
  }, [blueprintConfirmationId]);

  const flushPendingConfirmationRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    flushPendingConfirmationRef.current = () => {
      if (pendingWsConfirmationRef.current === null) return;
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      if (!blueprintConfirmationIdRef.current) return;
      const approved = pendingWsConfirmationRef.current;
      pendingWsConfirmationRef.current = null;
      wsRef.current.send(
        JSON.stringify({
          type: "confirmation_response",
          confirmation_id: blueprintConfirmationIdRef.current,
          approved,
          project_name: currentProject?.name ?? null,
        })
      );
    };
  }, [currentProject?.name]);

  useEffect(() => {
    flushPendingConfirmationRef.current?.();
  }, [blueprintConfirmationId]);

  useEffect(() => {
    const sender = (approved: boolean) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN && blueprintConfirmationIdRef.current) {
        wsRef.current.send(
          JSON.stringify({
            type: "confirmation_response",
            confirmation_id: blueprintConfirmationIdRef.current,
            approved,
            project_name: currentProject?.name ?? null,
          })
        );
        return true;
      }
      pendingWsConfirmationRef.current = approved;
      return false;
    };
    return registerBlueprintConfirmationSender(sender);
  }, [registerBlueprintConfirmationSender, currentProject?.name]);

  const pendingWsStartRef = useRef(false);

  useEffect(() => {
    const sender = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            type: "user_message",
            content: "start_blueprint_collection",
            project_name: currentProject?.name ?? null,
          })
        );
      } else {
        pendingWsStartRef.current = true;
      }
    };
    return registerBlueprintStartSender(sender);
  }, [registerBlueprintStartSender, currentProject?.name]);

  useEffect(() => {
    if (!effectiveOpen) {
      wsRef.current?.close();
      wsRef.current = null;
      setConnected(false);
      return;
    }

    const url =
      wsUrl ||
      (() => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}/ws/chat`;
      })();
    setConnecting(true);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setConnecting(false);
      if (pendingWsStartRef.current) {
        pendingWsStartRef.current = false;
        ws.send(
          JSON.stringify({
            type: "user_message",
            content: "start_blueprint_collection",
            project_name: currentProject?.name ?? null,
          })
        );
      }
      flushPendingConfirmationRef.current?.();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Blueprint orchestrator events (also update context state)
        if (["message", "blueprint_draft", "confirmation_request", "progress", "error"].includes(data.type)) {
          if (data.type === "confirmation_request" && data.confirmation_id) {
            setBlueprintConfirmationId(data.confirmation_id);
          }
          handleBlueprintEvent(data);
          const msg = convertEventToChatMessage(data);
          if (msg) setMessages((prev) => [...prev, msg]);
          return;
        }

        if (data.type === "awaiting_confirmation") {
          setPendingConfirmation({
            confirmationId: data.confirmation_id,
            message: data.message,
            candidates: data.candidates || [],
            projectName: data.project_name,
          });
          return;
        }

        const msg = convertEventToChatMessage(data);
        if (msg) {
          setMessages((prev) => [...prev, msg]);
          return;
        }

        // Fallback
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}_${Math.random()}`,
            type: "assistant",
            content: data.content || data.delta || data.result?.content || data.message || "",
            timestamp: Date.now(),
          },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: `${Date.now()}_${Math.random()}`,
            type: "assistant",
            content: event.data,
            timestamp: Date.now(),
          },
        ]);
      }
    };

    ws.onerror = () => {
      setConnected(false);
      setConnecting(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}_${Math.random()}`,
          type: "error",
          content: "WebSocket connection error",
          timestamp: Date.now(),
        },
      ]);
    };

    ws.onclose = () => {
      setConnected(false);
      setConnecting(false);
    };

    return () => {
      ws.close();
    };
  }, [open, wsUrl, reconnectKey, handleBlueprintEvent]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;

    if (isInterviewMode && !isReviewing) {
      handleBlueprintEvent({ type: "message", role: "user", content: text });
      const msg: ChatMessage = {
        id: `${Date.now()}_${Math.random()}`,
        type: "user",
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, msg]);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "user_message", content: text, project_name: currentProject?.name ?? null }));
      }
      setInput("");
      return;
    }

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const msg: ChatMessage = {
      id: `${Date.now()}_${Math.random()}`,
      type: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, msg]);
    wsRef.current.send(JSON.stringify({ type: "user_message", content: text, project_name: currentProject?.name ?? null }));
    setInput("");
  };

  const sendConfirmation = (approved: boolean) => {
    if (!pendingConfirmation || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(
      JSON.stringify({
        type: "confirmation_response",
        confirmation_id: pendingConfirmation.confirmationId,
        approved,
        project_name: pendingConfirmation.projectName ?? currentProject?.name ?? null,
      })
    );
    setPendingConfirmation(null);
  };

  return (
    <>
      {!isDocked && open && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={onClose}
        />
      )}
      <div
        data-testid={isDocked ? "chat-panel-docked" : "chat-drawer"}
        className={
          isDocked
            ? "flex h-full w-full flex-col"
            : `fixed inset-y-0 right-0 z-50 w-full max-w-md transform border-l bg-card shadow-xl transition-transform duration-200 ${
                effectiveOpen ? "translate-x-0" : "translate-x-full"
              }`
        }
      >
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex h-14 items-center justify-between border-b px-4">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              <span className="font-semibold">AI 助手</span>
              <span
                className={`ml-2 inline-block h-2 w-2 rounded-full ${
                  connected ? "bg-green-500" : "bg-red-500"
                }`}
                title={connected ? "Connected" : "Disconnected"}
              />
              {connecting && (
                <Loader2 className="ml-2 h-4 w-4 animate-spin text-muted-foreground" />
              )}
            </div>
            {!isDocked && (
              <button onClick={onClose} aria-label="Close chat">
                <X className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {displayMessages.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {isInterviewMode ? "发送消息继续对话" : "发送消息开始对话"}
              </div>
            )}
            {displayMessages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${
                  msg.type === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    msg.type === "user"
                      ? "bg-primary text-primary-foreground"
                      : msg.type === "error"
                      ? "bg-destructive/10 text-destructive"
                      : msg.type === "tool_start"
                      ? "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100"
                      : msg.type === "tool_result"
                      ? "bg-green-100 text-green-900 dark:bg-green-900/30 dark:text-green-100"
                      : msg.type === "blueprint_draft"
                      ? "bg-purple-100 text-purple-900 dark:bg-purple-900/30 dark:text-purple-100"
                      : msg.type === "confirmation_request"
                      ? "bg-blue-100 text-blue-900 dark:bg-blue-900/30 dark:text-blue-100"
                      : msg.type === "progress"
                      ? "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                      : "bg-muted"
                  }`}
                >
                  <div className="flex items-center gap-1.5 pb-1 text-xs opacity-80">
                    {msg.type === "user" && <User className="h-3 w-3" />}
                    {msg.type === "assistant" && <Bot className="h-3 w-3" />}
                    {msg.type === "blueprint_draft" && <Sparkles className="h-3 w-3" />}
                    {msg.type === "confirmation_request" && <CheckCircle className="h-3 w-3" />}
                    {msg.type === "progress" && <Loader2 className="h-3 w-3 animate-spin" />}
                    {msg.type === "tool_start" && <Wrench className="h-3 w-3" />}
                    {msg.type === "tool_result" && <CheckCircle2 className="h-3 w-3" />}
                    {msg.type === "error" && <span>!</span>}
                    <span className="capitalize">{msg.type.replace("_", " ")}</span>
                    {msg.toolName && <span className="font-medium">({msg.toolName})</span>}
                    {msg.percent !== undefined && (
                      <span className="font-medium">{msg.percent}%</span>
                    )}
                  </div>
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                  {msg.imageUrl && (
                    <img
                      src={msg.imageUrl}
                      alt="Generated asset"
                      className="mt-2 max-h-48 rounded-md border"
                    />
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Confirmation panel */}
          {pendingConfirmation && (
            <div className="border-t bg-muted/50 p-3">
              <p className="text-sm font-medium">{pendingConfirmation.message}</p>
              {pendingConfirmation.candidates.length > 0 && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {pendingConfirmation.candidates.map((c, idx) => (
                    <div
                      key={idx}
                      className="rounded border bg-card p-2 text-xs text-muted-foreground"
                    >
                      {c.path}
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-3 flex justify-end gap-2">
                <button
                  onClick={() => sendConfirmation(false)}
                  className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent"
                >
                  取消
                </button>
                <button
                  onClick={() => sendConfirmation(true)}
                  className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  确认
                </button>
              </div>
            </div>
          )}

          {/* Blueprint draft confirmation panel in reviewing mode */}
          {isReviewing && blueprintDraft && (
            <div className="border-t bg-muted/50 p-3" data-testid="chat-blueprint-confirmation">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-purple-500" />
                <span className="text-sm font-medium">蓝图草案确认</span>
              </div>
              <div className="rounded border bg-card p-2 mb-3 space-y-1.5">
                <p className="text-sm font-semibold text-gray-900">{blueprintDraft.title || "未命名项目"}</p>
                <div className="flex flex-wrap gap-2">
                  {blueprintDraft.genre && (
                    <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-full bg-purple-100 text-purple-700">
                      {blueprintDraft.genre}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  {blueprintDraft.characters && (
                    <span>{blueprintDraft.characters.length} 角色</span>
                  )}
                  {blueprintDraft.chapters && (
                    <span>{blueprintDraft.chapters.length} 章节</span>
                  )}
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => sendBlueprintConfirmation(false)}
                  className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent inline-flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  继续调整
                </button>
                <button
                  onClick={() => sendBlueprintConfirmation(true)}
                  className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 inline-flex items-center gap-1.5"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  确认并生成
                </button>
              </div>
            </div>
          )}

          {/* Input */}
          <div className="border-t p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={isReviewing ? "已生成蓝图草案，请在上方确认或调整" : "输入消息..."}
                rows={1}
                disabled={isReviewing}
                className="max-h-32 min-h-[2.5rem] flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || isReviewing || (!isInterviewMode && (!connected || !!pendingConfirmation))}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
