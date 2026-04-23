import RPi.GPIO as gpio
import time

gpio.setmode(gpio.BOARD)
gpio.setwarnings(False)

IN1=37
IN2=35
IN3=33
IN4=31
ENA=40
ENB=29



gpio.setup([IN1,IN2,IN3,IN4],gpio.OUT)
gpio.setup([ENA,ENB],gpio.OUT)
pwmL=gpio.PWM(ENB,1000)
pwmR=gpio.PWM(ENA,1000)

pwmL.start(0)
pwmR.start(0)

def stop():
    gpio.output([IN1, IN2, IN3, IN4], gpio.HIGH)
    pwmL.ChangeDutyCycle(0)
    pwmR.ChangeDutyCycle(0)

def forward(speed=100):
    gpio.output(IN1, gpio.LOW)
    gpio.output(IN2, gpio.HIGH)
    gpio.output(IN3, gpio.LOW)
    gpio.output(IN4, gpio.HIGH)
    pwmL.ChangeDutyCycle(speed)
    pwmR.ChangeDutyCycle(speed)

def backward(speed=100):
    gpio.output(IN1, gpio.HIGH)
    gpio.output(IN2, gpio.LOW)
    gpio.output(IN3, gpio.HIGH)
    gpio.output(IN4, gpio.LOW)
    pwmL.ChangeDutyCycle(speed)
    pwmR.ChangeDutyCycle(speed)

def turn_right(speed=55):
    gpio.output(IN1, gpio.LOW)
    gpio.output(IN2, gpio.HIGH)
    gpio.output(IN3, gpio.HIGH)
    gpio.output(IN4, gpio.LOW)
    pwmL.ChangeDutyCycle(speed)
    pwmR.ChangeDutyCycle(speed)

def turn_left(speed=55):
    gpio.output(IN1, gpio.HIGH)
    gpio.output(IN2, gpio.LOW)
    gpio.output(IN3, gpio.LOW)
    gpio.output(IN4, gpio.HIGH)
    pwmL.ChangeDutyCycle(speed)
    pwmR.ChangeDutyCycle(speed)

def set_motors(left_speed, right_speed):

    # LEFT MOTOR
    if left_speed > 0:
        gpio.output(IN1, gpio.LOW)
        gpio.output(IN2, gpio.HIGH)
    elif left_speed < 0:
        gpio.output(IN1, gpio.HIGH)
        gpio.output(IN2, gpio.LOW)
    else:
        gpio.output(IN1, gpio.LOW)
        gpio.output(IN2, gpio.LOW)

    # RIGHT MOTOR
    if right_speed > 0:
        gpio.output(IN3, gpio.LOW)
        gpio.output(IN4, gpio.HIGH)
    elif right_speed < 0:
        gpio.output(IN3, gpio.HIGH)
        gpio.output(IN4, gpio.LOW)
    else:
        gpio.output(IN3, gpio.LOW)
        gpio.output(IN4, gpio.LOW)

    # Clamp speed
    left_speed = max(0, min(100, int(abs(left_speed))))
    right_speed = max(0, min(100, int(abs(right_speed))))

    pwmL.ChangeDutyCycle(left_speed)
    pwmR.ChangeDutyCycle(right_speed)

try:
    print("Robot moving forward ")
    forward()
    time.sleep(3)

    print("Turning left")
    turn_left()
    time.sleep(2)

    print("Turning right")
    turn_right()
    time.sleep(2)

    print("Reversing")
    backward()
    time.sleep(3)

    print("Stopping")
    stop()
except KeyboardInterrupt:
    pass
finally:
    stop()
    pwmL.stop()
    pwmR.stop()
    gpio.cleanup()



