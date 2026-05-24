# import cv2
# import time
# import numpy as np
# from .utils import calculate_angle 
# # UPDATE: Use the new Hybrid Smart Coach
# from .ai_coach2 import AICoach

# class TricepPushdownTrainerAI:
#     def __init__(self):
#         self.counter = 0
#         self.stage = "up"
#         self.prev_angle = 0 # Track previous angle to detect direction
#         self.feedback = "Setup"
#         self.view_mode = "Detecting..." 

#         # --- AI COACH SETUP ---
#         self.coach = AICoach(language="ar") 
#         self.last_setup_voice_time = 0   
#         self.last_coach_voice_time = 0   
#         self.last_squeeze_voice_time = 0 
#         self.coach_cooldown = 4 

#     def process(self, frame, keypoints, confs):
#         # -----------------------------------------------------------
#         # 1. VISIBILITY CHECK (LENIENT)
#         # -----------------------------------------------------------
#         # We strictly need Shoulders (5,6) and Elbows (7,8)
#         required_indices = [5, 6, 7, 8]
        
#         missing_parts = []
#         for i in required_indices:
#             if confs[i] < 0.3: # Lenient threshold
#                 part_name = "Shoulder" if i in [5,6] else "Elbow"
#                 if part_name not in missing_parts:
#                     missing_parts.append(part_name)

#         if missing_parts:
#             error_text = f"MISSING: {missing_parts[0].upper()}"
#             self.feedback = error_text
#             self._draw_feedback(frame, (0, 0, 255)) # Red
            
#             # VOICE: Setup Instruction
#             if time.time() - self.last_setup_voice_time > 8:
#                 self.coach.speak(f"I can't see your Upper body.", urgent=True)
#                 self.last_setup_voice_time = time.time()
#             return frame

#         # -----------------------------------------------------------
#         # 2. VIEW DETECTION
#         # -----------------------------------------------------------
#         has_face = (confs[0] > 0.6) or (confs[1] > 0.6)
#         if has_face:
#             self.view_mode = "FRONT VIEW"
#             mode_color = (255, 200, 0)
#         else:
#             self.view_mode = "BACK VIEW"
#             mode_color = (0, 255, 255)

#         cv2.putText(frame, f"MODE: {self.view_mode}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, mode_color, 2)

#         # -----------------------------------------------------------
#         # 3. ANALYZE FORM (FLARE)
#         # -----------------------------------------------------------
#         def get_flare_angle(shoulder, elbow):
#             dy = elbow[1] - shoulder[1]
#             dx = elbow[0] - shoulder[0]
#             angle_deg = abs(np.arctan2(dy, dx) * 180.0 / np.pi)
#             return abs(90 - angle_deg)

#         l_dev = get_flare_angle(keypoints[5], keypoints[7])
#         r_dev = get_flare_angle(keypoints[6], keypoints[8])
#         max_deviation = max(l_dev, r_dev)
        
#         # LOGIC FLAGS
#         current_color = (0, 255, 0) # Default Green
#         stop_analysis = False       # Stop counting if error exists

#         if max_deviation > 27:
#             self.feedback = "TUCK ELBOWS!"
#             current_color = (0, 0, 255) # Red
#             stop_analysis = True
            
#             # Draw Red Lines
#             if l_dev > 27: cv2.line(frame, tuple(keypoints[5].astype(int)), tuple(keypoints[7].astype(int)), (0,0,255), 3)
#             if r_dev > 27: cv2.line(frame, tuple(keypoints[6].astype(int)), tuple(keypoints[8].astype(int)), (0,0,255), 3)

#             # VOICE: Urgent Correction
#             if time.time() - self.last_coach_voice_time > self.coach_cooldown:
#                 self.coach.speak("Tuck your elbows!", urgent=True)
#                 self.last_coach_voice_time = time.time()

#         # -----------------------------------------------------------
#         # 4. REP COUNTING & SMART SQUEEZE (Runs if NO Error)
#         # -----------------------------------------------------------
#         if not stop_analysis:
#             angles = []
#             if confs[9] > 0.5: angles.append(calculate_angle(keypoints[5], keypoints[7], keypoints[9]))
#             if confs[10] > 0.5: angles.append(calculate_angle(keypoints[6], keypoints[8], keypoints[10]))
            
#             if angles:
#                 avg_angle = sum(angles) / len(angles)
                
#                 # --- SMART DIRECTION LOGIC ---
#                 # Positive (+) = Pushing Down (Good)
#                 # Negative (-) = Returning Up (Retreating)
#                 angle_change = avg_angle - self.prev_angle 

