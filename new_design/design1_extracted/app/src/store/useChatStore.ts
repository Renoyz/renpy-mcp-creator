import { useContext } from 'react';
import { ChatContext } from './chatContext';

export function useChatStore() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChatStore must be used within ChatProvider');
  }
  return context;
}
