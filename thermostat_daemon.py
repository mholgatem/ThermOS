#! /usr/bin/python -u
from __future__ import print_function
from datetime import *
import os
import RPi.GPIO as GPIO
import scheduler
import signal
import smtplib
import sqlite3
import subprocess
import sys
import time

import forecastio
from getIndoorTemp import getIndoorTemp

__version__ = 2.26

# set working directory to where "thermos_daemon.py" is
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

class ThermOSDaemon(object):

    def signal_handler(self, sig, frame):
        pins = (self.config['heater_pin'], self.config['ac_pin'], self.config['fan_pin'])
        GPIO.output(pins, False)
        GPIO.cleanup(pins)
        self.sendErrorMail("Thermostat is stopping!")
        print('Kaaaaahhhnn!')
        sys.exit(0)
    
    def __init__(self):
        # Configure database
        sqlite3.register_adapter(bool, str)
        sqlite3.register_converter("BOOLEAN", lambda v: 'T' in v)
        
        # THERMOSTAT.DB
        # TABLES: status, schedule, settings
        self.thermConn = sqlite3.connect("logs/thermostat.db", 
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES,
                            check_same_thread=False) #use this to save datetime
        self.thermConn.row_factory = sqlite3.Row # returned rows can be called with case-insensitive column names
        self.thermCursor= self.thermConn.cursor()
        
        # LOGS.DB
        # TABLES: logging, hourlyWeather, dailyWeather
        self.logsConn = sqlite3.connect("logs/logs.db", 
                            detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES,
                            check_same_thread=False) #use this to save datetime
        self.logsConn.row_factory = sqlite3.Row # returned rows can be called with case-insensitive column names
        self.logsCursor= self.logsConn.cursor()
        
        self.config = self.thermCursor.execute('SELECT * FROM settings').fetchone()
        
        #set signal handlers
        for sig in [signal.SIGTERM, signal.SIGQUIT, signal.SIGINT]:
            signal.signal(sig, self.signal_handler)
        signal.signal(signal.SIGHUP, self.reload)
                
        # used for scheduling on/off times
        self.calendar = scheduler.Calendar()
        
        self.configureGPIO()
        self.lastLog = datetime.now()
        self.mailLog = {}
        self.lastWeatherUpdate = datetime.now() + timedelta(hours=-2)
        
        # if database is corrupt, let the user know
        if self.thermCursor.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            self.sendErrorMail("The thermostat database is corrupt!")
        if self.logsCursor.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            self.sendErrorMail("The logs database is corrupt!")
        
        self.getStatus()
            
        self.sendErrorMail("Thermostat is starting")

    def reload(self, sig, frame):
        ''' systemctl reload thermostat-daemon '''
        
        # save pins to check if gpio needs to be reconfigured
        oldPins = (self.config['heater_pin'], self.config['ac_pin'], self.config['fan_pin'])
        
        # reload databases
        self.config = self.thermCursor.execute('SELECT * FROM settings').fetchone()
        self.calendar.loadCalendar(forceReload = True)
        
        # compare new/old pins
        newPins = (self.config['heater_pin'], self.config['ac_pin'], self.config['fan_pin'])
        if newPins != oldPins:
            GPIO.output(pins, False)
            GPIO.cleanup(pins)
            self.configureGPIO()
        
        # if database is corrupt, let the user know
        if self.thermCursor.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            self.sendErrorMail("The thermostat database is corrupt!")
        if self.logsCursor.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            self.sendErrorMail("The logs database is corrupt!")
        
        self.getStatus()
        
    def configureGPIO(self):
        if 'BCM' in self.config['numbering_scheme']:
            GPIO.setmode(GPIO.BCM)
        else:
            GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        GPIO.setup(self.config['heater_pin'], GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.config['ac_pin'], GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.config['fan_pin'], GPIO.OUT, initial=GPIO.LOW)

    def getStatus(self):
        for x in range(30):
            self.status = self.thermCursor.execute('SELECT * FROM status').fetchone()
            if self.status:
                return
            sleep(3)
        self.sendErrorMail("Could not get Status from Thermostat Database", timedelta(days=1))
            
    def getHVACState(self):
        heatStatus = GPIO.input(self.config['heater_pin'])
        coolStatus = GPIO.input(self.config['ac_pin'])
        
        # Set and get Fan status based on status['fan_mode']
        if self.status['fan_mode'] == 'ON':
            GPIO.output(self.config['fan_pin'], True)
        if not heatStatus and not coolStatus and self.status['fan_mode'] != 'ON': # auto
            GPIO.output(self.config['fan_pin'], False)
        fanStatus = GPIO.input(self.config['fan_pin'])
        
        # heating
        if heatStatus == 1 and fanStatus == 1:
            return "HEAT"
        # cooling        
        elif coolStatus == 1 and fanStatus == 1:
            return "COOL"
        #idle or fan only
        elif heatStatus == 0 and coolStatus == 0:
            return "OFF"
        else:
            #broken
            error = "HEAT {0}, AC {1}, FAN {2}".format(
            "ON" if heatStatus else "OFF", 
            "ON" if coolStatus else "OFF", 
            "ON" if fanStatus else "OFF", 
            )
            self.sendErrorMail("Something is wrong with your thermostat! " + error)
            return "ERROR"

    def cool(self):
        GPIO.output(self.config['heater_pin'], False)
        GPIO.output(self.config['ac_pin'], True)
        GPIO.output(self.config['fan_pin'], True)
        self.recordDebugLog("STATE: Switching to cool")
        return "COOL"

    def heat(self):
        GPIO.output(self.config['heater_pin'], True)
        GPIO.output(self.config['ac_pin'], False)
        GPIO.output(self.config['fan_pin'], True)
        self.recordDebugLog("STATE: Switching to heat")
        return "HEAT"

    def fanOnly(self): 
        # to blow the rest of the heated / cooled air out of the system
        GPIO.output(self.config['heater_pin'], False)
        GPIO.output(self.config['ac_pin'], False)
        GPIO.output(self.config['fan_pin'], True)
        self.recordDebugLog("STATE: Switching to fan only")

    def idle(self):
        GPIO.output(self.config['heater_pin'], False)
        GPIO.output(self.config['ac_pin'], False)
        if self.status['fan_mode'] != 'ON':
            GPIO.output(self.config['fan_pin'], False)
        self.recordDebugLog("STATE: Switching to idle")
        # delay to preserve compressor
        time.sleep(360)
        return "OFF"
    
    def powerDown(self):
        if GPIO.input(self.config['fan_pin']):
            self.fanOnly()
            time.sleep(30)
        return self.idle()

    
    def recordDebugLog(self, msg):
        if self.config['debug'] == True:
            print('DEBUG:', msg) 
    
    def checkSystemErrors(self):
        ''' check if we need to send
            mail about any errors '''
        pass
        #TODO:
            # Build heating and cooling profile from logs
            # to measure if unit is working properly
                    
    def logData(self):
        try:
            now = datetime.now()
            heatStatus = GPIO.input(self.config['heater_pin'])
            coolStatus = GPIO.input(self.config['ac_pin'])
            fanStatus = GPIO.input(self.config['fan_pin'])
            if self.config['debug'] == True:
                    msg = ("hvacState = {0} \n".format(self.getHVACState()) + 
                            "indoorTemp = {0} \n".format(self.indoorTemp) +
                            "targetTemp = {0} \n".format(self.activeTarget) +
                            "heatStatus = {0} \n".format(heatStatus) +
                            "coolStatus = {0} \n".format(coolStatus) +
                            "fanStatus = {0}".format(fanStatus))
                    self.recordDebugLog(msg)
                    
            self.logElapsed = now - self.lastLog
            #logging actual temp and indoor temp to sqlite database.
            #you can do fun things with this data, like make charts! 
            if self.logElapsed > timedelta(minutes=6):
                # keep logging data for a month
                self.logsCursor.execute("DELETE FROM logging where datetime NOT IN (SELECT datetime from logging ORDER BY datetime DESC LIMIT 7500)")
                self.logsCursor.execute('INSERT INTO logging VALUES(?, ?, ?, ?, ?)', (now,
                                                                            self.indoorTemp,
                                                                            self.activeTarget,
                                                                            self.getHVACState(), 
                                                                            "ON" if fanStatus else "OFF"))
                self.logsConn.commit()
                self.lastLog = datetime.now()
                self.indoorTemp = getIndoorTemp(self.config['units'], self.config['temperature_offset'])
                if self.indoorTemp == 0: #exactly 0 means error
                    self.sendErrorMail("There is a problem reading the temperature sensor!", frequency = timedelta(hours=6))
        except:
            print("Error while saving log data: ", sys.exc_info()[0])
                    
    def sendErrorMail(self, msg = "Thermostat Error", timeout = 10, frequency = timedelta(minutes=30)):
        if self.config['mail_enabled']:
            try:
                msg = str(msg)
                # don't spam user if error occurs
                if not msg in self.mailLog or datetime.now() > (self.mailLog[msg] + frequency):
                    self.mailLog[msg] = datetime.now()
                    headers = ["From: " + self.config['sender'],
                           "To: " + self.config['recipient'],
                           "MIME-Version: 1.0",
                           "Content-Type: text/html"]
                    headers = "\r\n".join(headers)
                    session = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'], timeout = timeout)
                    session.ehlo()
                    # you may need to comment this line out if you're a crazy person
                    # and use non-tls SMTP servers
                    session.starttls()
                    session.ehlo
                    session.login(self.config['username'], self.config['password'])
                    session.sendmail(self.config['sender'], self.config['recipient'], 
                                                                        headers + "\r\n\r\n" + msg)
                    session.quit()
            except smtplib.socket.timeout:
                self.recordDebugLog("sendErrorMail() timed out!")
            except:
                self.recordDebugLog("sendErrorMail() had an error:\n{0}".format(sys.exc_info()[0]))
    
    def updateWeather(self):
        ''' icon:
                clear-day, clear-night, rain, snow, sleet, wind, fog,
                cloudy, partly-cloudy-day, or partly-cloudy-night
            *precipProbability:
                0 to 1
            **precipType:
                rain, snow, sleet
            temperature:
                float
            apparentTemperature:
                feels like (float)
            *windSpeed:
                float
            **windBearing:
                0 = True North -> clockwise
            cloudCover:
                0 to 1
            humidity:
                0 to 1

            Table: hourlyWeather
                Columns:
                    date
                    icon
                    temperature
                    apparentTemperature
                    windSpeed
                    windBearing
                    cloudCover
                    humidity
                    precipProbability
                    precipType
            
            Table: dailyWeather
                Columns:
                    date
                    tempMin
                    tempMinTime
                    tempMax
                    tempMaxTime
                    moonPhase
            '''
        if self.config['weather_enabled']:
            try:
                if (datetime.now() - self.lastWeatherUpdate).seconds > 3600:
                    self.lastWeatherUpdate = datetime.now()
                    
                    #timezone offset for weather forecast
                    utcDelta = (datetime.now() - datetime.utcnow())
                    utcDelta = timedelta(utcDelta.days, utcDelta.seconds+int(utcDelta.microseconds / 500000), 0)
                    
                    forecast = forecastio.load_forecast(self.config['api_key'], 
                                                        self.config['latitude'], 
                                                        self.config['longitude'], 
                                                        units = "us" if self.config['units'] == 'F' else "si")
                                                                                                    
                    hourly = forecast.hourly()
                    hours = []
                    for data in hourly.data:
                        t = data.time + utcDelta
                        precipType = data.precipType if data.precipProbability else "N/A"
                        windBearing = data.windBearing if data.windSpeed else "N/A"
                        hours.append((t, data.icon, 
                                        data.temperature, 
                                        data.apparentTemperature, 
                                        data.windSpeed, 
                                        windBearing, 
                                        data.cloudCover, 
                                        data.humidity, 
                                        data.precipProbability, 
                                        precipType))
                    
                    # keep weather data for a month
                    self.logsCursor.execute("DELETE FROM hourlyWeather where date NOT IN (SELECT date from hourlyWeather ORDER BY date DESC LIMIT 750)")
                    self.logsCursor.executemany("INSERT OR REPLACE INTO hourlyWeather VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", hours)
                    self.logsConn.commit()
                    
                    daily = forecast.daily()
                    days = []
                    for data in daily.data:
                        alerts = ""
                        for alert in forecast.alerts():
                            if data.time.date() <= datetime.fromtimestamp(alert.expires).date():
                                alerts += "<span class=\"alertTitle\">{0}</span> \
                                            <p class=\"alertBody\">{1}</p>".format(alert.title, alert.description)
                        alerts = "<div id=\"weatherAlerts\">" + alerts + "</div>" if alerts else None
                        
                        for entry in ['sunriseTime','sunsetTime','temperatureMinTime','temperatureMaxTime']:
                            data.d[entry] = data.d.get(entry, None)
                            if data.d[entry]:
                                data.d[entry] = datetime.fromtimestamp(data.d[entry])

                        days.append((   data.time.date(),
                                        data.d.get('icon', None),
                                        data.d.get('summary', None),
                                        data.d.get('temperatureMin', None),
                                        data.d['temperatureMinTime'],
                                        data.d.get('temperatureMax', None),
                                        data.d['temperatureMaxTime'],
                                        data.d['sunriseTime'],
                                        data.d['sunsetTime'],
                                        data.d.get('moonPhase', None),
                                        data.d.get('precipProbability', None),
                                        data.d.get('windSpeed', None),
                                        data.d.get('windBearing', None),
                                        data.d.get('humidity', None),
                                        data.d.get('ozone', None),
                                        data.d.get('pressure', None),
                                        data.d.get('cloudCover', None),
                                        data.d.get('visibility', None),
                                        alerts
                                    ))

                    self.logsCursor.execute("DELETE FROM hourlyWeather where date NOT IN (SELECT date from hourlyWeather ORDER BY date DESC LIMIT 400)")
                    self.logsCursor.executemany("INSERT OR REPLACE INTO dailyWeather VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", days)
                    self.logsConn.commit()
            except:
                print("Error while getting weather info:", sys.exc_info()[0])
        
    def getMode(self):
        ''' returns what mode the system should
            be in based on settings and schedule '''
        # error checking
        if not self.status:
            return 'OFF'
        else:
            if self.status['mode'] == 'AUTO':
                if self.schedule['systemOn']:
                    # AUTO COOL
                    if type(self.schedule['target_cool']) in [int, float] :
                        if self.indoorTemp >= self.schedule['target_cool'] - self.config['active_hysteresis']:
                            self.activeTarget = self.schedule['target_cool'] - self.config['active_hysteresis']
                            self.inactiveTarget = self.schedule['target_cool'] + self.config['inactive_hysteresis']
                            return "COOL"
                    # AUTO HEAT
                    if type(self.schedule['target_heat']) in [int, float]:
                        if self.indoorTemp <= self.schedule['target_heat'] + self.config['active_hysteresis']:
                            self.activeTarget = self.schedule['target_heat'] + self.config['active_hysteresis']
                            self.inactiveTarget = self.schedule['target_heat'] - self.config['inactive_hysteresis']
                            return "HEAT"
                # AUTO OFF
                elif not self.schedule['systemOn']:
                    return "OFF"
            else:
                # MANUAL COOL
                if self.status['mode'] == 'COOL':
                    if self.indoorTemp >= self.status['target_cool'] - self.config['active_hysteresis']:
                        self.activeTarget = self.status['target_cool'] - self.config['active_hysteresis']
                        self.inactiveTarget = self.status['target_cool'] + self.config['inactive_hysteresis']
                        return "COOL"
                # MANUAL HEAT
                if self.status['mode'] == 'HEAT':
                    if self.indoorTemp <= self.status['target_heat'] + self.config['active_hysteresis']:
                        self.activeTarget = self.status['target_heat'] + self.config['active_hysteresis']
                        self.inactiveTarget = self.status['target_heat'] - self.config['inactive_hysteresis']
                        return "HEAT"
                if self.status['mode'] == 'OFF':
                    return "OFF"
                
        return "OFF"
        
        
    def run(self):
        
        errorCount = 0
        self.inPassiveMode = False
        self.thermostatMode = "OFF"
        self.activeTarget = 0
        self.inactiveTarget = 0
        while True:
            
            self.indoorTemp = getIndoorTemp(self.config['units'], self.config['temperature_offset'])
            self.schedule = self.calendar.getStatus()
            self.thermostatMode = self.getMode()
            hvacState = self.getHVACState()

            if not self.inPassiveMode:
                if self.thermostatMode == "COOL": self.cool()
                if self.thermostatMode == "HEAT": self.Heat()

                if (self.thermostatMode == "OFF" or
                    self.thermostatMode == "COOL" and self.indoorTemp <= self.activeTarget or
                    self.thermostatMode == "HEAT" and self.indoorTemp >= self.activeTarget):
                    self.inPassiveMode = True
                    self.powerDown()
            else:
                if (self.thermostatMode == "COOL" and self.indoorTemp > self.inactiveTarget or
                    self.thermostatMode == "HEAT" and self.indoorTemp < self.inactiveTarget):
                    self.inPassiveMode = False

            self.logData()
            self.checkSystemErrors()
            self.updateWeather()  
            time.sleep(5)


if __name__ == "__main__":
    print("Thermostat Daemon v.", __version__)
    daemon = ThermOSDaemon()
    daemon.run()
