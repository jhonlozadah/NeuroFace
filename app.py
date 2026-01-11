from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from gtts import gTTS
import datetime
import whisper
import subprocess
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
import base64
import requests

app = Flask(__name__)
app.secret_key = "CAMBIA_ESTO_POR_ALGO_SEGURO"

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

FACEPP_API_KEY = "6Tu6dp3Vy6LcRALXaQ5mMZIdzZKna_C6"
FACEPP_API_SECRET = "accWLe5G_ivSImn2x-oNvAwUXZZwcUaN"
FACEPP_COMPARE_URL = "https://api-us.faceplusplus.com/facepp/v3/compare"
FACEPP_DETECT_URL = "https://api-us.faceplusplus.com/facepp/v3/detect"

WHISPER_MODEL = whisper.load_model("base") 
def get_audio_duration(path):
    try:
        result = subprocess.run(
            [ 
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        duration_str = result.stdout.strip()
        if not duration_str:
            return None
        return float(duration_str)
    except Exception as e:
        print("Error obteniendo duración de audio:", e)
        return None


def format_duration(seconds):
    """
    Convierte segundos (float) en formato m:ss, 
    por ejemplo 3.4 -> '0:03', 75 -> '1:15'.
    """
    if seconds is None:
        return "0:00"
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "mistralai/mistral-7b-instruct"

STABILITY_API_KEY = "sk-VKfa8BTyep1Ae1v2ps2GOHCVGZHbLZFi9whmQ5kM9Z2XpN6j"
STABILITY_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"

PSICOLOGIA_SYSTEM_PROMPT = """
Eres un asistente emocionalmente cálido, empático y profesional especializado
EXCLUSIVAMENTE en psicología, salud mental y bienestar emocional.

TU ESTILO:
- Tono cálido, humano, cercano y validante.
- Puedes saludar, acompañar, conversar y mostrar empatía naturalmente.
- Utiliza un lenguaje emocionalmente inteligente.
- Ayuda a reflexionar, no a juzgar.

TU ALCANCE:
Puedes hablar solo de temas psicológicos:
- Emociones
- Ansiedad, estrés, tristeza, miedo
- Autoestima, autoconcepto
- Relaciones interpersonales
- Duelo, rupturas
- Comunicación asertiva
- Autocuidado, rutinas saludables
- Motivación y bienestar

SI EL TEMA NO TIENE RELACIÓN CON PSICOLOGÍA:
No des información técnica.
En su lugar responde con cariño:
"Entiendo tu interés, pero solo puedo ayudarte en temas de psicología y bienestar emocional.
Si quieres, podemos hablar sobre cómo te sientes o alguna situación emocional que estés viviendo."

NORMAS ÉTICAS:
- No des diagnósticos clínicos formales.
- Si el usuario expresa riesgo (autolesión, suicidio, abuso):
  • valida emociones,
  • expresa cuidado,
  • recomiéndale buscar ayuda profesional o servicios de emergencia.

OBJETIVO:
Acompañar emocionalmente al usuario con sensibilidad, contención y profesionalismo.
"""

def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            phone TEXT,
            photo_path TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

with app.app_context():
    init_db()

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        full_name = request.form.get("full_name")
        phone = request.form.get("phone")
        password = request.form.get("password")
        photo_data_url = request.form.get("photo")  

        if not all([username, email, password, photo_data_url]):
            flash("Completa todos los campos obligatorios.", "danger")
            return redirect(url_for("register"))

        if "," in photo_data_url:
            header, encoded = photo_data_url.split(",", 1)
        else:
            encoded = photo_data_url

        try:
            img_bytes = base64.b64decode(encoded)
        except Exception:
            flash("Error al procesar la imagen capturada.", "danger")
            return redirect(url_for("register"))

        filename = secure_filename(f"{username}_face.png")
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        with open(filepath, "wb") as f:
            f.write(img_bytes)

        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users (username, email, password_hash, full_name, phone, photo_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, email, password_hash, full_name, phone, filepath),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("Usuario o correo ya registrados.", "danger")
            return redirect(url_for("register"))

        conn.close()
        flash("Registro exitoso. Ahora inicia sesión.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username_or_email")
        password = request.form.get("password")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email),
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"] 
            flash("Has iniciado sesión correctamente.", "success")
            return redirect(url_for("index"))

        else:
            flash("Credenciales inválidas.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/face_login", methods=["POST"])
def face_login():
    photo_data_url = request.form.get("photo")
    if not photo_data_url:
        return jsonify({"success": False, "message": "No se recibió imagen."})

    if "," in photo_data_url:
        header, encoded = photo_data_url.split(",", 1)
    else:
        encoded = photo_data_url

    try:
        login_img_base64 = encoded
    except Exception:
        return jsonify({"success": False, "message": "Error al procesar la imagen."})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        return jsonify({"success": False, "message": "No hay usuarios registrados."})

    CONFIDENCE_THRESHOLD = 70 

    for user in users:
        stored_image_path = user["photo_path"]
        if not os.path.exists(stored_image_path):
            continue

        with open(stored_image_path, "rb") as img_file:
            stored_image_bytes = img_file.read()
            stored_image_base64 = base64.b64encode(stored_image_bytes).decode("utf-8")

        data = {
            "api_key": FACEPP_API_KEY,
            "api_secret": FACEPP_API_SECRET,
            "image_base64_1": stored_image_base64,
            "image_base64_2": login_img_base64,
        }

        try:
            response = requests.post(FACEPP_COMPARE_URL, data=data)
            resp_json = response.json()

            if "confidence" in resp_json:
                confidence = resp_json["confidence"]
                if confidence >= CONFIDENCE_THRESHOLD:
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["full_name"] = user["full_name"] 
                    return jsonify(
                        {
                            "success": True,
                            "message": f"Bienvenido, {user['username']}. Confianza: {confidence}",
                        }
                    )

        except Exception as e:
            print("Error al llamar a Face++:", e)
            return jsonify({"success": False, "message": "Error con la API de Face++."})

    return jsonify(
        {
            "success": False,
            "message": "No se encontró coincidencia. Intenta de nuevo o verifica tu registro.",
        }
    )

@app.route("/index")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session.get("username"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))

