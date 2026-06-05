import uvicorn

def main():
    """Entry point for starting the project.
    This is just a script runner. The app logic is in app/main.py
    """
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()

