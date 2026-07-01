import os
import re
import random
import secrets

from flask import Flask, render_template, request, jsonify, session
from groq import Groq

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY ortam degiskeni ayarlanmamis.\n"
        "Calistirmadan once terminalde ayarla:\n"
        "  Linux/Mac : export GROQ_API_KEY='gsk_...'\n"
        "  Windows CMD: set GROQ_API_KEY=gsk_...\n"
        "  PowerShell : $env:GROQ_API_KEY='gsk_...'"
    )

client = Groq(api_key=GROQ_API_KEY)

app = Flask(__name__)
# Oturum (session) verilerini imzalamak icin gizli anahtar.
# Uretimde bunu da bir ortam degiskeninden okumak daha guvenli olur.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

MISTAKE_LIMIT = 2
CORRECT_POINTS = 5
WRONG_POINTS = -4
MIN_WORD_LEN = 3


# ---------------------------------------------------------------------------
# Groq yardimci fonksiyonlari
# ---------------------------------------------------------------------------

def is_real_word(word: str) -> bool:
    """Kelimenin gercek Ingilizce kelime olup olmadigini Groq ile kontrol et."""
    if len(word) < MIN_WORD_LEN or not word.isalpha():
        return False
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=5,
            temperature=0,
            messages=[{
                "role": "user",
                "content": f'Is "{word}" a real common English word? Answer only YES or NO.'
            }]
        )
        answer = response.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception:
        return len(word) > 4


def parse_words_from_text(text: str, letter: str, used_words: set) -> list[str]:
    """
    API yanitindan hedef harfle baslayan gecerli kelimeleri cikar.
    AI bazen cumle kurarak cevap verebiliyor, bu yuzden noktalama/bosluk
    fark etmeksizin metindeki TUM alfabetik kelimeleri tek tek cikarip
    filtreliyoruz.
    """
    text = text.lower()
    candidates = re.findall(r"[a-z]+", text)

    possible = []
    for word in candidates:
        if len(word) >= MIN_WORD_LEN and word[0] == letter and word not in used_words:
            possible.append(word)

    return possible


def get_ai_word(letter: str, used_words: set) -> str | None:
    """AI'nin belirli harfle baslayan bir kelime secmesini sagla."""
    used_list = ", ".join(list(used_words)[-40:]) if used_words else "none"

    for attempt in range(2):
        try:
            if attempt == 0:
                prompt = (
                    f"Give me ONE common English word that starts with the letter '{letter}'. "
                    f"Do NOT use any of these words: {used_list}. "
                    f"Reply with ONLY the single word, nothing else."
                )
                max_tok = 15
            else:
                prompt = (
                    f"List 8 common English words starting with '{letter}', "
                    f"excluding: {used_list}. "
                    f"One word per line, no numbers, no punctuation."
                )
                max_tok = 100

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=max_tok,
                temperature=0.85 + attempt * 0.1,
                messages=[{"role": "user", "content": prompt}]
            )

            raw = response.choices[0].message.content.strip().lower()

            if attempt == 0:
                word = re.sub(r"[^a-z]", "", raw.split()[0]) if raw.split() else ""
                if word and len(word) >= MIN_WORD_LEN and word[0] == letter and word not in used_words:
                    return word
                words = parse_words_from_text(raw, letter, used_words)
                if words:
                    return random.choice(words)
            else:
                words = parse_words_from_text(raw, letter, used_words)
                if words:
                    return random.choice(words)

        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Oturum durumu yardimcilari
# ---------------------------------------------------------------------------

def new_state() -> dict:
    return {
        "chain": [],
        "used_words": [],
        "player_score": 0,
        "ai_score": 0,
        "turns": 0,
        "mistakes": 0,
        "game_over": False,
    }


def get_state() -> dict:
    if "game" not in session:
        session["game"] = new_state()
    return session["game"]


def save_state(state: dict) -> None:
    session["game"] = state
    session.modified = True


# ---------------------------------------------------------------------------
# Rotalar
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    save_state(new_state())
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(get_state())


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    state = new_state()
    save_state(state)
    return jsonify(state)


@app.route("/api/submit_word", methods=["POST"])
def api_submit_word():
    state = get_state()

    if state["game_over"]:
        return jsonify({**state, "message": "Oyun bitti. Yeni oyun baslat.", "message_type": "error"})

    data = request.get_json(silent=True) or {}
    raw_input = (data.get("word") or "").strip().lower()
    timed_out = bool(data.get("timed_out"))

    used_words = set(state["used_words"])
    required = state["chain"][-1][-1].lower() if state["chain"] else None

    def register_mistake(reason: str):
        state["mistakes"] += 1
        state["player_score"] += WRONG_POINTS
        over = state["mistakes"] >= MISTAKE_LIMIT
        state["game_over"] = over
        save_state(state)
        return jsonify({
            **state,
            "message": reason + (f" ({WRONG_POINTS} puan) [Hata: {state['mistakes']}/{MISTAKE_LIMIT}]"),
            "message_type": "error",
        })

    # Sure doldu
    if timed_out:
        return register_mistake("Sure doldu!")

    word = re.sub(r"[^a-z]", "", raw_input)

    if not word:
        return jsonify({**state, "message": "Bos girdi, tekrar dene.", "message_type": "warn"})

    if len(word) < MIN_WORD_LEN:
        return jsonify({**state, "message": "Kelime en az 3 harf olmali.", "message_type": "warn"})

    if required and word[0] != required:
        return jsonify({**state, "message": f"'{word}' '{required.upper()}' ile baslamiyor!", "message_type": "warn"})

    if word in used_words:
        return jsonify({**state, "message": f"'{word}' zaten kullanildi!", "message_type": "warn"})

    if not is_real_word(word):
        return register_mistake(f"'{word}' gecerli bir Ingilizce kelime degil!")

    # Kelime kabul edildi
    state["chain"].append(word)
    state["used_words"].append(word)
    state["player_score"] += CORRECT_POINTS
    state["turns"] += 1
    used_words.add(word)

    messages = [f"'{word}' kabul edildi! (+{CORRECT_POINTS})"]

    next_letter = word[-1]
    ai_word = get_ai_word(next_letter, used_words)

    if ai_word:
        state["chain"].append(ai_word)
        state["used_words"].append(ai_word)
        state["ai_score"] += CORRECT_POINTS
        state["turns"] += 1
        messages.append(f"AI: '{ai_word}' (+{CORRECT_POINTS})")
    else:
        state["player_score"] += CORRECT_POINTS
        messages.append(f"AI '{next_letter.upper()}' ile kelime bulamadi! +{CORRECT_POINTS} bonus sana.")

    save_state(state)
    return jsonify({**state, "message": "  ".join(messages), "message_type": "success"})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)