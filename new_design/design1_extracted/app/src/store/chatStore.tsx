import React, { useCallback, useMemo, useState } from 'react';
import { useAppStore } from './useAppStore';
import { ChatContext } from './chatContext';
import type { ChatMessage } from '@/types';

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const {
    messages,
    addUserMessage: appAddUserMessage,
    addAssistantMessage: appAddAssistantMessage,
    clearMessages: appClearMessages,
    setMessages: appSetMessages,
    blueprintPhase,
    setBlueprintPhase,
    submitBlueprintGeneration,
    simulateGenerationProgress,
    simulateAuditReport,
    simulateBlueprintInterview,
  } = useAppStore();

  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);

  const addAssistantMessage = useCallback((content: string, type?: ChatMessage['type'], data?: unknown) => {
    appAddAssistantMessage(content, type, data);
  }, [appAddAssistantMessage]);

  const handleSendMessage = useCallback((content: string) => {
    appAddUserMessage(content);
    setInputValue('');
    setIsTyping(true);

    const process = () => {
      if (blueprintPhase === 'idle') {
        setBlueprintPhase('collecting');
        addAssistantMessage(
          `你好！很高兴帮你创建 Ren'Py 视觉小说项目。\n\n请简单描述一下你的游戏构思，比如：\n- 题材（校园恋爱、悬疑推理、奇幻冒险等）\n- 核心角色（1-3位）\n- 期望的游戏时长或章节数`
        );
        return;
      }

      if (blueprintPhase === 'collecting' || blueprintPhase === 'reviewing') {
        if (/生成|开始|确认|好了/.test(content)) {
          addAssistantMessage('好的，正在根据访谈内容生成项目蓝图，请稍候...');
          setBlueprintPhase('generating');
          submitBlueprintGeneration();
        } else {
          simulateBlueprintInterview(content);
        }
        return;
      }

      if (blueprintPhase === 'editing') {
        if (/生成|脚本|章节/.test(content)) {
          simulateGenerationProgress();
        } else if (/审计|检查|审阅/.test(content)) {
          simulateAuditReport();
        } else {
          addAssistantMessage('收到。你可以在左侧切换视图继续编辑项目，或随时向我提问。');
        }
        return;
      }

      if (blueprintPhase === 'generating') {
        addAssistantMessage('蓝图生成中，请稍候片刻...');
        return;
      }

      addAssistantMessage('收到你的消息，我正在处理中。');
    };

    setTimeout(() => {
      process();
      setIsTyping(false);
    }, 600);
  }, [
    appAddUserMessage,
    addAssistantMessage,
    blueprintPhase,
    setBlueprintPhase,
    submitBlueprintGeneration,
    simulateGenerationProgress,
    simulateAuditReport,
    simulateBlueprintInterview,
  ]);

  const clearMessages = useCallback(() => {
    appClearMessages();
  }, [appClearMessages]);

  const resetChat = useCallback(() => {
    appSetMessages([]);
  }, [appSetMessages]);

  const value = useMemo(
    () => ({
      messages,
      inputValue,
      isTyping,
      setInputValue,
      sendMessage: handleSendMessage,
      clearMessages,
      addAssistantMessage,
      resetChat,
    }),
    [messages, inputValue, isTyping, handleSendMessage, clearMessages, addAssistantMessage, resetChat]
  );

  return (
    <ChatContext.Provider value={value}>
      {children}
    </ChatContext.Provider>
  );
}
