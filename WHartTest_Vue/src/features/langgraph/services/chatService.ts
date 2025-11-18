import { ref } from 'vue';
import { request } from '@/utils/request';
import { useAuthStore } from '@/store/authStore';
import type { ApiResponse } from '@/features/langgraph/types/api';
import type {
  ChatRequest,
  ChatResponseData,
  ChatHistoryResponseData,
  ChatSessionsResponseData
} from '@/features/langgraph/types/chat';

// --- 全局流式状态管理 ---
interface StreamMessage {
  content: string;
  type: 'human' | 'ai' | 'tool' | 'system';
  time: string;
  isExpanded?: boolean;
  isThinkingProcess?: boolean;
  isThinkingExpanded?: boolean;
}

interface StreamState {
  content: string;
  error?: string;
  isComplete: boolean;
  messages: StreamMessage[]; // 存储所有消息,包括工具消息
}

export const activeStreams = ref<Record<string, StreamState>>({});

export const clearStreamState = (sessionId: string) => {
  if (activeStreams.value[sessionId]) {
    delete activeStreams.value[sessionId];
  }
};
// --- 全局流式状态管理结束 ---

const API_BASE_URL = '/lg/chat';

// 获取API基础URL
function getApiBaseUrl() {
  const envUrl = import.meta.env.VITE_API_BASE_URL;

  // 如果环境变量是完整URL（包含http/https），直接使用
  if (envUrl && (envUrl.startsWith('http://') || envUrl.startsWith('https://'))) {
    return envUrl;
  }

  // 否则使用相对路径，让浏览器自动解析到当前域名
  return '/api';
}

/**
 * 发送对话消息
 */
export async function sendChatMessage(
  data: ChatRequest
): Promise<ApiResponse<ChatResponseData>> {
  const response = await request<ChatResponseData>({
    url: `${API_BASE_URL}/`,
    method: 'POST',
    data
  });

  if (response.success) {
    return {
      status: 'success',
      code: 200,
      message: response.message || 'success',
      data: response.data!,
      errors: undefined
    };
  } else {
    return {
      status: 'error',
      code: 500,
      message: response.error || 'Failed to send chat message',
      data: {} as ChatResponseData,
      errors: { detail: [response.error || 'Unknown error'] }
    };
  }
}

/**
 * 刷新token
 */
async function refreshAccessToken(): Promise<string | null> {
  const authStore = useAuthStore();
  const refreshToken = authStore.getRefreshToken;

  if (!refreshToken) {
    authStore.logout();
    return null;
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/token/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        refresh: refreshToken
      }),
    });

    if (response.ok) {
      const data = await response.json();
      if (data.access) {
        // 更新token
        localStorage.setItem('auth-accessToken', data.access);
        return data.access;
      }
    }

    // 刷新失败，登出用户
    authStore.logout();
    return null;
  } catch (error) {
    console.error('Token refresh failed:', error);
    authStore.logout();
    return null;
  }
}

/**
 * 发送流式对话消息
 */
export async function sendChatMessageStream(
  data: ChatRequest,
  onStart: (sessionId: string) => void, // 简化回调，只保留 onStart
  signal?: AbortSignal
): Promise<void> {
  const authStore = useAuthStore();
  let token = authStore.getAccessToken;
  let streamSessionId: string | null = data.session_id || null;

  // 错误处理函数，用于更新全局状态
  const handleError = (error: any, sessionId: string | null) => {
    console.error('Stream error:', error);
    if (sessionId && activeStreams.value[sessionId]) {
      activeStreams.value[sessionId].error = error.message || '流式请求失败';
      activeStreams.value[sessionId].isComplete = true;
    }
  };

  if (!token) {
    handleError(new Error('未登录或登录已过期'), streamSessionId);
    return;
  }

  try {
    let response = await fetch(`${getApiBaseUrl()}${API_BASE_URL}/stream/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(data),
      signal,
    });

    if (response.status === 401) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        token = newToken;
        response = await fetch(`${getApiBaseUrl()}${API_BASE_URL}/stream/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify(data),
          signal,
        });
      } else {
        handleError(new Error('登录已过期，请重新登录'), streamSessionId);
        return;
      }
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
      throw new Error('Failed to get response reader');
    }

    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        // 流结束时，如果会话仍在进行中，则标记为完成
        if (streamSessionId && activeStreams.value[streamSessionId] && !activeStreams.value[streamSessionId].isComplete) {
            activeStreams.value[streamSessionId].isComplete = true;
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim() === '' || !line.startsWith('data: ')) continue;
        
        const jsonData = line.slice(6);
        if (jsonData === '[DONE]') {
            if (streamSessionId && activeStreams.value[streamSessionId]) {
                activeStreams.value[streamSessionId].isComplete = true;
            }
            continue;
        }

        try {
          const parsed = JSON.parse(jsonData);

          if (parsed.type === 'error') {
            handleError(new Error(parsed.message || '流式请求失败'), streamSessionId);
            return;
          }

          if (parsed.type === 'start' && parsed.session_id) {
            streamSessionId = parsed.session_id;
            if (streamSessionId) {
              // 初始化或重置此会话的流状态
              activeStreams.value[streamSessionId] = {
                content: '',
                isComplete: false,
                messages: []
              };
              onStart(streamSessionId);
            }
          }

          // 处理工具消息(update事件)
          if (parsed.type === 'update' && streamSessionId && activeStreams.value[streamSessionId]) {
            const updateData = parsed.data;
            if (typeof updateData === 'string') {
              // 解析工具消息
              // 格式类似: "{'agent': {'messages': [ToolMessage(content='...', name='tool_name', ...)]}}"
              if (updateData.includes('ToolMessage')) {
                try {
                  // 提取工具消息内容
                  const contentMatch = updateData.match(/content='([^']*(?:\\'[^']*)*)'/);
                  const nameMatch = updateData.match(/name='([^']*)'/);
                  
                  if (contentMatch) {
                    const toolContent = contentMatch[1].replace(/\\'/g, "'").replace(/\\n/g, '\n');
                    const toolName = nameMatch ? nameMatch[1] : 'tool';
                    
                    const now = new Date();
                    const time = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
                    
                    // 🔧 如果当前有AI流式内容,先将其固化为独立消息
                    if (activeStreams.value[streamSessionId].content && activeStreams.value[streamSessionId].content.trim()) {
                      activeStreams.value[streamSessionId].messages.push({
                        content: activeStreams.value[streamSessionId].content,
                        type: 'ai',
                        time: time,
                        isExpanded: false
                      });
                      // 清空AI内容,准备接收新的内容
                      activeStreams.value[streamSessionId].content = '';
                    }
                    
                    // 添加工具消息作为新的独立消息
                    activeStreams.value[streamSessionId].messages.push({
                      content: toolContent,
                      type: 'tool',
                      time: time,
                      isExpanded: false
                    });
                  }
                } catch (e) {
                  console.warn('Failed to parse tool message:', updateData);
                }
              }
            }
          }

          // 处理AI消息(message事件)
          if (parsed.type === 'message' && streamSessionId && activeStreams.value[streamSessionId]) {
            const messageData = parsed.data;
            if (typeof messageData === 'string') {
              let content = '';
              if (messageData.includes('AIMessageChunk')) {
                 const match = messageData.match(/content='((?:\\'|[^'])*)'/);
                 if(match && match[1] !== undefined) {
                    content = match[1].replace(/\\'/g, "'");
                 }
              }
              // 在这里直接更新全局状态
              activeStreams.value[streamSessionId].content += content;
            }
          }

          if (parsed.type === 'complete' && streamSessionId && activeStreams.value[streamSessionId]) {
            activeStreams.value[streamSessionId].isComplete = true;
          }
        } catch (e) {
          console.warn('Failed to parse SSE data:', jsonData);
        }
      }
    }
  } catch (error) {
    handleError(error, streamSessionId);
  }
}

