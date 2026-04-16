import { useRef, useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { useChatStore } from '@/store/useChatStore';
import { Send, Trash2, Settings, Bot, User, Loader2, GitFork, Map, Sparkles, Wand2, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { BlueprintCard } from '@/components/cards/BlueprintCard';
import { ProgressCard } from '@/components/cards/ProgressCard';
import { AuditReportCard } from '@/components/cards/AuditReportCard';
import { ResourceCandidateCard } from '@/components/cards/ResourceCandidateCard';
import { cn } from '@/lib/utils';
import type { ChatMessage } from '@/types';

export function ChatPanel() {
  const { messages, inputValue, isTyping, setInputValue, sendMessage, clearMessages, addAssistantMessage } = useChatStore();
  const { isGenerating, chapters, blueprintPhase, startBlueprintCollection, submitBlueprintGeneration, setBlueprintPhase, createEmptyBlueprint } = useAppStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevPhaseRef = useRef(blueprintPhase);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // 自动发送开场白当从 idle 进入 collecting
  useEffect(() => {
    if (prevPhaseRef.current === 'idle' && blueprintPhase === 'collecting') {
      addAssistantMessage(
        '太棒了！让我来帮你把这个想法变成完整的蓝图。首先，你希望这个故事大概有几章？有没有特别想设定的主角人设或故事基调？'
      );
    }
    prevPhaseRef.current = blueprintPhase;
  }, [blueprintPhase, addAssistantMessage]);

  const handleSend = () => {
    if (inputValue.trim()) {
      sendMessage(inputValue.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-950 border-l border-gray-200 dark:border-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              与 AI 协作创作
            </h3>
            <p className="text-xs text-gray-500">
              campus_romance
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={clearMessages}
            className="h-8 w-8"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
          >
            <Settings className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message: ChatMessage) => (
          <MessageItem key={message.id} message={message} />
        ))}

        {isTyping && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center flex-shrink-0">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <div className="flex items-center gap-2 py-2">
              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
              <span className="text-sm text-gray-500">AI 正在思考...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-800">
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isGenerating
                ? 'AI 正在生成中，请稍候...'
                : blueprintPhase === 'collecting' || blueprintPhase === 'reviewing'
                ? '回复 AI 的问题...'
                : '输入消息...'
            }
            className="flex-1"
            disabled={isGenerating}
          />
          <Button
            onClick={handleSend}
            disabled={!inputValue.trim() || isGenerating}
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>

        {/* Quick Actions */}
        {!isGenerating && (
          <div className="flex gap-2 mt-3 flex-wrap">
            {blueprintPhase === 'collecting' && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-800">
                <Loader2 className="w-3 h-3 animate-spin" />
                继续回答 AI 的问题以细化需求
              </span>
            )}

            {blueprintPhase === 'reviewing' && (
              <>
                <QuickActionButton
                  label="开始生成蓝图"
                  icon={<Wand2 className="w-3 h-3" />}
                  onClick={() => {
                    sendMessage('开始生成');
                    submitBlueprintGeneration();
                  }}
                />
                <QuickActionButton
                  label="再调整一下"
                  icon={<FileText className="w-3 h-3" />}
                  onClick={() => {
                    setBlueprintPhase('collecting');
                    sendMessage('再调整一下');
                  }}
                />
              </>
            )}

            {blueprintPhase === 'idle' && chapters.length === 0 && (
              <>
                <QuickActionButton
                  label="生成校园恋爱蓝图"
                  icon={<Wand2 className="w-3 h-3" />}
                  onClick={() => {
                    startBlueprintCollection();
                    sendMessage('生成校园恋爱蓝图');
                  }}
                />
                <QuickActionButton
                  label="生成悬疑科幻蓝图"
                  icon={<Wand2 className="w-3 h-3" />}
                  onClick={() => {
                    startBlueprintCollection();
                    sendMessage('生成悬疑科幻蓝图');
                  }}
                />
                <QuickActionButton
                  label="手动输入 YAML"
                  icon={<FileText className="w-3 h-3" />}
                  onClick={() => {
                    createEmptyBlueprint();
                    sendMessage('手动输入 YAML');
                  }}
                />
              </>
            )}

            {blueprintPhase === 'editing' && chapters.length > 0 && (
              <>
                <QuickActionButton
                  label="生成第一章"
                  onClick={() => sendMessage('开始生成第一章')}
                />
                <QuickActionButton
                  label="查看审计报告"
                  onClick={() => sendMessage('查看审计报告')}
                />
                <QuickActionButton
                  label="确认蓝图"
                  onClick={() => sendMessage('确认蓝图')}
                />
                <QuickActionButton
                  label="添加分支选项"
                  icon={<GitFork className="w-3 h-3" />}
                  onClick={() => sendMessage('帮我在当前场景添加一个分支选项')}
                />
                <QuickActionButton
                  label="查看故事地图"
                  icon={<Map className="w-3 h-3" />}
                  onClick={() => sendMessage('打开故事地图')}
                />
                <QuickActionButton
                  label="生成结局"
                  icon={<Sparkles className="w-3 h-3" />}
                  onClick={() => sendMessage('设计一个多结局方案')}
                />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <div className={cn(
      "flex items-start gap-3",
      isUser && "flex-row-reverse"
    )}>
      {/* Avatar */}
      <div className={cn(
        "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0",
        isUser
          ? "bg-gray-200 dark:bg-gray-700"
          : "bg-gradient-to-br from-blue-500 to-purple-500"
      )}>
        {isUser ? (
          <User className="w-4 h-4 text-gray-600 dark:text-gray-400" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className={cn(
        "flex-1 max-w-[85%]",
        isUser && "text-right"
      )}>
        {isUser ? (
          <div className="inline-block px-4 py-2 rounded-2xl bg-blue-500 text-white text-left">
            <p className="text-sm">{message.content}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Render different card types */}
            {message.type === 'blueprint' && message.data ? (
              <BlueprintCard data={message.data as {
                title: string;
                genre: string;
                characters: { name: string; role: string }[];
                chapters: { name: string; scenes: number }[];
              }} />
            ) : null}

            {message.type === 'progress' && message.data ? (
              <ProgressCard data={message.data as {
                chapterId: string;
                sceneId: string;
                sceneName: string;
                step: string;
                percent: number;
              }} />
            ) : null}

            {message.type === 'audit' && message.data ? (
              <AuditReportCard data={message.data as {
                status: 'passed' | 'failed';
                score: number;
                issues: import('@/types').AuditIssue[];
              }} />
            ) : null}

            {message.type === 'resource' && message.data ? (
              <ResourceCandidateCard data={message.data as {
                type: 'background' | 'character';
                sceneId: string;
                urls: string[];
              }} />
            ) : null}

            {(message.type === 'text' || !message.data) && (
              <div className="inline-block px-4 py-2 rounded-2xl bg-gray-100 dark:bg-gray-800 text-left">
                <p className="text-sm text-gray-800 dark:text-gray-200">
                  {message.content}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function QuickActionButton({ label, onClick, icon }: { label: string; onClick: () => void; icon?: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
    >
      {icon}
      {label}
    </button>
  );
}