@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():
    if "user_id" not in session:
        return redirect(url_for("login"))

    chat_history = session.get("chat_history", [])
    speak_last = False

    if request.method == "POST" and "audio" in request.files:

        audio_file = request.files["audio"]

        filename = f"user_{session['user_id']}_{len(chat_history)}.webm"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        audio_file.save(filepath)

        abs_path = os.path.abspath(filepath)
        print("Audio guardado en:", abs_path, "exists:", os.path.exists(abs_path))

        try:
            result = WHISPER_MODEL.transcribe(abs_path, language="es")
            user_text = result.get("text", "").strip()
            print("Transcripción Whisper local:", user_text)
        except Exception as e:
            print("Error Whisper local:", e)
            user_text = ""

        user_dur_sec = get_audio_duration(abs_path)
        user_dur_str = format_duration(user_dur_sec)
        chat_history.append({
            "sender": "user",
            "type": "audio",
            "audio_url": url_for("uploaded_file", filename=filename),
            "duration": user_dur_str,
            "time": datetime.datetime.now().strftime("%H:%M")
        })

        if user_text:
            messages = [{"role": "system", "content": PSICOLOGIA_SYSTEM_PROMPT}]
            messages.append({"role": "user", "content": user_text})

            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": messages,
                        "temperature": 0.8,
                    },
                    timeout=40,
                )

                if response.status_code == 200:
                    data = response.json()
                    ai_text = data["choices"][0]["message"]["content"].strip()
                else:
                    print("Error OpenRouter:", response.status_code, response.text)
                    ai_text = "Hubo un problema al conectar al asistente."

            except Exception as e:
                print("Error IA:", e)
                ai_text = "Lo siento, ocurrió un error al procesar tu mensaje."
        else:
            ai_text = "Lo siento, no pude escuchar bien tu mensaje."

        if not ai_text or not ai_text.strip():
            ai_text = "Lo siento, hubo un problema al generar mi respuesta, pero estoy aquí para acompañarte."

        print("Texto que se enviará a gTTS:", repr(ai_text))

        bot_audio_filename = f"bot_{session['user_id']}_{len(chat_history)}.mp3"
        bot_audio_path = os.path.join(app.config["UPLOAD_FOLDER"], bot_audio_filename)

        try:
            tts = gTTS(ai_text, lang='es')
            tts.save(bot_audio_path)

            chat_history.append({
                "sender": "bot",
                "type": "audio",
                "audio_url": url_for("uploaded_file", filename=bot_audio_filename),
                "duration": "0:07",
                "time": datetime.datetime.now().strftime("%H:%M")
            })

        except Exception as e:
            print("Error gTTS:", e)
            chat_history.append({
                "sender": "bot",
                "type": "text",
                "text": ai_text,
            })

        session["chat_history"] = chat_history
        return redirect(url_for("chatbot"))
    elif request.method == "POST":
        user_message = request.form.get("message", "").strip()
        if user_message:
            chat_history.append({"sender": "user", "type": "text", "text": user_message})

            messages = [{"role": "system", "content": PSICOLOGIA_SYSTEM_PROMPT}]
            for msg in chat_history[-10:]:
                if msg.get("type") == "audio":
                    continue
                messages.append({
                    "role": "user" if msg["sender"] == "user" else "assistant",
                    "content": msg.get("text", "")
                })

            try:
                response = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": OPENROUTER_MODEL,
                        "messages": messages,
                        "temperature": 0.8,
                    },
                    timeout=40,
                )

                if response.status_code == 200:
                    data = response.json()
                    ai_text = data["choices"][0]["message"]["content"].strip()
                else:
                    print("Error OpenRouter:", response.status_code, response.text)
                    ai_text = "Hubo un problema al conectar al asistente."

            except Exception as e:
                print("Error IA:", e)
                ai_text = "Lo siento, ocurrió un error al procesar tu mensaje."

            if not ai_text or not ai_text.strip():
                ai_text = "Lo siento, tuve un problema al responder, pero estoy aquí contigo."

            bot_audio_filename = f"bot_{session['user_id']}_{len(chat_history)}.mp3"
            bot_audio_path = os.path.join(app.config["UPLOAD_FOLDER"], bot_audio_filename)

            try:
                tts = gTTS(ai_text, lang='es')
                tts.save(bot_audio_path)
                bot_dur_sec = get_audio_duration(bot_audio_path)
                bot_dur_str = format_duration(bot_dur_sec)

                chat_history.append({
                    "sender": "bot",
                    "type": "audio",
                    "audio_url": url_for("uploaded_file", filename=bot_audio_filename),
                    "duration": bot_dur_str,
                    "time": datetime.datetime.now().strftime("%H:%M")
                })

            except Exception as e:
                print("Error gTTS (texto):", e)
                chat_history.append({"sender": "bot", "type": "text", "text": ai_text})

            session["chat_history"] = chat_history
            return redirect(url_for("chatbot"))

    return render_template(
        "chatbot.html",
        chat_history=chat_history,
        username=session.get("username"),
        speak_last=False
    )

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/emociones")
def emociones():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("emociones.html", username=session.get("username"))