/**
 * 获取聊天历史记录
 * @param sessionId 会话ID
 * @param projectId 项目ID
 */
export async function getChatHistory(
  sessionId: string,
  projectId: number | string
): Promise<ApiResponse<ChatHistoryResponseData>> {
  const response = await request<ChatHistoryResponseData>({
    url: `${API_BASE_URL}/history/`,
    method: 'GET',
    params: {
      session_id: sessionId,
      project_id: String(projectId) // 确保转换为string
    }
  });

  if (response.success) {
    return {
      status: 'success',
      code: 200,
      message: response.message || 'success',
      data: response.data!,
      errors: undefined
    };
  } else {
    return {
      status: 'error',
      code: 500,
      message: response.error || 'Failed to get chat history',
      data: {} as ChatHistoryResponseData,
      errors: { detail: [response.error || 'Unknown error'] }
    };
  }
}

/**
 * 删除聊天历史记录
 * @param sessionId 要删除历史记录的会话ID
 * @param projectId 项目ID
 */
export async function deleteChatHistory(
  sessionId: string,
  projectId: number | string
): Promise<ApiResponse<null>> {
  const response = await request<null>({
    url: `${API_BASE_URL}/history/`,
    method: 'DELETE',
    params: {
      session_id: sessionId,
      project_id: String(projectId) // 确保转换为string
    }
  });

  if (response.success) {
    return {
      status: 'success',
      code: 200,
      message: response.message || '聊天历史记录已成功删除',
      data: null,
      errors: undefined
    };
  } else {
    return {
      status: 'error',
      code: 500,
      message: response.error || 'Failed to delete chat history',
      data: null,
      errors: { detail: [response.error || 'Unknown error'] }
    };
  }
}

/**
 * 获取用户的所有会话列表
 * @param projectId 项目ID
 */
export async function getChatSessions(projectId: number): Promise<ApiResponse<ChatSessionsResponseData>> {
  const response = await request<ChatSessionsResponseData>({
    url: `${API_BASE_URL}/sessions/`,
    method: 'GET',
    params: {
      project_id: projectId
    }
  });

  if (response.success) {
    return {
      status: 'success',
      code: 200,
      message: response.message || 'success',
      data: response.data!,
      errors: undefined
    };
  } else {
    return {
      status: 'error',
      code: 500,
      message: response.error || 'Failed to get chat sessions',
      data: {} as ChatSessionsResponseData,
      errors: { detail: [response.error || 'Unknown error'] }
    };
  }
}

/**
 * 批量删除聊天历史记录
 * @param sessionIds 要删除的会话ID数组
 * @param projectId 项目ID
 */
export async function batchDeleteChatHistory(
  sessionIds: string[],
  projectId: number | string
): Promise<ApiResponse<{ deleted_count: number; processed_sessions: number; failed_sessions: any[] }>> {
  const response = await request<{ deleted_count: number; processed_sessions: number; failed_sessions: any[] }>({
    url: `${API_BASE_URL}/batch-delete/`,
    method: 'POST',
    data: {
      session_ids: sessionIds,
      project_id: String(projectId)
    }
  });

  if (response.success) {
    return {
      status: 'success',
      code: 200,
      message: response.message || '批量删除成功',
      data: response.data!,
      errors: undefined
    };
  } else {
    return {
      status: 'error',
      code: 500,
      message: response.error || '批量删除失败',
      data: { deleted_count: 0, processed_sessions: 0, failed_sessions: [] },
      errors: { detail: [response.error || 'Unknown error'] }
    };
  }
}