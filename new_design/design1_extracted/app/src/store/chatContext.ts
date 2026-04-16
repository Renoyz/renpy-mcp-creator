import { createContext } from 'react';
import type { ChatMessage } from '@/types';

export interface ChatContextValue {
  messages: ChatMessage[];
  inputValue: string;
  isTyping: boolean;
  setInputValue: (value: string) => void;
  sendMessage: (content: string) => void;
  clearMessages: () => void;
  addAssistantMessage: (content: string, type?: ChatMessage['type'], data?: unknown) => void;
  resetChat: () => void;
}

export const ChatContext = createContext<ChatContextValue | null>(null);