#                 # A. GOING UP (Reset)
#                 if avg_angle < 85:
#                     self.stage = "up"
#                     self.feedback = "PUSH DOWN"
#                     current_color = (255, 255, 255) # White
                
#                 # B. SQUEEZE ZONE (The "Don't Quit" Check)
#                 # Only warn if: 
#                 # 1. In the zone (120-155)
#                 # 2. Stage is UP (You haven't finished yet)
#                 # 3. Angle Change is NEGATIVE (You started giving up and going back)
#                 elif 90 < avg_angle < 155 and self.stage == "up":
                    
#                     if angle_change < -1.0: # Filter small jitters
#                         # VOICE: Urgent Motivation
#                         if time.time() - self.last_squeeze_voice_time > 4:
#                             self.coach.speak("Don't quit! Squeeze down.", urgent=True)
#                             self.last_squeeze_voice_time = time.time()
                        
#                         self.feedback = "DON'T QUIT! SQUEEZE!"
#                         current_color = (0, 165, 255) # Orange

#                 # C. FINISHED REP
#                 elif avg_angle > 165 and self.stage == "up":
#                     self.stage = "down"
#                     self.counter += 1
#                     self.feedback = "GOOD!"
#                     current_color = (0, 255, 0) # Green
                    
#                     # --- NEW HYBRID VOICE LOGIC ---
#                     # 1. Milestone Reps (Every 3rd): Gemini Hype
#                     if self.counter % 3 == 0:
#                         prompt = f"User just hit {self.counter} tricep pushdowns. Hype them up."
#                         self.coach.speak(prompt, urgent=False, use_gemini=True, is_motivation=True)
                    
#                     # 2. Standard Reps (Every 2nd): Simple Count
#                     elif self.counter % 2 == 0:
#                         self.coach.speak(f"{self.counter}", urgent=False, use_gemini=False, is_motivation=False)

#                 # Store current angle for next frame comparison
#                 self.prev_angle = avg_angle

#             else:
#                 if not stop_analysis:
#                     self.feedback = "WRISTS HIDDEN"
#                     current_color = (100, 100, 100)

#         # 5. DRAW FEEDBACK (Single Call)
#         self._draw_feedback(frame, current_color)
        
#         # 6. DRAW SKELETON
#         for idx_set in [(5,7,9), (6,8,10)]:
#             if all(confs[i] > 0.3 for i in idx_set):
#                 a, b, c = idx_set
#                 # Don't draw white lines over red error lines
#                 if stop_analysis: continue
                
#                 cv2.line(frame, tuple(keypoints[a].astype(int)), tuple(keypoints[b].astype(int)), (255,255,255), 2)
#                 cv2.line(frame, tuple(keypoints[b].astype(int)), tuple(keypoints[c].astype(int)), (255,255,255), 2)

#         return frame

#     def _draw_feedback(self, frame, color):
#         # Background Box
#         cv2.rectangle(frame, (0,0), (640, 60), (30,30,30), -1)
        
#         # Top Text
#         cv2.putText(frame, f"MODE: {self.view_mode}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
#         cv2.putText(frame, f"REPS: {self.counter}", (250, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
        
#         # Bottom Feedback (Centered)
#         text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
#         text_x = (640 - text_size[0]) // 2
#         cv2.putText(frame, self.feedback, (text_x, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)





#######################################################################################


import cv2
import time
import numpy as np
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach2 import AICoach
from AI_EXE.messages import (
    CANT_SEE_BODY,
    TUCK_ELBOWS, DONT_QUIT,LOCK_ARMS
)