def get_dominant_emotion(emotion_dict):
    """Recibe el dict de emociones de Face++ y devuelve la emoción dominante."""
    if not emotion_dict:
        return None
    return max(emotion_dict, key=emotion_dict.get)

@app.route("/api/emocion", methods=["POST"])
def api_emocion():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Sesión no válida."}), 401

    photo_data_url = request.form.get("photo")
    if not photo_data_url:
        return jsonify({"success": False, "message": "No se recibió imagen."})

    if "," in photo_data_url:
        header, encoded = photo_data_url.split(",", 1)
    else:
        encoded = photo_data_url

    data = {
        "api_key": FACEPP_API_KEY,
        "api_secret": FACEPP_API_SECRET,
        "image_base64": encoded,
        "return_attributes": "emotion",
    }

    try:
        resp = requests.post(FACEPP_DETECT_URL, data=data, timeout=20)
        resp_json = resp.json()
    except Exception as e:
        print("Error Face++ emociones:", e)
        return jsonify({"success": False, "message": "Error al conectar con Face++."})

    faces = resp_json.get("faces", [])
    if not faces:
        return jsonify({"success": False, "message": "No se detectó ningún rostro. Intenta de nuevo."})

    attributes = faces[0].get("attributes", {})
    emotion_dict = attributes.get("emotion", {})
    dominant = get_dominant_emotion(emotion_dict)

    if not dominant:
        return jsonify({"success": False, "message": "No se pudo determinar la emoción."})

    session["last_emotion"] = dominant

    return jsonify({
        "success": True,
        "emotion": dominant,
        "redirect_url": url_for("emocion_result")
    })

