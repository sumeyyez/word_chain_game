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

LANGUAGE_CONFIG = {
    "en": {
        "letters_pattern": r"[a-z]+",
        "clean_pattern": r"[^a-z]",
    },
    "tr": {
        "letters_pattern": r"[a-zçğıöşü]+",
        "clean_pattern": r"[^a-zçğıöşü]",
    },
}


def smart_lower(text: str, language: str) -> str:
    """
    Turkce'de standart .lower() 'I' harfini yanlis kucultur (I -> i yerine I -> ı olmali).
    Bu fonksiyon dile gore dogru kucultmeyi yapar.
    """
    if language == "tr":
        text = text.replace("İ", "i").replace("I", "ı")
    return text.lower()


# ---------------------------------------------------------------------------
# Groq yardimci fonksiyonlari
# ---------------------------------------------------------------------------

def is_real_word(word: str, language: str) -> bool:
    """Kelimenin gercek bir kelime olup olmadigini Groq ile, secilen dilde kontrol et."""
    if len(word) < MIN_WORD_LEN or not word.isalpha():
        return False
    try:
        if language == "tr":
            content = f'"{word}" gercek, yaygin kullanilan bir Turkce kelime mi? Sadece EVET veya HAYIR yaz.'
        else:
            content = f'Is "{word}" a real common English word? Answer only YES or NO.'

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=5,
            temperature=0,
            messages=[{"role": "user", "content": content}]
        )
        answer = response.choices[0].message.content.strip().upper()
        if language == "tr":
            return answer.startswith("EVET")
        return answer.startswith("YES")
    except Exception:
        return len(word) > 4


def parse_words_from_text(text: str, letter: str, used_words: set, language: str) -> list[str]:
    """
    API yanitindan hedef harfle baslayan gecerli kelimeleri cikar.
    Dile gore (Ingilizce/Turkce) harf kumesi degisir.
    """
    text = smart_lower(text, language)
    pattern = LANGUAGE_CONFIG[language]["letters_pattern"]
    candidates = re.findall(pattern, text)

    possible = []
    for word in candidates:
        if len(word) >= MIN_WORD_LEN and word[0] == letter and word not in used_words:
            possible.append(word)

    return possible


def get_ai_word(letter: str, used_words: set, language: str, recent_endings: list[str] | None = None) -> str | None:
    """
    AI'nin belirli harfle baslayan, secilen dilde, mumkunse cesitli bitis
    harfine sahip bir kelime secmesini sagla.
    """
    used_list = ", ".join(list(used_words)[-40:]) if used_words else "none"
    recent_endings = recent_endings or []

    for attempt in range(2):
        try:
            if language == "tr":
                avoid_text = (
                    f" Su harflerle biten kelimelerden kacinmaya calis: {', '.join(sorted(set(recent_endings)))}."
                    if recent_endings else ""
                )
                prompt = (
                    f"'{letter}' harfiyle baslayan 10 tane yaygin Turkce kelime listele. "
                    f"Su kelimeleri KULLANMA: {used_list}."
                    f"{avoid_text} "
                    f"Kelimelerin son harflerini mumkun oldugunca cesitlendir. "
                    f"Her satira bir kelime yaz, numara veya noktalama kullanma."
                )
            else:
                avoid_text = (
                    f" Try to avoid words ending in these letters: {', '.join(sorted(set(recent_endings)))}."
                    if recent_endings else ""
                )
                prompt = (
                    f"List 10 common English words that start with the letter '{letter}'. "
                    f"Do NOT use any of these words: {used_list}."
                    f"{avoid_text} "
                    f"Try to vary the last letters of the words as much as possible. "
                    f"One word per line, no numbers, no punctuation."
                )

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=140,
                temperature=0.9,
                messages=[{"role": "user", "content": prompt}]
            )

            raw = smart_lower(response.choices[0].message.content.strip(), language)
            words = parse_words_from_text(raw, letter, used_words, language)

            if words:
                preferred = [w for w in words if w[-1] not in recent_endings]
                pool = preferred if preferred else words
                return random.choice(pool)

        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Oturum durumu yardimcilari
# ---------------------------------------------------------------------------

def new_state(language: str = "en") -> dict:
    return {
        "chain": [],
        "used_words": [],
        "player_score": 0,
        "ai_score": 0,
        "turns": 0,
        "mistakes": 0,
        "game_over": False,
        "language": language,
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
    data = request.get_json(silent=True) or {}
    language = data.get("language", "en")
    if language not in LANGUAGE_CONFIG:
        language = "en"
    state = new_state(language)
    save_state(state)
    return jsonify(state)


@app.route("/api/submit_word", methods=["POST"])
def api_submit_word():
    state = get_state()

    if state["game_over"]:
        return jsonify({**state, "message": "Oyun bitti. Yeni oyun baslat.", "message_type": "error"})

    language = state.get("language", "en")
    clean_pattern = LANGUAGE_CONFIG[language]["clean_pattern"]

    data = request.get_json(silent=True) or {}
    raw_input = smart_lower((data.get("word") or "").strip(), language)
    timed_out = bool(data.get("timed_out"))

    used_words = set(state["used_words"])
    required = state["chain"][-1][-1] if state["chain"] else None

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

    word = re.sub(clean_pattern, "", raw_input)

    if not word:
        return jsonify({**state, "message": "Bos girdi, tekrar dene.", "message_type": "warn"})

    if len(word) < MIN_WORD_LEN:
        return jsonify({**state, "message": "Kelime en az 3 harf olmali.", "message_type": "warn"})

    if required and word[0] != required:
        return jsonify({**state, "message": f"'{word}' '{required.upper()}' ile baslamiyor!", "message_type": "warn"})

    if word in used_words:
        return jsonify({**state, "message": f"'{word}' zaten kullanildi!", "message_type": "warn"})

    if not is_real_word(word, language):
        return register_mistake(f"'{word}' gecerli bir kelime degil!")

    # Kelime kabul edildi
    state["chain"].append(word)
    state["used_words"].append(word)
    state["player_score"] += CORRECT_POINTS
    state["turns"] += 1
    used_words.add(word)

    messages = [f"'{word}' kabul edildi! (+{CORRECT_POINTS})"]

    next_letter = word[-1]
    recent_endings = [w[-1] for w in state["chain"][-6:]]
    ai_word = get_ai_word(next_letter, used_words, language, recent_endings=recent_endings)

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