class TricepPushdownTrainerAI:
    def __init__(self):
        self.counter  = 0
        self.stage    = "up"
        self.prev_angle = 0
        self.feedback = "Setup"
        self.view_mode = "Detecting..."

        self.coach = AICoach()
        self.last_setup_voice_time   = 0
        self.last_coach_voice_time   = 0
        self.last_squeeze_voice_time = 0
        self.coach_cooldown = 4

    def process(self, frame, keypoints, confs):
        # ── 1. VISIBILITY CHECK ───────────────────────────────
        required_indices = [5, 6, 7, 8]
        missing_parts = []
        for i in required_indices:
            if confs[i] < 0.3:
                part_name = "Shoulder" if i in [5, 6] else "Elbow"
                if part_name not in missing_parts:
                    missing_parts.append(part_name)

        if missing_parts:
            self.feedback = f"MISSING: {missing_parts[0].upper()}"
            self._draw_feedback(frame, (0, 0, 255))
            if time.time() - self.last_setup_voice_time > 8:
                self.coach.speak(CANT_SEE_BODY, urgent=True)
                self.last_setup_voice_time = time.time()
            return frame

        # ── 2. VIEW DETECTION ─────────────────────────────────
        has_face = (confs[0] > 0.6) or (confs[1] > 0.6)
        if has_face:
            self.view_mode = "FRONT VIEW"
            mode_color = (255, 200, 0)
        else:
            self.view_mode = "BACK VIEW"
            mode_color = (0, 255, 255)

        cv2.putText(frame, f"MODE: {self.view_mode}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, mode_color, 2)

        # ── 3. ELBOW FLARE CHECK ──────────────────────────────
        def get_flare_angle(shoulder, elbow):
            dy = elbow[1] - shoulder[1]
            dx = elbow[0] - shoulder[0]
            return abs(90 - abs(np.arctan2(dy, dx) * 180.0 / np.pi))

        l_dev = get_flare_angle(keypoints[5], keypoints[7])
        r_dev = get_flare_angle(keypoints[6], keypoints[8])
        max_deviation = max(l_dev, r_dev)

        current_color = (0, 255, 0)
        stop_analysis = False

        if max_deviation > 27:
            self.feedback = "TUCK ELBOWS!"
            current_color = (0, 0, 255)
            stop_analysis = True

            if l_dev > 27:
                cv2.line(frame, tuple(keypoints[5].astype(int)),
                         tuple(keypoints[7].astype(int)), (0, 0, 255), 3)
            if r_dev > 27:
                cv2.line(frame, tuple(keypoints[6].astype(int)),
                         tuple(keypoints[8].astype(int)), (0, 0, 255), 3)

            if time.time() - self.last_coach_voice_time > self.coach_cooldown:
                self.coach.speak(TUCK_ELBOWS, urgent=True)
                self.last_coach_voice_time = time.time()

        # ── 4. REP COUNTING ───────────────────────────────────
        if not stop_analysis:
            angles = []
            if confs[9]  > 0.5: angles.append(calculate_angle(keypoints[5], keypoints[7], keypoints[9]))
            if confs[10] > 0.5: angles.append(calculate_angle(keypoints[6], keypoints[8], keypoints[10]))

            if angles:
                avg_angle    = sum(angles) / len(angles)
                angle_change = avg_angle - self.prev_angle

                # A. Going up (reset)
                if avg_angle < 85:
                    self.stage    = "up"
                    self.feedback = "PUSH DOWN"
                    current_color = (255, 255, 255)

                # B. Squeeze zone — don't quit
                elif 90 < avg_angle < 155 and self.stage == "up":
                    if angle_change < -1.0:
                        if time.time() - self.last_squeeze_voice_time > 4:
                            self.coach.speak(DONT_QUIT, urgent=True)
                            self.last_squeeze_voice_time = time.time()
                        self.feedback = "DON'T QUIT! SQUEEZE!"
                        current_color = (0, 165, 255)

                # C. Finished rep
# C. Finished rep
                elif avg_angle > 165 and self.stage == "up":
                    self.stage    = "down"
                    self.counter += 1
                    self.feedback = "GOOD!"

                # D. Lock arms — only triggers AFTER a rep is counted (stage == "down")
                # and angle is dropping again before reaching full reset (< 85)
                elif self.stage == "down" and 85 < avg_angle < 140 and angle_change < -2.0:
                    self.feedback = "LOCK ARMS!"
                    current_color = (0, 165, 255)
                    if time.time() - self.last_coach_voice_time > self.coach_cooldown:
                        self.coach.speak(LOCK_ARMS, urgent=True)
                        self.last_coach_voice_time = time.time()

                    if self.counter % 3 == 0:
                        prompt = f"User just hit {self.counter} tricep pushdowns. Hype them up."
                        self.coach.speak(prompt, urgent=False, use_gemini=True, is_motivation=True)
                    elif self.counter % 2 == 0:
                        self.coach.speak(f"{self.counter}", urgent=False, use_gemini=False, is_motivation=False)

                self.prev_angle = avg_angle

            else:
                self.feedback = "WRISTS HIDDEN"
                current_color = (100, 100, 100)

        # ── 5. DRAW ───────────────────────────────────────────
        self._draw_feedback(frame, current_color)

        for idx_set in [(5, 7, 9), (6, 8, 10)]:
            if all(confs[i] > 0.3 for i in idx_set) and not stop_analysis:
                a, b, c = idx_set
                cv2.line(frame, tuple(keypoints[a].astype(int)),
                         tuple(keypoints[b].astype(int)), (255, 255, 255), 2)
                cv2.line(frame, tuple(keypoints[b].astype(int)),
                         tuple(keypoints[c].astype(int)), (255, 255, 255), 2)

        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"MODE: {self.view_mode}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        text_x = (640 - text_size[0]) // 2
        cv2.putText(frame, self.feedback, (text_x, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)