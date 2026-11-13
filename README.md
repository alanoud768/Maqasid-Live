# Maqasid Live

A live demo of our study, in four steps:

1. **Search:** the visitor chooses an access need, an interest and a budget. "Keep my access needs private" is on by default: Maqasid uses the access need to check the places and does not send it to the AI (the study's groups B and C). Turned off, the AI is told too (groups A and D).
2. **Maqasid checks 144 places** with our real filter (`maqasid/filter/filter.py`, the study's frozen version: the app refuses to start if it was changed).
3. **Two phones:** GPT-6.1 Sol is asked twice with the study's exact prompt, once with all 144 places and once with only the places that passed the filter. Every pick is checked with the same filter.
4. **Analysis:** this search, scored with the paper's measures (places you can use, fully suitable, places you can't use, budget, interest, diversity), then charts of all 1,000 recorded study answers.

**Checked:** the app's scoring code was run on all 1,000 recorded answers (groups A, B, C and D) and gives exactly the paper's numbers (for example 89, 40 and 31 of 100 for group B; fully suitable 2.81 / 4.16 / 4.46 / 4.76 for the wheelchair user in B, C, A, D).

## Run it on a laptop (exhibition)

You need Python 3.11 or newer (python.org) and the OpenAI API key.

- **Windows:** double-click `start_windows.bat`, paste the key, press Enter. The browser opens at http://localhost:5000
- **Mac:** double-click `start_mac.command` (first time: right-click › Open), paste the key, press Enter.

The key is only kept in that window. It is never written to a file. Close the window to stop the app.

**No key or no internet?** Just press Enter without a key. The app still works and shows real recorded answers from our study (budget fixed at 200 SAR). For each profile it shows, in turn, the three matching pairs from the study where the difference is clearest, and the page says so. The whole-study charts in Step 4 still use all 1,000 answers. The "Quick examples" buttons set the three profiles with the clearest differences. If the internet drops during a live run, it switches to recorded answers by itself and says so.

## Put it online (for the poster QR code)

1. Upload this folder to a GitHub repository (not the anonymous review one).
2. On render.com: New › Blueprint › choose the repository. It reads `render.yaml`.
3. When asked, paste the key into `OPENAI_API_KEY` (it stays secret on Render).
4. Use the address Render gives you for the QR code.

`MAQASID_DAILY_LIMIT` (default 400) is the most live runs per day. After that the app uses recorded answers, so the credit cannot be emptied by mistake.

## Files

- `app.py`: the web server.
- `maqasid/core.py`: the prompt, the filter calls, the scoring and the stand counter. Same prompt and answer format as `stage1/study_common.py`.
- `maqasid/filter/`: `filter.py`, `places.csv`, `categories.csv` and `rules_frozen.txt`, copied unchanged from `accessibility_filter_v7_4`.
- `maqasid/recorded/study_answers.json`: the 1,000 answers of groups A, B, C and D, used when there is no key.
- `static/index.html`: the page.
- `data/stats.json`: today's stand counter (created on the first live run).
