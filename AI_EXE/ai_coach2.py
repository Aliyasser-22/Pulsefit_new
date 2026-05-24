
# import os
# import pygame
# import threading
# import queue
# import time
# from gtts import gTTS
# import google.generativeai as genai
# import random

# # --- CONFIGURATION ---
# API_KEY = "AIzaSyDleO-j9kqb2026zV7F9_145GNOPwbEk9s" 
# genai.configure(api_key=API_KEY)

# class AICoach:
#     def __init__(self, language="en"):
#         # Audio setup
#         pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=4096)
        
#         self.audio_queue = queue.Queue()
#         self.is_speaking_urgent = False 
#         self.language = language 
        
#         self.last_motivation_data = None 
#         self.model = genai.GenerativeModel("gemini-2.0-flash")
        
#         # --- MAP ENGLISH KEYS TO YOUR FILES ---
#         self.voice_map = {
#             "Tuck your elbows!": "my_voice/tuck_elbows.mp3",
#             "Relax your shoulders.": "my_voice/relax_shoulders.mp3",
#             "All the way down! Don't cheat.": "my_voice/dont_cheat_down.mp3",
#             "Squeeze! Don't drop it yet.": "my_voice/squeeze_up.mp3",
#             "Please sit down on a chair.": "my_voice/sit_down.mp3",
#             "Please step back so I can see your knees.": "my_voice/step_back.mp3",
#             "Lock your arms! All the way down.": "my_voice/lock_arms.mp3",
#             "Don't rest on your body.": "my_voice/dont_rest.mp3",
#             "Lift elbow off leg.": "my_voice/lift_elbow.mp3",
#             # Add more here as you record them!
#         }

#         threading.Thread(target=self._audio_loop, daemon=True).start()

#     def speak(self, text, urgent=False, use_gemini=False, is_motivation=False):
#         if is_motivation:
#             self.last_motivation_data = {"text": text, "use_gemini": use_gemini}
#         threading.Thread(target=self._generate_and_queue, args=(text, urgent, use_gemini)).start()

#     def _generate_and_queue(self, text, urgent, use_gemini):
#         try:
#             final_text = text
#             filename = ""
#             is_pre_recorded = False

#             # --- 1. CHECK FOR YOUR RECORDED VOICE (Highest Priority) ---
#             # If we are in Arabic Mode AND we have a recording for this error
#             if self.language == "ar" and text in self.voice_map:
#                 potential_file = self.voice_map[text]
#                 if os.path.exists(potential_file):
#                     print(f"🎙️ Playing Your Voice: {potential_file}")
#                     filename = potential_file
#                     is_pre_recorded = True
#                 else:
#                     print(f"⚠️ Recording missing: {potential_file}. Using AI instead.")

#             # --- 2. IF NO RECORDING, USE AI ---
#             if not is_pre_recorded:
                
#                 # A. GEMINI MOTIVATION
#                 if use_gemini and not urgent:
#                     try:
#                         if self.language == "en":
#                             prompt = f"You are a gym bro. Give me a very short motivation phrase (max 4 words) for: {text}."
#                         else:
#                             prompt = f"You are an Egyptian Gym Coach. Give me a funny Egyptian slang phrase (max 4 words) for: {text}. Output ONLY Arabic."

#                         response = self.model.generate_content(prompt)
#                         final_text = response.text.strip().replace('"', '').replace('*', '')
                        
#                         if self.last_motivation_data:
#                             self.last_motivation_data["text"] = final_text
#                             self.last_motivation_data["use_gemini"] = False 
                            
#                     except Exception:
#                         print(f"⚠️ API Busy. Using Backup.")
#                         if self.language == "en":
#                             backup = ["Light weight!", "Yeah buddy!"]
#                         else:
#                             backup = ["عاش يا وحش", "يا جامد", "كمل يا بطل"]
#                         final_text = random.choice(backup)

#                 # B. TRANSLATE URGENT (If no recording found)
#                 if self.language == "ar" and urgent and not is_pre_recorded:
#                     final_text = self._translate_urgent(text)

#                 # C. GENERATE TTS
#                 filename = f"temp_{int(time.time()*1000)}_{random.randint(0,100)}.mp3"
#                 tts_lang = 'ar' if self.language == "ar" else 'en'
#                 tts = gTTS(text=final_text, lang=tts_lang, slow=False)
#                 tts.save(filename)

#             # --- 3. PLAYBACK LOGIC ---
#             if urgent:
#                 if self.is_speaking_urgent:
#                     if not is_pre_recorded: 
#                         try: os.remove(filename)
#                         except: pass
#                     return 

