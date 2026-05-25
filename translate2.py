import re
from pathlib import Path

replacements = {
    # formatter.py
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
    
    # handlers.py
    '👋 Привет! Я — твой AI-планировщик задач.': '👋 Hello! I am your AI task planner.',
    'Просто напиши или отправь голосовое сообщение о том, что нужно сделать, и я разберу это в задачи.': 'Just write or send a voice message about what needs to be done, and I will break it down into tasks.',
    'Вы можете использовать кнопки внизу или отправлять команды.': 'You can use the buttons below or send commands.',
    'Использование: /delete [номер задачи]': 'Usage: /delete [task number]',
    'Нет задачи с номером': 'No task with number',
    '🗑 Удалена:': '🗑 Deleted:',
    '⚠️ Планировщик не инициализирован.': '⚠️ Planner is not initialized.',
    '⚠️ Timeline Engine не инициализирован.': '⚠️ Timeline Engine is not initialized.',
    '📖 <b>Доступные команды</b>': '📖 <b>Available commands</b>',
    'Отметить задачу как выполненную': 'Mark task as completed',
    'Показать это сообщение': 'Show this message',
    'Также вы можете просто написать текстом или отправить голосовое сообщение о том, что нужно сделать,': 'You can also just write text or send a voice message about what needs to be done,',
    'и AI-планировщик разберёт это в задачи.': 'and the AI planner will break it down into tasks.',
    '⚠️ Голосовой ввод не поддерживается (модель не загружена).': '⚠️ Voice input is not supported (model not loaded).',
    '🎤 Распознаю голосовое сообщение...': '🎤 Recognizing voice message...',
    '❌ Не удалось загрузить голосовое сообщение.': '❌ Failed to download voice message.',
    '❌ Не удалось распознать голосовое сообщение. Попробуйте ещё раз.': '❌ Failed to recognize voice message. Please try again.',
    '🎤 Распознано': '🎤 Recognized',
    '(уверенность:': '(confidence:',
    'Это правильно?': 'Is this correct?',
    '❌ Ошибка обработки голосового сообщения.': '❌ Voice processing error.',
    'Хорошо, введите текст вручную.': 'Okay, type the text manually.',
    '❌ <b>Отклонено</b>': '❌ <b>Rejected</b>',
    'Текст не найден, попробуйте отправить заново.': 'Text not found, try sending again.',
    '❌ <b>Текст не найден</b>': '❌ <b>Text not found</b>',
    '⏳ <b>Обрабатываю...</b>': '⏳ <b>Processing...</b>',
    'Ошибка: неверный ID задачи.': 'Error: invalid task ID.',
    '⏳ Сначала завершите предыдущие задачи!': '⏳ First complete previous tasks!',
    '✅ Выполнено!': '✅ Completed!',
    '🗑 Удалено.': '🗑 Deleted.',
    'Ошибка: неверный ID.': 'Error: invalid ID.',
    '✅ Подтверждено!': '✅ Confirmed!',
    '✅ <b>Подтверждено</b>': '✅ <b>Confirmed</b>',
    'Напоминание не найдено.': 'Reminder not found.',
    '❌ Регулярная задача отменена.': '❌ Recurring task cancelled.',
    'Задача не найдена.': 'Task not found.',
    'Оставил без изменений.': 'Left unchanged.',
    '❌ <b>Оставлено без изменений</b>': '❌ <b>Left unchanged</b>',
    'Ошибка: неверный формат времени.': 'Error: invalid time format.',
    'Ошибка: Timeline не инициализирован.': 'Error: Timeline is not initialized.',
    '✅ Задача перенесена!': '✅ Task rescheduled!',
    '✅ <b>Перенесено</b>': '✅ <b>Rescheduled</b>',
    'Ошибка: не удалось перенести задачу.': 'Error: failed to reschedule task.',
    'Использование: /': 'Usage: /',
    '⏳ Невозможно завершить': '⏳ Cannot complete',
    'Сначала выполните предыдущие задачи!': 'First complete previous tasks!',
    '✅ Завершена:': '✅ Completed:',
    '❌ Отменена:': '❌ Cancelled:',
    
    # main.py comments
    'Точка входа для запуска проекта.': 'Entry point for starting the project.',
    'Это просто скрипт-runner. Сама логика приложения находится в app/main.py': 'This is just a script runner. The app logic is in app/main.py',
    
    # scheduler.py / planner.py residual strings
    'проснулся': 'woke up',
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
