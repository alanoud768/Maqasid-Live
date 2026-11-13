#!/bin/bash
cd "$(dirname "$0")"
echo "Maqasid Live"
echo "Paste the OpenAI API key and press Enter (or just press Enter to show the clearest examples from our study)."
echo "The key is only kept in this window. It is never saved to a file."
read -s -p "Key: " OPENAI_API_KEY; echo
export OPENAI_API_KEY
if [ ! -f .installed ]; then echo "First run: installing, one moment..."; python3 -m pip install -q -r requirements.txt && touch .installed; fi
(sleep 2; open http://localhost:5000) &
python3 app.py