#                 was_playing = pygame.mixer.music.get_busy()
#                 if was_playing:
#                     pygame.mixer.music.stop()
                
#                 with self.audio_queue.mutex:
#                     self.audio_queue.queue.clear()
                
#                 if (was_playing or self.audio_queue.qsize() > 0) and self.last_motivation_data:
#                     threading.Thread(
#                         target=self._generate_and_queue, 
#                         args=(self.last_motivation_data["text"], False, False)
#                     ).start()

#                 # Pass 'is_pre_recorded' so we don't delete your special files!
#                 self.audio_queue.put((filename, True, is_pre_recorded))
#             else:
#                 if self.audio_queue.empty() and not pygame.mixer.music.get_busy() and not self.is_speaking_urgent:
#                     self.audio_queue.put((filename, False, False))
#                 else:
#                     if not is_pre_recorded:
#                         try: os.remove(filename)
#                         except: pass

#         except Exception as e:
#             print(f"Gen Error: {e}")

#     def _translate_urgent(self, text):
#         # ... (Keep your dictionary here as a backup) ...
#         translations = {
#             "Tuck your elbows!": "ضم كوعك جنبك",
#             "Setup": "تجهيز",
#              # ... add the rest ...
#         }
#         return translations.get(text, text)

#     def _audio_loop(self):
#         while True:
#             filename, is_urgent, is_pre_recorded = self.audio_queue.get()
#             try:
#                 self.is_speaking_urgent = is_urgent
#                 pygame.mixer.music.load(filename)
#                 pygame.mixer.music.play()
#                 while pygame.mixer.music.get_busy():
#                     pygame.time.Clock().tick(10)
#                 pygame.mixer.music.unload()
#                 self.is_speaking_urgent = False
#                 time.sleep(0.05)
                
#                 # IMPORTANT: Only delete TEMP files, NEVER delete your recordings
#                 if not is_pre_recorded:
#                     os.remove(filename)
#             except Exception as e:
#                 print(f"Play Error: {e}")
#                 self.is_speaking_urgent = False
#             self.audio_queue.task_done()


###########################################################################################

import os
import pygame
import threading
import queue
import time
from gtts import gTTS
import google.generativeai as genai
import random

from AI_EXE.messages import (
    # Setup
    STEP_BACK, CANT_SEE_BODY, SIT_DOWN,
    # Bicep
    RELAX_SHOULDER, PIN_ELBOW, DONT_REST_BODY,
    LIFT_OFF_LEG, FULL_EXTENSION, SQUEEZE_UP,
    # Tricep
    TUCK_ELBOWS, DONT_QUIT, LOCK_ARMS,
)

# ── CONFIGURATION ─────────────────────────────────────────────
API_KEY = "YOUR_API_KEY_HERE"
genai.configure(api_key=API_KEY)


