import uvicorn

def main():
    """Точка входа для запуска проекта.
    Это просто скрипт-runner. Сама логика приложения находится в app/main.py
    """
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
