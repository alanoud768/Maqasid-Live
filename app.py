"""Maqasid Live: run with  python app.py  then open http://localhost:5000

The OpenAI key is read from the OPENAI_API_KEY environment variable. It is never written in any file.
Without a key (or without internet) the app still works: it shows recorded answers from our study instead,
and says so on screen.
"""
import os
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, request, send_from_directory

from maqasid import core

APP_VERSION = "10"
core.check_frozen()
SUMMARY = core.study_summary()        # all 1,000 recorded answers, scored by this app's own code
app = Flask(__name__, static_folder="static", static_url_path="/static")
DAILY_LIMIT = int(os.environ.get("MAQASID_DAILY_LIMIT", "400"))   # live runs per day, to protect the credit
SHOW_TOP = 3   # recorded mode shows the clearest matching pairs from the study for each profile, in turn


def _showcase():
    """For every profile (told or private, traveller, interest), rank the 20 recorded matching pairs by how clearly
    they differ: places the traveller can't use that Maqasid avoided first, then extra fully suitable places.
    The page says these are selected examples; the whole-study charts still use all 1,000 answers."""
    out = {}
    for disclose in (False, True):
        g_alone, g_maq = ("A", "D") if disclose else ("B", "C")
        for d in core.DISABILITIES:
            kept = [i for i in core.ALL_IDS if core.verdict(i, d)["outcome"] != "out"]
            for it in core.INTEREST:
                ranked = []
                for rep in range(1, 21):
                    a = core.score(core.recorded(g_alone, d, it, rep)["parsed"], d, 200, core.ALL_IDS, it)
                    m = core.score(core.recorded(g_maq, d, it, rep)["parsed"], d, 200, kept, it)
                    ranked.append((a["unusable"] - m["unusable"], m["full"] - a["full"], -rep, rep))
                ranked.sort(reverse=True)
                out[(disclose, d, it)] = [r[3] for r in ranked[:SHOW_TOP]]
    return out


SHOWCASE = _showcase()
_turn = {}
MODEL_NAME = os.environ.get("MAQASID_MODEL_NAME", "GPT-6.1 Sol")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify({
        "version": APP_VERSION,
        "live": core.live_available(),
        "model_name": MODEL_NAME,
        "interests": [{"key": r["interest_key"], "text": r["interest_text"]} for r in core.INTERESTS],
        "today": core.today_stats(),
        "summary": SUMMARY,
    })


@app.post("/api/filter")
def run_filter():
    body = request.get_json(force=True)
    disability = body.get("disability")
    if disability not in core.DISABILITIES:
        return jsonify({"error": "unknown traveller"}), 400
    order = core.shuffled_order()
    out = core.filter_run(disability, order)
    out["order"] = order
    return jsonify(out)


@app.post("/api/ask")
def ask():
    body = request.get_json(force=True)
    disability = body.get("disability")
    interest = body.get("interest")
    disclose = bool(body.get("disclose", False))
    budget = int(body.get("budget", 200))
    order = body.get("order") or core.shuffled_order()
    if disability not in core.DISABILITIES or interest not in core.INTEREST or not (0 <= budget <= 1000):
        return jsonify({"error": "bad request"}), 400
    if sorted(order) != sorted(core.ALL_IDS):
        order = core.shuffled_order()

    # Maqasid's list: the same order, without the places that fail an Essential rule for this traveller.
    kept = [pid for pid in order if core.verdict(pid, disability)["outcome"] != "out"]
    message = core.traveller_message(interest, disability, disclose, budget)
    # Study groups: not disclosed = B (alone) and C (Maqasid); disclosed = A (alone) and D (Maqasid).
    g_alone, g_maq = ("A", "D") if disclose else ("B", "C")

    note, mode = None, "recorded"
    if core.live_available() and core.today_stats()["runs"] < DAILY_LIMIT:
        try:
            with ThreadPoolExecutor(2) as pool:
                fa = pool.submit(core.ask_live, order, message)
                fm = pool.submit(core.ask_live, kept, message)
                alone, maq = fa.result(), fm.result()
            mode = "live"
        except Exception as e:  # no internet, no credit, timeout...: fall back, and say so
            note = f"The live request did not work ({type(e).__name__}), so this search shows recorded answers from our study."
    if mode == "recorded":
        key = (disclose, disability, interest)   # the same repeat on both sides: a matching pair from the study
        k = _turn.get(key, 0); _turn[key] = k + 1
        rep = SHOWCASE[key][k % len(SHOWCASE[key])]
        alone = core.recorded(g_alone, disability, interest, rep)
        maq = core.recorded(g_maq, disability, interest, rep)
        alone_shown = core.ALL_IDS
        maq_shown = [i for i in core.ALL_IDS if core.verdict(i, disability)["outcome"] != "out"]
        if budget != 200:
            note = (note + " " if note else "") + "Recorded answers were asked with a budget of 200 SAR."
        budget = 200
        message = core.traveller_message(interest, disability, disclose, 200)
    else:
        alone_shown, maq_shown = order, kept

    s_alone = core.score(alone["parsed"], disability, budget, alone_shown, interest)
    s_maq = core.score(maq["parsed"], disability, budget, maq_shown, interest)
    today = core.record_visit(s_alone["main_outcome"]) if mode == "live" else core.today_stats()
    return jsonify({
        "mode": mode, "note": note, "message": message, "budget": budget,
        "disclose": disclose, "groups": [g_alone, g_maq], "n_all": len(order), "n_kept": len(kept),
        "alone": {**s_alone, "seconds": alone.get("seconds")},
        "maqasid": {**s_maq, "seconds": maq.get("seconds")},
        "today": today,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"\n  Maqasid Live is running: open http://localhost:{port}\n"
          f"  Mode: {'LIVE (' + core.MODEL + ')' if core.live_available() else 'RECORDED (no OPENAI_API_KEY set)'}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
