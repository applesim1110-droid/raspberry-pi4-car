import RPi.GPIO as gpio
from angleMPU import anglecalculation
import time
from car_movement import forward, backward, turn_right, turn_left, stop
from mpu6050 import mpu6050

sensor = mpu6050(0x68)
gpio.setmode(gpio.BOARD)
gpio.setwarnings(False)



def get_calibration():
    print("Calibrating... DO NOT TOUCH")
    samples = 100
    total = 0
    for i in range(samples):
        total += sensor.get_gyro_data()['z']
        time.sleep(0.01)
    drift = total / samples
    return drift

def get_pwm_from_data(target_ms):
    PWM = (35.9446 + -53.445* target_ms + 195.52* (target_ms**2))
    if (PWM > 100):PWM = 100
    if (PWM < 0): PWM = 0
    return PWM
    
DURATION = 1.0

def menu():
    print("Robot remote control (Braking Compensated)")
    print("Command: f=forward, b=backward, l=left turn, r=right turn, s=stop")
    
    while True:
        command = input("Enter Command: ").lower()
        try:
            global left_counts, right_counts
            left_counts = 0
            right_counts = 0
            
            if command in ['f', 'b']:
                while True:
                    speed_input = input(f"Enter speed (m/s) [min 0.34][max 0.72]: ")
                    try:
                        if speed_input == "":
                            target_speed = 0.7536
                        else:
                            target_speed = float(speed_input)
                        
                        # 1. Get Exact PWM
                        PWM = get_pwm_from_data(target_speed)
                        
                        # 2. Exact Time MINUS braking time
                        # If DURATION is 1.0, we drive for 0.94s and coast for 0.06s
                        total_time = DURATION 
                        
                        print(f"Target: {target_speed} m/s -> {PWM:.1f}% Power")
                        print(f"Drive Time: {total_time:.3f}s (Coasting last 3cm)")
                        
                        if command == 'f':
                            forward(PWM)
                            time.sleep(DURATION)
                            
                        else:
                            backward(PWM)
                            time.sleep(DURATION)
                            

                        stop()
                        
                        print(f"[DONE] Raw Pulses: L={left_counts} R={right_counts}")
                        break
                        
                    except ValueError:
                        print("Invalid number")
                        continue

            elif command in ['l', 'r']:
                angle = input("Enter angle [Default 45]: ")
                try:
                    angle = int(angle) if angle else 45
                    print(f"Turning {'left' if command=='l' else 'right'} at {angle}")
                    drift = get_calibration()
                    
                    if command == 'l': turn_left()
                    else: turn_right()
                    
                    anglecalculation(drift, angle)
                    stop()
                except ValueError:
                    print("Invalid")
                    
            elif command == 's':
                stop()
            else:
                print("Invalid command")
                
        except ValueError:
            print("Error")
            continue

if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        stop()
        gpio.cleanup()
    