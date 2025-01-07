## The example project will be a simple automation for a gardin

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

