import re
from pathlib import Path

replacements = {
    # main.py & bot_polling.py
    'Регистрация + приветствие': 'Registration + welcome',
    'Список активных задач': 'Active tasks list',
    'Отметить задачу выполненной': 'Mark task as completed',
    'Отменить задачу': 'Cancel task',
    'Удалить задачу': 'Delete task',
    'Утренняя сводка (погода + план дня)': 'Morning brief (weather + day plan)',
    'Расписание дня': 'Day schedule',
    'Управление регулярными задачами': 'Manage recurring tasks',
    'Статистика': 'Statistics',
    'Показать все команды': 'Show all commands',

    # constraints.py
    '"Сон"': '"Sleep"',
    '"Школа"': '"School"',
    
    # planner.py
    '"проснулся", "проснулась", "доброе утро", "утро",': '"woke up", "good morning", "morning",',
    '"план на день", "план дня", "что сегодня", "сводка",': '"day plan", "plan for the day", "what\'s today", "brief",',
    '"Данные о погоде недоступны."': '"Weather data unavailable."',
    '"Нет блокировок в расписании."': '"No constraints in the schedule."',
    '"Произошла техническая заминка при обращении к ИИ. Попробуйте ещё раз."': '"A technical error occurred while communicating with the AI. Please try again."',
    '"Сервис ИИ временно недоступен или вернул пустой ответ."': '"AI service is temporarily unavailable or returned an empty response."',
    'Не удалось найти правило в расписании для удаления:': 'Failed to find a constraint in the schedule to delete:',
    'Не удалось добавить правило': 'Failed to add constraint',
    'Не удалось сохранить:': 'Failed to save:',

    # scheduler.py
    '🔔 Напоминание:\n<b>': '🔔 Reminder:\n<b>',
    
    # rescheduler.py
    '⚠️ Перенос задачи:\n<b>': '⚠️ Reschedule task:\n<b>',
    'У вас появилось окно в расписании. Перенести задачу на ': 'You have a free window in your schedule. Move the task to ',

    # callbacks.py (and buttons)
    '✅ Да, верно': '✅ Yes, correct',
    '❌ Нет, введу текстом': '❌ No, I will type',
    '✅ Согласен': '✅ Agree',
    '❌ Оставить как есть': '❌ Leave as is',
    
    # formatter.py
    '📋 Мои задачи': '📋 My tasks',
    '🌅 Мой день': '🌅 My day',
    '📅 Расписание': '📅 Schedule',
    '🔄 Регулярные': '🔄 Recurring',
    '📊 Статистика': '📊 Statistics',
    '❓ Помощь': '❓ Help',
    
    '📝 <b>Активные задачи:</b>\n\n': '📝 <b>Active tasks:</b>\n\n',
    'Дедлайн:': 'Deadline:',
    'Фикс. время:': 'Fixed time:',
    'мин': 'min',
    '✅ Выполнить': '✅ Complete',
    '🗑 Удалить': '🗑 Delete',
    '✅ Понял': '✅ Got it',
    
    '🌅 <b>Ваш день:</b>\n\n': '🌅 <b>Your day:</b>\n\n',
    'Свободных окон:': 'Free windows:',
    'Свободное время:': 'Free time:',
    'занято:': 'busy:',
    
    '🔄 <b>Регулярные задачи:</b>\n\n': '🔄 <b>Recurring tasks:</b>\n\n',
    'Следующий запуск:': 'Next run:',
    'отменена': 'cancelled',
    '❌ Отменить': '❌ Cancel',
    
    '📊 <b>Ваша статистика:</b>\n\n': '📊 <b>Your statistics:</b>\n\n',
    '✅ Выполнено:': '✅ Completed:',
    '❌ Отменено:': '❌ Cancelled:',
    '⏳ Просрочено:': '⏳ Overdue:',
    '⏱ Среднее время:': '⏱ Average time:',
    '🔥 Серия дней:': '🔥 Day streak:',
    'Учеба': 'Study',
    'Дом': 'Home',
    'Здоровье': 'Health',
    'Спорт': 'Sport',
    'Работа': 'Work',
    'Поручения': 'Errands',
    'Разное': 'Other',
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