class AICoach:
    def __init__(self, language="en"):
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=4096)

        self.audio_queue        = queue.Queue()
        self.is_speaking_urgent = False
        self.language           = language
        self.last_motivation_data = None
        self.model = genai.GenerativeModel("gemini-2.0-flash")

        # ── VOICE MAP ─────────────────────────────────────────
        # Keys are imported constants — zero chance of typos.
        # To add a new sentence: add constant to coach_messages.py,
        # import it above, then add one line here.
        self.voice_map = {
            # Setup
            STEP_BACK:      "my_voice/step_back.mp3",
            CANT_SEE_BODY:  "my_voice/cant_see_body.mp3",
            SIT_DOWN:       "my_voice/sit_down.mp3",
            # Bicep curl
            RELAX_SHOULDER: "my_voice/relax_shoulders.mp3",
            PIN_ELBOW:      "my_voice/pin_elbow.mp3",
            DONT_REST_BODY: "my_voice/dont_rest.mp3",
            LIFT_OFF_LEG:   "my_voice/lift_elbow.mp3",
            FULL_EXTENSION: "my_voice/dont_cheat_down.mp3",
            SQUEEZE_UP:     "my_voice/squeeze_up.mp3",
            # Tricep pushdown
            TUCK_ELBOWS:    "my_voice/tuck_elbows.mp3",
            DONT_QUIT:      "my_voice/dont_quit.mp3",
            LOCK_ARMS:      "my_voice/lock_arms.mp3",
        }

        threading.Thread(target=self._audio_loop, daemon=True).start()

    # ── PUBLIC ────────────────────────────────────────────────
    def speak(self, text, urgent=False, use_gemini=False, is_motivation=False):
        if is_motivation:
            self.last_motivation_data = {"text": text, "use_gemini": use_gemini}
        threading.Thread(
            target=self._generate_and_queue,
            args=(text, urgent, use_gemini)
        ).start()

    # ── INTERNAL ──────────────────────────────────────────────
    def _generate_and_queue(self, text, urgent, use_gemini):
        try:
            final_text    = text
            filename      = ""
            is_pre_recorded = False

            # 1. Check for pre-recorded Arabic voice (highest priority)
            if self.language == "ar" and text in self.voice_map:
                potential_file = self.voice_map[text]
                if os.path.exists(potential_file):
                    print(f"🎙️ Playing recorded voice: {potential_file}")
                    filename        = potential_file
                    is_pre_recorded = True
                else:
                    print(f"⚠️ Recording missing: {potential_file}. Falling back to TTS.")

            # 2. No recording — generate audio
            if not is_pre_recorded:

                # A. Gemini motivation phrase
                if use_gemini and not urgent:
                    try:
                        if self.language == "en":
                            prompt = f"You are a gym bro. Give me a very short motivation phrase (max 4 words) for: {text}."
                        else:
                            prompt = f"You are an Egyptian Gym Coach. Give me a funny Egyptian slang phrase (max 4 words) for: {text}. Output ONLY Arabic."

                        response   = self.model.generate_content(prompt)
                        final_text = response.text.strip().replace('"', '').replace('*', '')

                        if self.last_motivation_data:
                            self.last_motivation_data["text"]       = final_text
                            self.last_motivation_data["use_gemini"] = False

                    except Exception:
                        print("⚠️ Gemini API busy. Using backup phrase.")
                        backup     = ["Light weight!", "Yeah buddy!"] if self.language == "en" \
                                     else ["عاش يا وحش", "يا جامد", "كمل يا بطل"]
                        final_text = random.choice(backup)

                # B. Translate urgent message to Arabic if no recording
                if self.language == "ar" and urgent:
                    final_text = self._translate_urgent(text)

                # C. Generate TTS file
                filename = f"temp_{int(time.time()*1000)}_{random.randint(0,100)}.mp3"
                tts_lang = 'ar' if self.language == "ar" else 'en'
                tts = gTTS(text=final_text, lang=tts_lang, slow=False)
                tts.save(filename)

            # 3. Playback logic
            if urgent:
                if self.is_speaking_urgent:
                    if not is_pre_recorded:
                        try: os.remove(filename)
                        except: pass
                    return

                was_playing = pygame.mixer.music.get_busy()
                if was_playing:
                    pygame.mixer.music.stop()

                with self.audio_queue.mutex:
                    self.audio_queue.queue.clear()

                if (was_playing or self.audio_queue.qsize() > 0) and self.last_motivation_data:
                    threading.Thread(
                        target=self._generate_and_queue,
                        args=(self.last_motivation_data["text"], False, False)
                    ).start()

                self.audio_queue.put((filename, True, is_pre_recorded))

            else:
                if self.audio_queue.empty() and not pygame.mixer.music.get_busy() and not self.is_speaking_urgent:
                    self.audio_queue.put((filename, False, False))
                else:
                    if not is_pre_recorded:
                        try: os.remove(filename)
                        except: pass

        except Exception as e:
            print(f"Gen Error: {e}")

    def _translate_urgent(self, text):
        """Fallback Arabic translations when no recording exists."""
        translations = {
            STEP_BACK:      "ارجع للوراء عشان أشوف ركبك",
            CANT_SEE_BODY:  "مش شايف جسمك كويس",
            SIT_DOWN:       "اقعد على الكرسي",
            RELAX_SHOULDER: "ارخي كتفك",
            PIN_ELBOW:      "ثبت كوعك جنبك",
            DONT_REST_BODY: "ماترتكيش على جسمك",
            LIFT_OFF_LEG:   "ارفع كوعك عن رجلك",
            FULL_EXTENSION:  "نزل للآخر ماتغشيش",
            SQUEEZE_UP:     "اعصر فوق ماترميش",
            TUCK_ELBOWS:    "ضم كوعك جنبك",
            DONT_QUIT:      "ماتوقفش اعصر للآخر",
            LOCK_ARMS:      "افرد ذراعك للآخر",
        }
        return translations.get(text, text)

    def _audio_loop(self):
        while True:
            filename, is_urgent, is_pre_recorded = self.audio_queue.get()
            try:
                self.is_speaking_urgent = is_urgent
                pygame.mixer.music.load(filename)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                pygame.mixer.music.unload()
                self.is_speaking_urgent = False
                time.sleep(0.05)
                if not is_pre_recorded:
                    os.remove(filename)
            except Exception as e:
                print(f"Play Error: {e}")
                self.is_speaking_urgent = False
            self.audio_queue.task_done()