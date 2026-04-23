import RPi.GPIO as gpio
import time
from car_movement import forward, stop

# --- PIN SETUP ---
gpio.setmode(gpio.BOARD)
gpio.setwarnings(False)

L_PIN, R_PIN = 13, 15
left_counts = 0
right_counts = 0

# Theoretical Constants (Used only for comparison)
PULSES_PER_REV = 20.0
WHEEL_DIAMETER_CM = 6.5
C = 3.14159 * WHEEL_DIAMETER_CM
Theoretical_DistPerPulse = C / PULSES_PER_REV

gpio.setup([L_PIN, R_PIN], gpio.IN, pull_up_down=gpio.PUD_UP)

def l_cb(channel): global left_counts; left_counts += 1
def r_cb(channel): global right_counts; right_counts += 1

gpio.add_event_detect(R_PIN, gpio.FALLING, callback=r_cb, bouncetime=2)
gpio.add_event_detect(L_PIN, gpio.FALLING, callback=l_cb, bouncetime=2)

# --- THE TEST ---
print("========================================")
print("   ULTIMATE CALIBRATION TOOL")
print("========================================")
print("1. Place robot at START line.")
print("2. I will drive forward for 2.0 seconds.")
print("3. Get your tape measure ready.")
input("Press ENTER to GO...")

# Drive Blindly (Open Loop)
start_time = time.time()
forward(100) # Full Power
time.sleep(2.0)
stop()

# --- THE CALCULATIONS ---
print("\nStopped!")

# FIX: Calculate this NOW, after the robot has moved
avg_counts = (left_counts + right_counts) / 2
DistanceMeasure = avg_counts * Theoretical_DistPerPulse

print(f"Left Encoder:  {left_counts}")
print(f"Right Encoder: {right_counts}")
print(f"Encoder thinks we moved: {DistanceMeasure:.2f} cm")
print("----------------------------------------")

# Get real world data from user
try:
    real_dist_cm = float(input("Enter REAL measured distance in cm: "))
    
    # 1. Calculate REAL MAX SPEED
    # Speed = Distance / Time (2.0s)
    real_speed_ms = (real_dist_cm / 100.0) / 2.0

    # 3. Calculate LEFT/RIGHT ERROR RATIO
    if left_counts > 0 and right_counts > 0:
        ratio = left_counts / right_counts
    else:
        ratio = 1.0

    print("\n\n========================================")
    print("   COPY THESE VALUES INTO YOUR CODE")
    print("========================================")
    print(f"MAX_V = {real_speed_ms:.4f}")
    print(f"Distance measured by encoder = {DistanceMeasure:.4f}")
    print(f"ENCODER_RATIO = {ratio:.4f}")
    print("========================================")

except ValueError:
    print("Invalid number entered. Run test again.")

gpio.cleanup()