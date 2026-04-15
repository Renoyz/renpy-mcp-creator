import { useEffect, useRef, useState } from "react";
import { Send, X, Bot, User, Loader2, Wrench, CheckCircle2 } from "lucide-react";

export type MessageType =
  | "user"
  | "assistant"
  | "tool_start"
  | "tool_result"
  | "error";

export interface ChatMessage {
  id: string;
  type: MessageType;
  content: string;
  toolName?: string;
  timestamp: number;
}

export interface PendingConfirmation {
  confirmationId: string;
  message: string;
  candidates: { type: string; path: string }[];
}

interface ChatDrawerProps {
  open: boolean;
  onClose: () => void;
  wsUrl?: string;
}

export function ChatDrawer({ open, onClose, wsUrl }: ChatDrawerProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [reconnectKey, setReconnectKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const handleProjectChange = () => {
      if (open && wsRef.current) {
        wsRef.current.close();
        setReconnectKey((k) => k + 1);
      }
    };
    window.addEventListener("project-changed", handleProjectChange);
    return () => {
      window.removeEventListener("project-changed", handleProjectChange);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
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
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "awaiting_confirmation") {
          setPendingConfirmation({
            confirmationId: data.confirmation_id,
            message: data.message,
            candidates: data.candidates || [],
          });
          return;
        }
        const msg: ChatMessage = {
          id: `${Date.now()}_${Math.random()}`,
          type: data.type || "assistant",
          content:
            data.content || data.delta || data.result?.content || data.message || "",
          toolName: data.tool_name,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, msg]);
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
  }, [open, wsUrl, reconnectKey]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    const msg: ChatMessage = {
      id: `${Date.now()}_${Math.random()}`,
      type: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, msg]);
    wsRef.current.send(JSON.stringify({ type: "user_message", content: text }));
    setInput("");
  };

  const sendConfirmation = (approved: boolean) => {
    if (!pendingConfirmation || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(
      JSON.stringify({
        type: "confirmation_response",
        confirmation_id: pendingConfirmation.confirmationId,
        approved,
      })
    );
    setPendingConfirmation(null);
  };

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={onClose}
        />
      )}
      <div
        className={`fixed inset-y-0 right-0 z-50 w-full max-w-md transform border-l bg-card shadow-xl transition-transform duration-200 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
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
            <button onClick={onClose} aria-label="Close chat">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">
                发送消息开始对话
              </div>
            )}
            {messages.map((msg) => (
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
                      : "bg-muted"
                  }`}
                >
                  <div className="flex items-center gap-1.5 pb-1 text-xs opacity-80">
                    {msg.type === "user" && <User className="h-3 w-3" />}
                    {msg.type === "assistant" && <Bot className="h-3 w-3" />}
                    {msg.type === "tool_start" && <Wrench className="h-3 w-3" />}
                    {msg.type === "tool_result" && <CheckCircle2 className="h-3 w-3" />}
                    {msg.type === "error" && <span>!</span>}
                    <span className="capitalize">{msg.type.replace("_", " ")}</span>
                    {msg.toolName && <span className="font-medium">({msg.toolName})</span>}
                  </div>
                  <div className="whitespace-pre-wrap">{msg.content}</div>
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
                placeholder="输入消息..."
                rows={1}
                className="max-h-32 min-h-[2.5rem] flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || !connected || !!pendingConfirmation}
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
