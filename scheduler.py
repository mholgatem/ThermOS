#! /usr/bin/python

import sqlite3
from datetime import *


conn = sqlite3.connect("logs/thermostat.db", check_same_thread = False)
c = conn.cursor()
    
def getStringDate(string):
    ''' convert string to date or bitmask
        monday-Sunday = 0-6
        return weight, specific dates override
        generic terms'''
    string = string.upper()
    weight = 50
    try:
        bitMask = datetime.strptime(string, "%Y/%m/%d")
        weight = 100
    except:
        bitMask = 0L
        # weekday
        if string == "MONDAYS":
            bitMask = (1L << 0)
            weight = 75
        if string == "TUESDAYS":
            bitMask = (1L << 1)
            weight = 75
        if string == "WEDNESDAYS":
            bitMask = (1L << 2)
            weight = 75
        if string == "THURSDAYS":
            bitMask = (1L << 3)
            weight = 75
        if string == "FRIDAYS":
            bitMask = (1L << 4)
            weight = 75
        if string == "SATURDAYS":
            bitMask = (1L << 5)
            weight = 75
        if string == "SUNDAYS":
            bitMask = (1L << 6)
            weight = 75
        # weekday groups
        if string == "WEEKDAYS":
            bitMask = 31L
            weight = 50
        if string == "WEEKENDS":
            bitMask = 96L
            weight = 50
        if string == "ALWAYS":
            bitMask = 127L
            weight = 25
            
    return bitMask, weight
    
def getStringTime(string):
    ''' convert string to datetime.time()
        formats include 12-hour (3:05 PM/3:05pm)
        and 24-hour (15:05)'''
    try:
        string = string.upper()
        if 'AM' in string or 'PM' in string:
            # format 12-hour clock 3:05pm
            return datetime.strptime(string.replace(' ',''), "%I:%M%p").time()
        else:
            # format 24-hour clock 15:05
            string = "".join([x for x in string if x.isdigit() or x == ":"])
            return datetime.strptime(string, "%I:%M").time()
    except:
        return None
                    


