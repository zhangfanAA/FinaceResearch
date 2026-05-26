/**
 * @fileoverview DeepSeek 金融问答面板 - 支持与 DeepSeek 进行金融分析对话
 * @module components/DeepSeekSearchPanel
 * @description 提供一个聊天式界面，用户可以向 DeepSeek 提问金融相关问题。
 * 支持：
 * - 实时问答对话
 * - 历史消息记录
 * - 加载状态和错误处理
 * - 快捷问题模板
 * - 消息复制功能
 */

import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { askDeepSeek } from '../api/client';

/**
 * 快捷问题模板
 */
const QUICK_QUESTIONS = [
  '今日A股市场整体走势如何？',
  '半导体板块近期有什么利好消息？',
  '白酒板块的投资价值分析',
  '当前市场情绪如何？适合入场吗？',
];

/**
 * 格式化时间戳
 * @param {Date} date
 * @returns {string}
 */
function formatTime(date) {
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * 消息气泡组件
 */
function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [message.content]);

  return (
    <div className={`chat-message chat-message--${isUser ? 'user' : 'assistant'}`}>
      <div className="chat-message__header">
        <span className="chat-message__role">
          {isUser ? 'You' : 'DeepSeek'}
        </span>
        <span className="chat-message__time">
          {formatTime(message.timestamp)}
        </span>
      </div>
      <div className="chat-message__content">
        {message.loading ? (
          <div className="chat-message__loading">
            <span className="chat-message__dot" />
            <span className="chat-message__dot" />
            <span className="chat-message__dot" />
          </div>
        ) : (
          <>
            <div className="chat-message__text">{message.content}</div>
            {!isUser && message.content && (
              <button
                type="button"
                className="chat-message__copy"
                onClick={handleCopy}
                title="Copy to clipboard"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            )}
          </>
        )}
      </div>
      {message.error && (
        <div className="chat-message__error">{message.error}</div>
      )}
    </div>
  );
}

/**
 * DeepSeek 金融问答面板主组件
 *
 * @component DeepSeekSearchPanel
 * @description 提供与 DeepSeek 的金融问答交互界面
 */
export default function DeepSeekSearchPanel() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  /**
   * 滚动到最新消息
   */
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  /**
   * 提交问题到 DeepSeek
   */
  const handleSubmit = useCallback(async (question) => {
    const q = (question || input).trim();
    if (!q || isSubmitting) return;

    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: q,
      timestamp: new Date(),
    };

    // Add loading assistant message
    const assistantId = Date.now() + 1;
    const loadingMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      loading: true,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setInput('');
    setIsSubmitting(true);

    // Scroll to bottom after state update
    setTimeout(scrollToBottom, 50);

    try {
      const result = await askDeepSeek(q);

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: result.answer || 'No response received.',
                model: result.model,
                loading: false,
              }
            : msg
        )
      );
    } catch (e) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                content: '',
                loading: false,
                error: e.message || 'Failed to get response from DeepSeek.',
              }
            : msg
        )
      );
    } finally {
      setIsSubmitting(false);
      setTimeout(scrollToBottom, 50);
      inputRef.current?.focus();
    }
  }, [input, isSubmitting, scrollToBottom]);

  /**
   * 处理键盘提交
   */
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  /**
   * 清空对话历史
   */
  const handleClear = useCallback(() => {
    setMessages([]);
  }, []);

  return (
    <section className="panel deepseek-panel">
      <div className="section-header">
        <div>
          <h2>{t('deepseek.title', 'DeepSeek 金融问答')}</h2>
          <p>{t('deepseek.subtitle', 'Ask DeepSeek financial analysis questions')}</p>
        </div>
        <div className="section-header__actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="button button--secondary button--sm"
              onClick={handleClear}
              disabled={isSubmitting}
            >
              {t('deepseek.clear', 'Clear')}
            </button>
          )}
        </div>
      </div>

      {/* Quick questions */}
      {messages.length === 0 && (
        <div className="deepseek-quick-questions">
          <p className="deepseek-quick-questions__label">
            {t('deepseek.quickQuestions', 'Quick questions:')}
          </p>
          <div className="deepseek-quick-questions__grid">
            {QUICK_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                className="deepseek-quick-questions__item"
                onClick={() => {
                  setInput(q);
                  handleSubmit(q);
                }}
                disabled={isSubmitting}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat messages */}
      <div className="deepseek-chat-messages">
        {messages.length === 0 ? (
          <div className="deepseek-empty-state">
            <div className="deepseek-empty-state__icon">{'\u{1F4CA}'}</div>
            <p>{t('deepseek.emptyState', 'Ask any financial question to get AI-powered analysis.')}</p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="deepseek-input-area">
        <textarea
          ref={inputRef}
          className="deepseek-input-area__textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('deepseek.placeholder', 'Ask a financial question... (Enter to send, Shift+Enter for new line)')}
          rows={2}
          disabled={isSubmitting}
        />
        <button
          type="button"
          className="button deepseek-input-area__send"
          onClick={() => handleSubmit()}
          disabled={!input.trim() || isSubmitting}
        >
          {isSubmitting
            ? t('deepseek.sending', 'Sending...')
            : t('deepseek.send', 'Send')}
        </button>
      </div>
    </section>
  );
}
