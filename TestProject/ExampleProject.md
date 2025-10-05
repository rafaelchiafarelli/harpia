## The example project will be a simple data logger with visualization
# What is a Data Logger?
Is something that is able to record data from somewhere into some place. And it does that following some rules, as in:
* if the temperature is greater than 
* do 
What are going to log?
* CPU temperature
* CPU Usage
* Memory usage

Domotics project

light-switches
    simple lights (ON/OFF)

power-inlets
    simple power supply (110/220)

action-devices 
    electric gates (sensor-less action - ACT)
    garage door (sensor action OPEN/CLOSE  isOpen/isClosed)

full devices 
    air-conditioning (sensor-full and operation )

sensors
    sensor devices that return a value when asked

automation processes
    simple state-machine (turn-on device one, wait for something, turn-on device 2, wait for another something, select device 3, etc)
    simple closed loop (while variable not something, keep ACT)

loging processes
    get information of all devices in the network

show status
    show status of devices, processes, sensors


a mesh structure of all devices connected through a network
one or many servers
operations
# we will automate the watering of the plants.

low level will consist of a esp32 with wi-fi and a few relays

* R1 -> mains relay. This relay will turn on the 12V power-source and also feed the 127 valves
* R2 -> will turn on the W1 valve (12V)
* R3 -> will turn on the W2 valve (12V)
* R4 -> will turn on the W3 valve (127V)
* R5 -> will turn on the W4 valve (127V)

relays are scheduled to be turned on by:
    * days of the week
    * hours of the day
    * minutes of the hour
    * seconds of the minute.
    for example:
    R2 will activate in all the days of the week, 

R1 has a feed logic --> it must be on so the others can be on.
    scheduling of the others will make this schedule as well.
        if we schedukle
R2 
