"""Tests for the memory layer."""

from app.services.memory import ConversationContext


def test_conversation_context_empty():
    """Empty context should produce a sensible string."""
    ctx = ConversationContext()
    result = ctx.to_context_string()
    assert "Нет предыдущего контекста" in result


def test_conversation_context_with_summary():
    """Context with summary should include it."""
    ctx = ConversationContext(summary="Пользователь учится в университете.")
    result = ctx.to_context_string()
    assert "университет" in result.lower()


def test_conversation_context_with_messages():
    """Context with messages should format them."""
    ctx = ConversationContext(
        recent_messages=[
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте"},
        ]
    )
    result = ctx.to_context_string()
    assert "Пользователь" in result
    assert "Привет" in result


def test_conversation_context_limits_messages():
    """Context should only show last 5 messages."""
    messages = [
        {"role": "user", "content": f"Сообщение {i}"}
        for i in range(10)
    ]
    ctx = ConversationContext(recent_messages=messages)
    result = ctx.to_context_string()
    # Should contain message 5-9 (last 5)
    assert "Сообщение 9" in result
    assert "Сообщение 5" in result
