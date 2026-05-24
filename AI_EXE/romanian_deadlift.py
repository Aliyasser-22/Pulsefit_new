import cv2
import numpy as np
from collections import deque
from AI_EXE.utils import calculate_angle
from AI_EXE.ai_coach3 import AICoach
from AI_EXE.messages import (
    ROMANIAN_DEADLIFT_SETUP,
    ROMANIAN_DEADLIFT_HINGE,
    ROMANIAN_DEADLIFT_UP,
    ROMANIAN_DEADLIFT_BACK,
    GOOD_REP,
)


class RomanianDeadliftTrainerAI:
    def __init__(self, language="ar"):
        self.counter = 0
        self.stage   = "up"          # "up" = standing/lockout, "down" = hip hinge
        self.feedback = "Setup"
        self.coach = AICoach(language=language)

        self.angle_history      = deque(maxlen=1)
        self.min_angle_this_rep = 180.0   # tracked while descending (stage=="up")
        self.max_angle_this_rep = 0.0     # tracked while ascending  (stage=="down")

    # ── helpers ───────────────────────────────────────────────────────────
    def _reset_rep_tracking(self):
        self.min_angle_this_rep = 180.0
        self.max_angle_this_rep = 0.0

    def _smooth(self, angle):
        self.angle_history.append(angle)
        return float(np.mean(self.angle_history))

    # ── main loop ─────────────────────────────────────────────────────────
    def process(self, frame, keypoints, confs):
        # Need shoulder, hip, knee (for hip angle) + ankle (for knee angle form check)
        if confs[5] > 0.4 and confs[11] > 0.4 and confs[13] > 0.4 and confs[15] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 5, 11, 13, 15
        elif confs[6] > 0.4 and confs[12] > 0.4 and confs[14] > 0.4 and confs[16] > 0.4:
            s_idx, h_idx, k_idx, a_idx = 6, 12, 14, 16
        else:
            self.feedback = "SHOW SIDE VIEW"
            self._draw_feedback(frame, (0, 0, 255))
            self.coach.on_error(ROMANIAN_DEADLIFT_SETUP, urgent=True)
            return frame

        self.coach.reset_error(ROMANIAN_DEADLIFT_SETUP)

        shoulder = keypoints[s_idx]
        hip      = keypoints[h_idx]
        knee     = keypoints[k_idx]
        ankle    = keypoints[a_idx]

        raw_hip_angle  = calculate_angle(shoulder, hip, knee)
        hip_angle      = self._smooth(raw_hip_angle)
        knee_angle     = calculate_angle(hip, knee, ankle)   # form check only

        current_color  = (0, 255, 0)

        # ── Track extremes per stage ───────────────────────────────────────
        if self.stage == "up":
            # Descending: angle DECREASES → track min
            self.min_angle_this_rep = min(self.min_angle_this_rep, hip_angle)
        else:
            # Ascending: angle INCREASES → track max
            self.max_angle_this_rep = max(self.max_angle_this_rep, hip_angle)

        # ── Form check: knee shouldn't bend too much (squatting the weight) ─
        if knee_angle < 120:
            self.feedback = "DON'T SQUAT IT! HINGE!"
            current_color = (0, 0, 255)
            self.coach.on_error(ROMANIAN_DEADLIFT_BACK)
        else:
            self.coach.reset_error(ROMANIAN_DEADLIFT_BACK)

        # ── 1) Top (Lockout) ──────────────────────────────────────────────
        if hip_angle > 165:
            if self.stage == "down":
                self.stage    = "up"
                self.counter += 1
                self.feedback = "GOOD REP!"
                current_color = (0, 255, 0)

                phase = "starting" if self.counter < 3 else "final" if self.counter > 7 else "middle"
                self.coach.speak_motivation(phase)
                self.coach.on_good_rep()
                self.coach.speak_if_ready(GOOD_REP)

                self.coach.reset_error(ROMANIAN_DEADLIFT_UP)
                self._reset_rep_tracking()
                self.max_angle_this_rep = hip_angle   # seed for descending
            else:
                if knee_angle >= 120:
                    self.feedback = "STAND TALL!"
                    current_color = (0, 255, 0)

        # ── 2) Bottom (Full Hinge / Stretch) ──────────────────────────────
        elif hip_angle < 100:
            if self.stage != "down":
                self.stage    = "down"
                self.feedback = "DRIVE HIPS FORWARD!"
                current_color = (255, 255, 255)
                self.coach.reset_error(ROMANIAN_DEADLIFT_HINGE)
                self._reset_rep_tracking()
                self.min_angle_this_rep = hip_angle   # seed for ascending

        # ── 3) Hysteresis: Descending (stage=="up", angle still mid-range) ─
        elif self.stage == "up" and 100 <= hip_angle <= 165:
            # Reversal check: angle was decreasing but now has gone UP > 15°
            if hip_angle - self.min_angle_this_rep > 15:
                self.feedback = "HINGE DEEPER!"
                current_color = (0, 165, 255)
                self.coach.on_error(ROMANIAN_DEADLIFT_HINGE)
            else:
                if knee_angle >= 120:
                    self.feedback = "HINGING..."
                    current_color = (255, 255, 255)
                self.coach.reset_error(ROMANIAN_DEADLIFT_HINGE)

        # ── 4) Hysteresis: Ascending (stage=="down", angle still mid-range) ─
        elif self.stage == "down" and 100 <= hip_angle <= 165:
            # Reversal check: angle was increasing but now has DROPPED > 15°
            if self.max_angle_this_rep - hip_angle > 15:
                self.feedback = "LOCK HIPS OUT!"
                current_color = (0, 165, 255)
                self.coach.on_error(ROMANIAN_DEADLIFT_UP)
            else:
                if knee_angle >= 120:
                    self.feedback = "DRIVING UP..."
                    current_color = (255, 255, 255)
                self.coach.reset_error(ROMANIAN_DEADLIFT_UP)

        # ── Draw ──────────────────────────────────────────────────────────
        cv2.putText(frame, f"Hip:{int(hip_angle)}", tuple(hip.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Knee:{int(knee_angle)}", tuple(knee.astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.line(frame, tuple(shoulder.astype(int)), tuple(hip.astype(int)), (255, 100, 0), 2)
        cv2.line(frame, tuple(hip.astype(int)),      tuple(knee.astype(int)), current_color, 2)
        cv2.line(frame, tuple(knee.astype(int)),     tuple(ankle.astype(int)), current_color, 2)

        self._draw_feedback(frame, current_color)
        return frame

    def _draw_feedback(self, frame, color):
        cv2.rectangle(frame, (0, 0), (640, 60), (30, 30, 30), -1)
        cv2.putText(frame, f"REPS: {self.counter}", (250, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        text_size = cv2.getTextSize(self.feedback, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
        cv2.putText(frame, self.feedback, ((640 - text_size[0]) // 2, 450),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)