def translate_prompt_to_english(prompt_es):
    """
    Traduce un prompt al inglés usando OpenRouter.
    Stability AI solo acepta prompts en inglés.
    """
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a translation assistant. Translate the following prompt from Spanish to English. "
                    "Do NOT change meaning, do NOT add creative content. Just translate naturally."
                ),
            },
            {
                "role": "user",
                "content": prompt_es,
            },
        ]

        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Emotion Prompt Translator",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.0, 
            },
            timeout=50,
        )

        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        print("Error translating prompt:", response.text)
        return prompt_es  

    except Exception as e:
        print("Translation error:", e)
        return prompt_es

@app.route("/emocion_result")
def emocion_result():
    if "user_id" not in session:
        return redirect(url_for("login"))

    emotion_key = session.get("last_emotion")
    full_name = session.get("full_name") or session.get("username")

    if not emotion_key:
        flash("Primero analiza tu emoción desde la cámara.", "warning")
        return redirect(url_for("emociones"))

    context = get_emotion_context(emotion_key)
    label = context["label"]
    desc = context["desc"]
    image_prompt_es = context["image_prompt"]
    image_prompt_en = translate_prompt_to_english(image_prompt_es)
    story_prompt = context["story_prompt"]

    image_data_url = None
    if STABILITY_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {STABILITY_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = {
                "text_prompts": [{"text": image_prompt_en}],
                "cfg_scale": 7,
                "height": 1344, 
                "width": 768,
                "samples": 1,
            }

            r = requests.post(STABILITY_URL, headers=headers, json=payload, timeout=60)
            print("Stability status:", r.status_code)
            print("Stability body:", r.text)

            if r.status_code == 200:
                data = r.json()
                artifacts = data.get("artifacts", [])
                if artifacts:
                    b64 = artifacts[0].get("base64")
                    if b64:
                        image_data_url = f"data:image/png;base64,{b64}"
            else:
                print("Error Stability:", r.status_code, r.text)
        except Exception as e:
            print("Error llamando a Stability AI:", e)

    story_text = "No se pudo generar la historia en este momento. Intenta más tarde."
    try:
        user_content = story_prompt
        if full_name:
            user_content = (
                f"El protagonista de la historia se llama {full_name} y la historia debe estar escrita en primera persona, "
                f"como si {full_name} estuviera hablando de sí mismo. Usa su nombre de forma natural a lo largo del relato, "
                f"pero sin abusar de él.\n\n"
                f"{story_prompt}"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un narrador empático y especialista en psicología. "
                    "Escribes historias cortas en primera persona y reflexiones sanas sobre emociones. "
                    "Nunca das diagnósticos clínicos ni recomiendas medicación. "
                    "Mantén un tono cálido, cercano y respetuoso."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5000",
                "X-Title": "Historia emocional",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.9,
            },
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            if "choices" in data and data["choices"]:
                story_text = data["choices"][0]["message"]["content"]
        else:
            print("Error OpenRouter historia:", response.status_code, response.text)
    except Exception as e:
        print("Error con OpenRouter (historia):", e)

    return render_template(
        "emocion_result.html",
        username=session.get("username"),
        emotion_key=emotion_key,
        emotion_label=label,
        emotion_desc=desc,
        image_data_url=image_data_url,
        story_text=story_text,
    )

def get_emotion_context(emotion_key):
    """
    Mapea la emoción de Face++ a texto en español y prompts
    para la imagen y la historia/reflexión.
    """
    emotion_key = (emotion_key or "").lower()

    mapping = {
        "happiness": {
            "label": "alegría",
            "desc": "Tu rostro refleja alegría o una emoción positiva.",
            "image_prompt": "una ilustración cálida y luminosa que represente alegría, esperanza y luz interior, estilo acuarela suave, colores cálidos",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que siente alegría "
                "pero que también desea usar esa alegría para seguir creciendo emocionalmente. "
                "Incluye una reflexión final con consejos prácticos para cuidar su bienestar emocional "
                "y mantener un equilibrio sano, todo en tono cálido y empático."
            ),
        },
        "sadness": {
            "label": "tristeza",
            "desc": "Tu rostro muestra señales de tristeza o melancolía.",
            "image_prompt": "una escena suave y emotiva de una persona mirando por la ventana en un día nublado, con un pequeño rayo de luz que simboliza esperanza, estilo ilustración emocional",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que atraviesa un momento "
                "de tristeza, pero que poco a poco encuentra pequeñas fuentes de esperanza y apoyo. "
                "Incluye una reflexión final con ideas concretas para cuidar de sí mismo, validar sus emociones y "
                "buscar apoyo cuando lo necesite, en tono terapéutico y empático."
            ),
        },
        "anger": {
            "label": "enojo",
            "desc": "Tu rostro refleja enojo, irritación o frustración.",
            "image_prompt": "una imagen artística que represente enojo transformándose en calma, con colores intensos que se convierten en tonos suaves, estilo abstracto emocional",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que siente enojo o frustración, "
                "pero que aprende a reconocer sus límites, a respirar y a expresarse de forma asertiva. "
                "Termina con una reflexión que ofrezca estrategias para manejar el enojo de forma sana y proteger las relaciones."
            ),
        },
        "fear": {
            "label": "miedo",
            "desc": "Tu rostro expresa algún tipo de temor o ansiedad.",
            "image_prompt": "una escena simbólica de una persona caminando por un bosque oscuro hacia una luz al fondo, representando miedo y valentía, estilo ilustración suave",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que siente miedo o ansiedad, "
                "pero que poco a poco se atreve a dar pequeños pasos hacia adelante. "
                "Incluye una reflexión final con técnicas prácticas para manejar el miedo, cuidar la mente y pedir ayuda."
            ),
        },
        "surprise": {
            "label": "sorpresa",
            "desc": "Tu rostro muestra sorpresa o impacto emocional.",
            "image_prompt": "una ilustración de una persona rodeada de elementos inesperados y colores vivos, que representa sorpresa pero también curiosidad y aprendizaje",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que vive una sorpresa intensa, "
                "que puede ser agradable o difícil, y cómo esa experiencia le ayuda a conocerse mejor. "
                "Termina con una reflexión sobre cómo integrar lo inesperado y mantener estabilidad emocional."
            ),
        },
        "disgust": {
            "label": "rechazo",
            "desc": "Tu rostro refleja incomodidad o rechazo.",
            "image_prompt": "una imagen simbólica que represente dejar atrás lo que hace daño y caminar hacia un entorno más sano, con contraste entre colores oscuros y claros",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que siente rechazo o incomodidad "
                "por una situación, y aprende a poner límites y elegir entornos más sanos. "
                "Incluye una reflexión final sobre autocuidado, límites sanos y respeto propio."
            ),
        },
        "neutral": {
            "label": "neutralidad",
            "desc": "Tu expresión es bastante neutra o equilibrada.",
            "image_prompt": "una escena tranquila de un atardecer sereno, con una persona sentada en calma, estilo minimalista y colores suaves",
            "story_prompt": (
                "Escribe una breve historia en primera persona (8–12 líneas) sobre alguien que se siente en un estado neutral, "
                "sin emociones intensas, y reflexiona sobre la importancia de escuchar sus necesidades internas. "
                "Termina con una reflexión sobre cómo aprovechar los momentos de calma para conocerse mejor y cultivar hábitos saludables."
            ),
        },
    }

    return mapping.get(
        emotion_key,
        mapping["neutral"]  
    )
if __name__ == "__main__":
    app.run(debug=True)