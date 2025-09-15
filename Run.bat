@echo off
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --app-dir "D:\WebApp\my_chatbot_server"
timeout /t 5 > nul
echo.
pause
