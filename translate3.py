import re
from pathlib import Path

replacements = {
    # formatter.py
    'до ': 'until ',
    '📌 в ': '📌 at ',
    '📋 <b>Рекомендации:</b>': '📋 <b>Recommendations:</b>',
    '❓ <b>Уточни:</b>': '❓ <b>Clarify:</b>',
    '✅ Обработано.': '✅ Processed.',
    '... (обрезано)': '... (truncated)',
    '📋 Нет активных задач.': '📋 No active tasks.',
    '✨ <b>Ваши активные задачи</b>': '✨ <b>Your active tasks</b>',
    '📅 <b>Расписание на ': '📅 <b>Schedule for ',
    'Нет запланированных блоков.': 'No scheduled blocks.',
    '✨ <b>Свободные окна:</b>': '✨ <b>Free windows:</b>',
    '💡 <b>Рекомендации:</b>': '💡 <b>Recommendations:</b>',
    '🔄 Нет активных повторяющихся задач.': '🔄 No active recurring tasks.',
    '🔄 <b>Ваши регулярные задачи</b>': '🔄 <b>Your recurring tasks</b>',
    'повтор: ': 'repeats: ',
    'следующий запуск: ': 'next run: ',
    '"Сегодня"': '"Today"',
    '"Неделя"': '"Week"',
    '"Месяц"': '"Month"',
    '"За всё время"': '"All time"',
    '📊 <b>Ваша статистика': '📊 <b>Your statistics',
    '✅ <b>Выполнено:</b>': '✅ <b>Completed:</b>',
    '❌ <b>Отменено:</b>': '❌ <b>Cancelled:</b>',
    '⏳ <b>Просрочено:</b>': '⏳ <b>Overdue:</b>',
    '🔥 <b>Серия (дней):</b>': '🔥 <b>Day streak:</b>',
    '⏱ <b>Среднее время на задачу:</b>': '⏱ <b>Average time per task:</b>',
    '🗂 <b>По категориям:</b>': '🗂 <b>By categories:</b>',

    # handlers.py
    'с inline-кнопками': 'with inline buttons',
    'Mark task as completed': 'Mark task as completed',
    'Cancel task': 'Cancel task',
    'Delete task': 'Delete task',
    'Day schedule (блокировки + свободные окна)': 'Day schedule (constraints + free windows)',
    'Показать это сообщение': 'Show this message',
    'Также вы можете просто написать текстом или отправить голосовое сообщение о том, что нужно сделать,': 'You can also just text or send a voice message with what needs to be done,',
    'и AI-планировщик разберёт это в задачи.': 'and the AI planner will break it down into tasks.',
    'Напоminание не найдено.': 'Reminder not found.',
    '❌ Регулярная задача cancelled.': '❌ Recurring task cancelled.',
    "Использование:": "Usage:",

    # routes.py
    'Планировщик не инициализирован.': 'Planner is not initialized.',
    
    # priority.py
    '"надо", "обязательно", "срочно", "важно", "критично", "asap"': '"must", "mandatory", "urgent", "important", "critical", "asap"',
    '⚠️ Задача \'': '⚠️ Task \'',
    '\' просрочена!': '\' is overdue!',
    '\' может не хватить времени до дедлайна.': '\' might not have enough time before the deadline.',
    '\' чувствительна к погоде. ': '\' is weather sensitive. ',
    'Ожидается дождь (': 'Rain expected (',
    '%). ': '%). ',
    'Рекомендуется перенести или подготовиться.': 'Recommended to reschedule or prepare.',
    '⚠️ Конфликт: \'': '⚠️ Conflict: \'',
    '\' и \'': '\' and \'',
    '\' пересекаются по времени.': '\' overlap in time.',

    # rescheduler.py
    'Свободное окно ': 'Free window ',

    # timeline.py
    '\' запланирована на ': '\' is scheduled for ',
    ', но это время заблокировано.': ', but this time is constrained.',
    '\' пересекаются (': '\' overlap (',
    ' (Привычка)': ' (Routine)',
    '⚠️ Не хватает времени для: ': '⚠️ Not enough time for: ',
    '. Рассмотрите перенос на другой день.': '. Consider rescheduling for another day.',
    'Перенесите \'': 'Reschedule \'',
    '\' на завтра или сократите длительность.': '\' to tomorrow or reduce duration.',
    '☔ Внимание: ожидается дождь, а задача \'': '☔ Warning: rain is expected, and task \'',
    '\' чувствительна к погоде. Возможно, стоит её перенести.': '\' is weather sensitive. It might be worth rescheduling.',
    '\' из-за дождя.': '\' due to rain.',

    # scheduler.py
    '⏰ Напоminание: \'': '⏰ Reminder: \'',
    '\' — дедлайн через ': '\' — deadline in ',
    '🔔 Напоminание:\\n<b>': '🔔 Reminder:\\n<b>',
    '💡 Рекомендую перенести на <b>': '💡 Recommend rescheduling to <b>',
    '<i>Причина: ': '<i>Reason: ',

    # memory.py
    'Краткая сводка: ': 'Brief summary: ',
    'Пользователь': 'User',
    'Ассистент': 'Assistant',
    'Последние сообщения:\\n': 'Recent messages:\\n',
    'Нет предыдущего контекста.': 'No previous context.',
    ' (дедлайн: ': ' (deadline: ',
    ' [фикс: ': ' [fixed: ',
    'Нет активных задач.': 'No active tasks.',
}

files_to_check = Path('app').rglob('*.py')
all_files = list(files_to_check) + [Path('main.py'), Path('bot_polling.py')]

for path in all_files:
    if not path.is_file():
        continue
    content = path.read_text(encoding='utf-8')
    original_content = content
    for ru_text, en_text in replacements.items():
        content = content.replace(ru_text, en_text)
    if content != original_content:
        path.write_text(content, encoding='utf-8')
        print(f"Updated {path}")