class Calendar(object):
    ''' Creates new Calendar from
        schedule database table. 
        USE getStatus() TO CHECK
        IF SYSTEM SHOULD BE ON/OFF'''
    def __init__(self):
        # Calendar.entries = list of DatabaseEntry
        # Calendar.timeline = list of days, each containing on/off timeframes
        self.loadCalendar(forceReload = True)
        self.lastUpdate = datetime.now()
    
    def loadCalendar(self, forceReload = False):
        if forceReload or (datetime.now() - self.lastUpdate).seconds > 60:
            self.entries = [DatabaseEntry(*x) for x in c.execute('SELECT * FROM schedule').fetchall()]
            self.timeline = [self.constructTimeline(datetime.now() + timedelta(days = x)) for x in xrange(-2,3)]
            self.lastUpdate = datetime.now()
        
    def constructTimeline(self, timelineDate):
        ''' timelineDate = datetime.date()
            Creates new timeFrame and
            populates it'''
        timelineDate = timelineDate.date()
        dailyList = []
        append = dailyList.append
        for entry in self.entries:
            if entry.runOnThisDate(timelineDate) == True:
                append(self.timeFrame(timelineDate, entry))
        return dailyList
    
    def timeFrame(self, timelineDate, entry):
        ''' if timeOff <= timeOn, assume user
            wants to run all night, but reduce
            weight of the request so next days
            schedule can override if necessary '''
        if entry.timeOff <= entry.timeOn:
            nextDay = timedelta(days = 1)
            entry.weight -= 1
        else:
            nextDay = timedelta(days = 0)
        return {"on": datetime.combine(timelineDate, entry.timeOn),
                "off": datetime.combine(timelineDate, entry.timeOff) + nextDay,
                "weight": entry.weight,
                "target_heat": entry.target_heat,
                "target_cool": entry.target_cool
                }
    
    def getStatus(self, now = None):
        ''' returns:
            systemOn (bool) - should system be on right now?
            target_heat/target_cool (Float) - what temp?
            on/off (datetime.date) - when do we turn on/off?'''
        if not now:
            now = datetime.now()
        #make sure calendar is up to date
        self.loadCalendar()
        currentWeight = -1
        systemStatus = {"systemOn": False, "target_heat": None, "target_cool": None}
        for day in self.timeline:
            for entry in day:
                if entry["on"] <= now < entry["off"] and (entry["weight"] > currentWeight):
                    currentWeight = entry["weight"]
                    systemStatus = {"systemOn": True,
                                    "target_heat": entry["target_heat"], 
                                    "target_cool": entry["target_cool"],
                                    "on": entry["on"],
                                    "off": entry["off"]}
        return systemStatus
    
    def getRemainingHoldTime(self):
        x = c.execute('SELECT * FROM schedule WHERE id = -1').fetchone()
        if x:
            if x[3] == 'ALWAYS':
                return 'FOREVER'
            else:
                x = self.timeFrame(datetime.now().date(), DatabaseEntry(*x))
                remaining = (x["off"] - datetime.now())
                if remaining.days < 0:
                    c.execute('DELETE FROM schedule WHERE id = -1')
                    conn.commit()
                    return ''
                return "{0}:{1:02d}:{2:02d}".format( remaining.seconds / 3600, 
                                            (remaining.seconds % 3600)/60, 
                                             remaining.seconds % 60 )
        return ''
        
    def getStatusHTML(self, now = None):
        if not now:
            now = datetime.now()
        #make sure calendar is up to date
        self.loadCalendar()
        currentWeight = -1
        systemStatus = {"systemOn": False, 
                            "on": "", 
                            "off": "", 
                            "title": "No Schedule entries", 
                            "target_heat": "N/A", 
                            "target_cool": "N/A"}
        for day in self.timeline:
            for entry in day:
                if entry["on"] <= now < entry["off"] and (entry["weight"] > currentWeight):
                    currentWeight = entry["weight"]
                    systemStatus = {"systemOn": True,
                                    "title": "CURRENT SCHEDULE:",
                                    "target_heat": entry["target_heat"], 
                                    "target_cool": entry["target_cool"],
                                    "on": entry["on"].time().strftime("%I:%M %p"),
                                    "off": entry["off"].time().strftime("%I:%M %p")}
        if systemStatus["systemOn"] == False:
            entry = self.nextScheduledRuntime()
            if entry:
                systemStatus = {"systemOn": False,
                                    "title": "NEXT SCHEDULE: {0}".format(entry["on"].date().strftime('%b %d,').upper()),
                                    "target_heat": entry["target_heat"], 
                                    "target_cool": entry["target_cool"],
                                    "on": entry["on"].time().strftime("%I:%M %p"),
                                    "off": entry["off"].time().strftime("%I:%M %p")}

        return "<div id=\"scheduleEntry\"><small>{0}</small> <b>{1}-{2}</b></div> \
                <div id=\"targetTemps\"><div id=\"target-heat\">{3}</div> \
                <div id=\"target-cool\">{4}</div></div>".format(systemStatus["title"],
                                                            systemStatus["on"].lstrip("0"),
                                                            systemStatus["off"].lstrip("0"),
                                                            systemStatus["target_heat"],
                                                            systemStatus["target_cool"],)
        
    def nextScheduledRuntime(self):
        # make sure calendar is up to date
        self.loadCalendar()
        now = datetime.now()
        # set closest time in the future, then find future date
        closestTime = timedelta(days = -1)
        nextScheduleEntry = None
        for day in self.timeline:
            for entry in day:
                testDate = entry["on"] - now
                if testDate.days > -1: # make sure testdate not in past
                    if testDate < closestTime or closestTime.days == -1:
                        closestTime = testDate
                        nextScheduleEntry = entry
        return nextScheduleEntry
                
                
        

class DatabaseEntry(object):
    def __init__(self, id, target_heat, target_cool, date, timeOn, timeOff):
        self.id = id
        self.target_heat = target_heat
        self.target_cool = target_cool
        self.dateString = date
        self.dateMask, self.weight = getStringDate(date)
        self.timeOn = getStringTime(timeOn)
        self.timeOff = getStringTime(timeOff)
        
        # MAKE SURE 'HOLD' OVERRIDES EVERYTHING ELSE
        if self.id == -1:
            self.weight = 1000
            
    def runOnThisDate(self, timelineDate):
        ''' returns True if day in dateMask,
            or if dates match.
            bitmask may contain multiple days '''
        if type(self.dateMask) is date:
            return self.dateMask == timelineDate
        if type(self.dateMask) is datetime:
            return self.dateMask.date() == timelineDate
        return (self.dateMask & (1L << timelineDate.weekday())) == (1L << timelineDate.weekday())
        