from mpu6050 import mpu6050
import time
from car_movement import stop

sensor=mpu6050(0x68)

def anglecalculation(drift,angle=45):
    current_angle=0
    previous=time.time()
    print("Target angle:{}".format(angle))
    
    while abs(current_angle)< angle-10:
        now=time.time()
        dt=now-previous
        previous=now
        
        gyro_data=sensor.get_gyro_data()
        rotational_speed=gyro_data['z']-drift
        
        #filter - ignore tiny movement
        if abs(rotational_speed)>1.3:
               current_angle+=rotational_speed*dt
               
        print("Current angle; {:.2f}".format(abs(current_angle)))
               
        time.sleep(0.01)
        
    stop()
    print("Target {:.2f} reached!".format(angle))

    





