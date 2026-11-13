@echo off
cd /d "%~dp0"
echo.
echo  Maqasid Live
echo  Paste the OpenAI API key and press Enter (or just press Enter to show the clearest examples from our study).
echo  The key is only kept in this window. It is never saved to a file.
set /p OPENAI_API_KEY=Key: 
if not exist ".installed" (
  echo  First run: installing Flask and the OpenAI library, one moment...
  python -m pip install -q -r requirements.txt && echo ok> .installed
)
start "" http://localhost:5000
python app.py
pause
