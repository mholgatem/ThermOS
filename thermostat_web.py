#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import subprocess
import sqlite3
from datetime import datetime, timedelta
from flask import *
import pygal
import RPi.GPIO as GPIO

import scheduler
import tempSensor

'''  INITIALIZE THERMOSTAT-WEB  '''
''''''''''''''''''''''''''''''''''''
app = Flask(__name__)
app.secret_key = 'DErGH65&*jKl990L.:s;6md8hgr53SD'

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

# register custom types
sqlite3.register_adapter(bool, str)
sqlite3.register_converter("BOOLEAN", lambda v: 'T' in v)

# TABLES: status, schedule, settings
thermConn = sqlite3.connect("logs/thermostat.db", 
					   detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES, #use this to save datetime
					   check_same_thread=False)
# returned rows can be called with case-insensitive column names
thermConn.row_factory = sqlite3.Row
thermCursor = thermConn.cursor()

# get CONFIG settings
CONFIG = thermCursor.execute('SELECT * FROM settings').fetchone()

# TABLES: logging, hourlyWeather, dailyWeather
logsConn = sqlite3.connect("logs/logs.db", 
					detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES, #use this to save datetime
				   check_same_thread=False) 
# returned rows can be called with case-insensitive column names
logsConn.row_factory = sqlite3.Row 
logsCursor = logsConn.cursor()

#load any scheduled items
calendar = scheduler.Calendar()


try:
	GPIO.setwarnings(False)
	if 'BCM' in CONFIG['numbering_scheme']:
		GPIO.setmode(GPIO.BCM)
	else:
		GPIO.setmode(GPIO.BOARD)
	GPIO.setup([CONFIG['heater_pin'], CONFIG['ac_pin'], CONFIG['fan_pin']], GPIO.OUT)
	settingsRedirect = False
except (ValueError, TypeError):
	settingsRedirect = True


''' WORKER FUNCTIONS '''
''''''''''''''''''''''''
def getWeatherGraph():
	''' used by /forecast to build 72 hour by hour weather graph '''
	#get latest 24 hours, hourly[0] = current hour
	startTime = str(datetime.now() - timedelta(hours=1))[:19]
	hourly = logsCursor.execute('select * from hourlyWeather \
								 where datetime(date) >= datetime("{0}")'.format(startTime)).fetchall()

	times = []
	temps = []
	uvIndex = []
	majorX = ["Now"]
	for hourlyData in hourly:
		if hourlyData == hourly[0]:
			time = "Now"
		else:
			time = str(hourlyData['date'].hour % 12)
			time = "12" if time == "0" else time
			time += "am" if hourlyData['date'].hour < 12 else "pm"
			if time == "12am":
				time = hourlyData['date'].strftime('%a')
				majorX.append(time)
		times.append(time)
		temps.append(hourlyData['temperature'])
		uvIndex.append(hourlyData['uvIndex'] if not None else 0)

	pygal.style.DarkSolarizedStyle.label_font_family = 'agencyfb'
	pygal.style.DarkSolarizedStyle.label_font_family = 'agencyfb'
	pygal.style.DarkSolarizedStyle.label_font_size = 35

	pygal.style.DarkSolarizedStyle.value_font_family = 'agencyfb'
	pygal.style.DarkSolarizedStyle.value_font_size = 25
	pygal.style.DarkSolarizedStyle.value_colors = ('white','white', 'white')
	
	pygal.style.DarkSolarizedStyle.major_label_font_family = 'agencyfb'
	pygal.style.DarkSolarizedStyle.major_label_font_size = 35
	
	pygal.style.DarkSolarizedStyle.tooltip_font_family = 'agencyfb'
	pygal.style.DarkSolarizedStyle.tooltip_font_size = 25
	
	pygal.style.DarkSolarizedStyle.colors = ('rgba(246,190,28,.7)', 'rgba(117, 0, 255, 0.45)', '#E95355', '#E87653', '#E89B53')
	pygal.style.DarkSolarizedStyle.background = 'rgba(31, 53, 70, 0.01)'
	pygal.style.DarkSolarizedStyle.plot_background = 'none'
	
	
	noDataText = "Data Not Available" if CONFIG['weather_enabled'] else "API Not Enabled"
	#clear-day, clear-night, rain, snow, sleet, wind, fog, cloudy, partly-cloudy-day, or partly-cloudy-night
	line_graph = pygal.Line( width = 5000, 
							height = 250,
							margin = 10,
							margin_left = -50,
							dots_size = 15,
							explicit_size = True, 
							#title = "Currently {0}&deg;{1}".format(hourly[0]['temperature'], CONFIG['units']), 
							interpolate = "cubic",
							fill = True,
							show_legend = True,
							#legend_box_size=25,
							print_values=True,
							#print_values_position='top',
							show_x_guides=True,
							show_y_labels=False,
							no_data_text=noDataText,
							style = pygal.style.DarkSolarizedStyle)
	line_graph.x_labels = times
	line_graph.x_labels_major = majorX
	line_graph.value_formatter = lambda x: "%.1f" % x
	line_graph.add("Temps", temps)
	line_graph.add("UV", uvIndex, fill=False, dots_size=4, formatter=lambda x: '%s' % x)


	return line_graph.render().decode("utf-8").replace("&amp;","&")
	
def getCurrentWeather():
	''' parses and returns current weather information '''
	if CONFIG['weather_enabled']:
		#get latest 24 hours, hourly[0] = current hour
		startTime = str(datetime.now() - timedelta(hours=1))[:19]
		hourly = logsCursor.execute('select * from hourlyWeather \
									 where datetime(date) >= datetime("{0}")'.format(startTime)).fetchone()
		
		if hourly:
			currentTemp = '<span class="unit-{1}" id="outdoorTempSpan">{0:.0f}</span>'.format( hourly['temperature'], 
																								   CONFIG['units'] )
																								   
			#clear-day, clear-night, rain, snow, sleet, wind, fog, cloudy, partly-cloudy-day, or partly-cloudy-night
			currentIcon = '<img id="currentWeatherIcon" src="static/images/weather/icons/128/{0}.png">'.format(hourly['icon'])
			currentHumidity = '<p id="outdoorHumidity"> \
									<span id="humidity">{0:.0f}%</span> \
									<span id="humidityLabel">Humidity</span> \
								</p>'.format(hourly['humidity'] * 100)
			
			html = '{0}{1}{2}'.format(currentTemp, currentIcon, currentHumidity)
			return html.decode("utf-8").replace("&amp;","&")
			
		return '<span style="font-size:60px;">Weather not yet populated</span>'

		
def getDailyWeather():
	''' parses and returns daily weather information '''
	if CONFIG['weather_enabled']:
		logsCursor.execute("SELECT * FROM (SELECT * FROM dailyWeather ORDER BY date DESC LIMIT 8) ORDER BY date ASC")
		daily = [dict(row) for row in logsCursor]
		for day in daily:
			
			if day['date'] == daily[0]['date']:
				day['weekday'] = 'TODAY'
			else:
				day['weekday'] = day['date'].strftime("%a").upper()
			day['date'] = day['date'].strftime("%b %d")
			day['tempMinTime'] = day['tempMinTime'].strftime("%I:%M %p").lstrip("0")
			day['tempMaxTime'] = day['tempMaxTime'].strftime("%I:%M %p").lstrip("0")
			day['sunriseTime'] = day['sunriseTime'].strftime("%I:%M %p").lstrip("0")
			day['sunsetTime'] = day['sunsetTime'].strftime("%I:%M %p").lstrip("0")
			day['visibility'] = "{0} mi.".format(day['visibility']) if day['visibility'] != None else 'N/A'
			day['cloudCover'] = "{:.0%}".format(day['cloudCover']) if day['cloudCover'] != None else 'N/A'
			day['humidity'] = "{:.0%}".format(day['humidity']) if day['humidity'] != None else 'N/A'
			day['precipProbability'] = "{:.0%}".format(day['precipProbability']) if day['precipProbability'] != None else 'N/A'
			if day['moonPhase']:
				if day['moonPhase'] <= 0.5:
					day['moonPhase'] = "{:.0%}".format(day['moonPhase'] * 2.0)
				else:
					day['moonPhase'] = "{:.0%}".format((day['moonPhase'] * 2.0) - 2)
			else:
				day['moonPhase'] = '0%'
			day['pressure'] = "{0} mb.".format(day['pressure']) if day['pressure'] else 'N/A'
			if day['windBearing']:
				if day['windBearing'] > 337:
					day['windBearing'] = 'N'
				elif day['windBearing'] > 292:
					day['windBearing'] = 'NW'
				elif day['windBearing'] > 247:
					day['windBearing'] = 'W'	
				elif day['windBearing'] > 202:
					day['windBearing'] = 'SW'
				elif day['windBearing'] > 157:
					day['windBearing'] = 'S'
				elif day['windBearing'] > 112:
					day['windBearing'] = 'SE'
				elif day['windBearing'] > 67:
					day['windBearing'] = 'E'
				elif day['windBearing'] > 22:
					day['windBearing'] = 'NE'
				elif day['windBearing'] >= 0:
					day['windBearing'] = 'N'
			else:
				day['windBearing'] = ''
				
		return daily
	return []

def getCurrentWeatherAlerts():
	''' returns any relevant daily weather alerts '''
	if CONFIG['weather_enabled']:
		#get latest week, daily[0] = current day
		daily = logsCursor.execute('SELECT * FROM dailyWeather WHERE date(date) = date("{0}")'.format(datetime.now().date()) ).fetchone()
		html = '<div id="weatherAlertContainer">{0}</div>'.format(daily['alert'] if daily and daily['alert'] else "")
		return html.decode("utf-8").replace("&amp;","&")
	return '<div id="weatherAlertContainer"></div>'

def getWhatsOn():
	''' get the current state of the gpio pins '''
	pins = {'heat': CONFIG['heater_pin'], 'cool': CONFIG['ac_pin'], 'fan': CONFIG['fan_pin']}
	html = ''
	for key,value in pins.iteritems():
		try:
			temp = "ON" if type(value) == int and GPIO.input(value) else "OFF"
		except:
			temp = "Misconfigured"
		html += '<p id="{0}">{1} (GPIO {2}): {3} </p>'.format(key, key.upper(), value, temp)
	return html

def getDaemonStatus():
	''' get the current status of thermostat-daemon. 
		Only used by /info for troubleshooting '''
	try:
		if 'active' in subprocess.check_output(['systemctl', 'is-active', 'thermostat-daemon']):
			return '<p id="daemonRunning"> Daemon is running. </p>'
		else:
			return '<p id="daemonNotRunning"> DAEMON IS NOT RUNNING. </p>'
	except:
		return '<p id="daemonNotRunning"> DAEMON IS NOT RUNNING. </p>'


def getValueByType(xName, xValue):
	''' used by settings_submit to validate
		entries based on type '''
	try:
		if 'int' in xName[:3]:
			return int(xValue) if xValue else 0
		if 'float' in xName[:5]:
			return float(xValue) if xValue else 0
		if ('option' in xName[:6] 
			or 'text' in xName[:4]):
			return xValue
	except:
		return None

def getModeHTML(status):
    ''' used by /info and /_liveUpdate to display
        relevant heating/cooling targets + schedule info '''
    mode = calendar.getStatusHTML()
    if status['mode'] == 'AUTO' or 'HOLD' in mode:
        return mode
    elif status['mode'] == 'COOL':
        mode = ['<div id="targetTemps"><div id="target-cool">{0}</div></div>'.format(status['target_cool'])]
    elif status['mode'] == 'HEAT':
        mode = ['<div id="targetTemps"><div id="target-heat">{0}</div></div>'.format(status['target_heat'])]
    else:
        mode = ['']
    return ['<div id="scheduleEntry"></div>'] + mode
	
def reloadDaemon():
	''' reload thermostat-daemon '''
	global CONFIG, calendar
	try:
		if 'active' in subprocess.check_output(['systemctl', 'is-active', 'thermostat-daemon']):
			subprocess.call(("systemctl", "reload", "thermostat-daemon"))
	except:
		subprocess.call(("systemctl", "start", "thermostat-daemon"))
	CONFIG = thermCursor.execute('SELECT * FROM settings').fetchone()
	calendar.loadCalendar(forceReload = True)


''' FLASK APP ROUTES '''
''''''''''''''''''''''''

'''   INDEX	'''
''''''''''''''''''
@app.route('/')
def main_form():
	CONFIG = thermCursor.execute('SELECT * FROM settings').fetchone()
	settingsRedirect = not (CONFIG['heater_pin'] or CONFIG['ac_pin'] or CONFIG['fan_pin'])
	# redirect if none of the pins are set
	if settingsRedirect:
		flash("You must setup your system before you can continue","warning")
		flash("HINT: Hover over an item to see a description","info")
		return redirect(url_for('settings_form'))
		#return render_template("index.html", openSettings = '$( "#settings-btn" ).click();')
	else:
		status = thermCursor.execute('SELECT * FROM status').fetchone()
		schedule = getModeHTML(status)
		temp = str(round(tempSensor.getCurrent(CONFIG['units'], CONFIG['temperature_offset']),1))
		if temp == "-666.0":
			temp = "Err"
		return render_template("index.html",unit = CONFIG['units'],
											fanStatus = status['fan_mode'],
											systemMode = status['mode'],
											targetTemps = Markup(schedule[1]),
											weatherVisible = 'visible' if CONFIG['weather_enabled'] else 'hidden',
											holdTime = calendar.getRemainingHoldTime(),
											temp = temp,
											title = Markup(temp + "&deg;"),
											scheduleTime = Markup(schedule[0]),
											currentWeather = Markup(getCurrentWeather()),
											time = Markup(datetime.now().strftime('<b>%I:%M</b><small>%p %A, %B %d</small>')),
											alerts = getCurrentWeatherAlerts())

										
'''  SCHEDULE  '''
''''''''''''''''''
@app.route('/schedule')
def schedule_form():
	options = thermCursor.execute('SELECT * FROM schedule where not id = -1').fetchall() 
	return render_template("schedule_form.html", options=options)

@app.route('/schedule/delete', methods=['POST'])
def schedule_delete():
	if 'id' in request.form:
		thermCursor.execute('DELETE FROM schedule WHERE id = (?)',(request.form['id'],))
		thermConn.commit()
		reloadDaemon()
	return redirect(url_for('schedule_form'))

@app.route('/schedule/edit', methods=['GET'])
def schedule_edit():
	id = request.args.get('id', '')
	if id and id != 'new':
		entry = thermCursor.execute('SELECT * FROM schedule WHERE id = {0}'.format(id)).fetchone()
	else:
		entry = {  'id': 'new',
				'date':'', 
				'target_cool':'74',
				'target_heat':'68',
				'time_on':'12:00 AM',
				'time_off':'12:00 AM'
				}
	return render_template("schedule_edit_form.html", entry=entry)

@app.route('/schedule/edit', methods=['POST'])
def schedule_submit():
	entry = {
				'id': request.form.get('id', ''),
				'date': request.form.get('date', ''),
				'target_cool': request.form.get('target_cool', ''),
				'target_heat': request.form.get('target_heat', ''),
				'time_on': request.form.get('time_on', ''),
				'time_off': request.form.get('time_off', '')
			}
	
	date_check = [  'MONDAYS', 
					'TUESDAYS', 
					'WEDNESDAYS', 
					'THURSDAYS', 
					'FRIDAYS', 
					'SATURDAYS', 
					'SUNDAYS', 
					'WEEKDAYS', 
					'WEEKENDS', 
					'ALWAYS' ]
	
	# Basic Error/Format Checking
	found_errors = False
	if not entry['date'] in date_check and len(entry['date'].split('/')) != 3:
		flash("Date does not conform to standards","danger")
		found_errors = True
		
	try:
		if entry['target_heat']:
			entry['target_heat'] = int(entry['target_heat'])
		if entry['target_cool']:
			entry['target_cool'] = int(entry['target_cool'])
	except:
		flash("Target temperatures must be a valid number", "danger")
		found_errors = True
		
	if not len(entry['time_on'].split(':')) == 2:
		flash("'Time on' is not in a recognized format", "danger")
		found_errors = True
		
	if not len(entry['time_off'].split(':')) == 2:
		flash("'Time off' is not in a recognized format", "danger")
		found_errors = True
		
	if found_errors:
		return render_template("schedule_edit_form.html", entry=entry)
	
	# Update and redirect
	if entry['id'] == 'new' or entry['id'] == '':
		thermCursor.execute('INSERT INTO schedule \
							(id, target_heat, target_cool, date, time_on, time_off) VALUES (?,?,?,?,?,?)', 
							(None, entry['target_heat'], entry['target_cool'], entry['date'], entry['time_on'], entry['time_off']))
		thermConn.commit()
		reloadDaemon()
		flash("New Entry Added!","success")
		return redirect(url_for('schedule_form'))
	else:
		thermCursor.execute('INSERT OR REPLACE INTO schedule \
							(id, target_heat, target_cool, date, time_on, time_off) VALUES (?,?,?,?,?,?)', 
							(entry['id'], entry['target_heat'], entry['target_cool'], entry['date'], entry['time_on'], entry['time_off']))
		thermConn.commit()
		reloadDaemon()
		flash("Entry #{0} has been updated!".format(entry['id']),"info")
		return redirect(url_for('schedule_form'))
 

	return render_template("schedule_edit_form.html", entry=entry)

	
'''  HOLD  '''
''''''''''''''''''
@app.route("/hold", methods=['POST'])
def hold_submit():

	text = request.form['target']
	mode = "cool" if 'onoffswitch' in request.form else "heat"
	try:
		newTargetTemp = float(request.form['target'])
	except:
		newTargetTemp = None

	if newTargetTemp != None:
		if mode == "heat":
			targetHeat = float(newTargetTemp)
			targetCool = 'HOLD'
		else:
			targetHeat = 'HOLD'
			targetCool = float(newTargetTemp)
		
		if request.form['timeFrame'] == "OFF":
			thermCursor.execute('DELETE FROM schedule WHERE id= -1')
			thermConn.commit()
			flash("Temperature hold has been disabled!")
		else:
			now = datetime.now()
			if request.form['timeFrame'] != 'FOREVER':
				time_frame = float(request.form['timeFrame'])
				date = now.date().strftime("%Y/%m/%d")
			else:
				time_frame = 0
				date = 'ALWAYS'
			time_on = (now.time()).strftime("%I:%M %p")
			time_off = (now + timedelta(hours=time_frame)).time().strftime("%I:%M %p")
			thermCursor.execute('INSERT OR REPLACE INTO schedule values (?, ?, ?, ?, ?, ?)', 
														(-1, targetHeat, targetCool, date, time_on, time_off))
			thermConn.commit()
			flash("Thermostat will {mode} to {temp} until {time}".format(mode=mode, 
																	   temp=newTargetTemp, 
																	   time = time_off if time_frame else 'forever',
																	   hours = 'hours' if time_frame else ''), 
																	   'info')
																	   
		# tell thermostat-daemon to reload config
		reloadDaemon()
		return redirect(url_for('hold_form'))
	else:
		flash("Must be a valid number", 'danger')
		return redirect(url_for('hold_form'))


@app.route('/hold')
def hold_form():
	targetCool, targetHeat, mode, fanMode = thermCursor.execute('SELECT * FROM status').fetchone()

	if mode == "heat":
		checked = ""
	else:
		checked = 'checked'
	return render_template("hold_form.html", targetTemp = (targetCool + targetHeat) / 2,
											 checked = checked)


'''  SYSTEM  '''
''''''''''''''''''
@app.route('/system')
def system_form():
	status = thermCursor.execute('SELECT * FROM status').fetchone()
	
	if status['mode'] == "heat":
		targetTemp = status['target_heat']
	elif status['mode'] == "cool":
		targetTemp = status['target_cool']
	else:
		(status['target_cool'] + status['target_heat']) / 2


	return render_template("system_form.html", offSelect = 'selected' if status['mode'] == 'OFF' else '',
											   coolSelect = 'selected' if status['mode'] == 'COOL' else '',
											   coolTemp = status['target_cool'],
											   heatSelect = 'selected' if status['mode'] == 'HEAT' else '',
											   heatTemp = status['target_heat'],
											   autoSelect = 'selected' if status['mode'] == 'AUTO' else '',
											   targetTemp = (status['target_cool'] + status['target_heat']) / 2)
											   
@app.route('/system', methods=['POST'])
def system_submit():
	
	status = thermCursor.execute('SELECT * FROM status').fetchone()
	mode = request.form['mode']
	try:
		newTargetTemp = float(request.form['target'])
	except:
		newTargetTemp = None
		flash("Must be a valid number!", 'danger')
	else:
		if mode == 'COOL':
			targetCool = newTargetTemp
			targetHeat = status['target_heat']
			msg = "Cooling to {0}&deg;{1}".format(targetCool, CONFIG['units'])
		elif mode == 'HEAT':
			targetCool = status['target_cool']
			targetHeat = newTargetTemp
			msg = "Heating to {0}&deg;{1}".format(targetHeat, CONFIG['units'])
		else:
			targetCool = status['target_cool']
			targetHeat = status['target_heat']
			if mode == 'OFF':
				msg = "Turning off system"
			else:
				msg = "Now using the schedule"
		
		thermCursor.execute('DELETE FROM status')
		thermCursor.execute('INSERT INTO status VALUES (?, ?, ?, ?)', (targetCool, targetHeat, mode, status['fan_mode']))
		thermConn.commit()
		
		reloadDaemon()
		flash(msg, 'info')


	return redirect(url_for('system_form'))
										
													
'''  SETTINGS  '''
''''''''''''''''''
@app.route("/settings", methods=['POST'])
def settings_submit():
	
	errorList = []
	formItems = {}
	
	debugEnabled = True if 'bool-debug' in request.form else False
	weatherEnabled = True if 'bool-weather' in request.form else False
	mailEnabled = True if 'bool-mail' in request.form else False
	
	thermElements = (   'option-temperature-units',
						'float-active-hysteresis',
						'float-inactive-hysteresis',
						'option-numbering-scheme',
						'int-ac-pin',
						'int-heat-pin',
						'int-fan-pin',
						'float-temperature-offset')
						
	weatherElements = ( 'text-api-key',
						'float-latitude',
						'float-longitude')
						
	mailElements = (	'float-error-threshold',
						'text-smtp-server',
						'int-smtp-port',
                        'text-imap-server',
                        'int-imap-port',
						'text-username',
						'text-password',
						'text-sender',
						'text-recipient',
                        'text-access-code')
		
						
	for key, value in request.form.iteritems():
		temp = ''
		temp = getValueByType(key, value)
		if temp != None: # if valid entry
			formItems[key] = temp
		else:
			# generate error message
			formItems[key] = ''
			if ((key in thermElements) or
				(weatherEnabled and key in weatherElements) or
				(mailEnabled and key in mailElements)):
					temp = key.split('-')
					tempType = "Numbers" if temp[0] in ["int", "float"] else "Letters"
					errorList.append ("{0} must contain only {1}".format(' '.join(temp[1:]), tempType))

	
	for e in errorList:
		flash(e, "danger")

	if not errorList:

		values = (  debugEnabled,
					formItems['option-temperature-units'],
					formItems['float-active-hysteresis'],
					formItems['float-inactive-hysteresis'],
					formItems['option-numbering-scheme'],
					formItems['int-ac-pin'],
					formItems['int-heat-pin'],
					formItems['int-fan-pin'],
					formItems['float-temperature-offset'],
					weatherEnabled,
					formItems['text-api-key'],
					formItems['float-latitude'],
					formItems['float-longitude'],
					mailEnabled,
					formItems['float-error-threshold'],
					formItems['text-smtp-server'],
					formItems['int-smtp-port'],
					formItems['text-username'],
					formItems['text-password'],
					formItems['text-sender'],
					formItems['text-recipient'],
                    formItems['text-imap-server'],
                    formItems['int-imap-port'],
                    formItems['text-access-code']
					)
		
		# save settings to thermostat.db
		thermCursor.execute('DELETE FROM settings')
		thermCursor.execute('INSERT INTO settings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', values)
		thermConn.commit()	
		
		# get globals (for setting later)
		global CONFIG, settingsRedirect
		
		# get current (old) pins
		oldPins = (CONFIG['heater_pin'], CONFIG['ac_pin'], CONFIG['fan_pin'])
		oldNumbering = CONFIG['numbering_scheme']
		
		# reload databases
		CONFIG = thermCursor.execute('SELECT * FROM settings').fetchone()
		
		# get submitted (new) pins
		newPins = (CONFIG['heater_pin'], CONFIG['ac_pin'], CONFIG['fan_pin'])
		newNumbering = CONFIG['numbering_scheme']
		
		# compare new/old pins
		if newPins != oldPins or newNumbering != oldNumbering :
		
			#stop daemon
			subprocess.call(("systemctl", "stop", "thermostat-daemon"))
			
			#cleanup pins
			try:
				oldPins = [ x for x in oldPins if type(x) == int and x > 0 ]
				GPIO.output(oldPins, False)
				GPIO.cleanup(oldPins)
			except:
				GPIO.cleanup(oldPins)
			
			# reconfigure gpio with new pins
			GPIO.setwarnings(False)
			if 'BCM' in CONFIG['numbering_scheme']:
				GPIO.setmode(GPIO.BCM)
			else:
				GPIO.setmode(GPIO.BOARD)
			try:
				GPIO.setup([CONFIG['heater_pin'], CONFIG['ac_pin'], CONFIG['fan_pin']], GPIO.OUT)
				
				# restart daemon
				subprocess.call(("systemctl", "start", "thermostat-daemon"))
				
				# if user was redirected here, send them to the main page
				if settingsRedirect:
					settingsRedirect = False
					return redirect(url_for('main_form'))
				else:
					flash("Settings have been saved!", "success")

			except ValueError:
				flash("Error setting one of the GPIO pins", "danger")
		else: #pins have not changed
			# tell thermostat-daemon to reload config
			flash("Settings have been saved!", "success")
			reloadDaemon()
	
	# re-render settings form with current entries
	values = dict(zip(map(str.lower, thermCursor.execute('SELECT * FROM settings').fetchone().keys()), values))
	return render_template("settings_form.html", config = values)

@app.route('/settings')
def settings_form():
	global CONFIG
	CONFIG = thermCursor.execute('SELECT * FROM settings').fetchone()
	return render_template("settings_form.html", config = CONFIG)

							
'''  FORECAST  '''
''''''''''''''''''
@app.route('/forecast')
def forecast_form():
	alerts = getCurrentWeatherAlerts()
	hideAlerts = 'hidden' if alerts == '<div id="weatherAlertContainer"></div>' else ''
	forecast = getDailyWeather()
	hideForecast = 'hidden' if not forecast else ''
	
	return render_template("weather.html",  graph = getWeatherGraph(),
											hideForecast = hideForecast,
											forecast = forecast,
											hideAlerts = hideAlerts,
											alerts = alerts)		


'''  LOGS  '''
''''''''''''''''''											
@app.route('/_daemonLogs', methods= ['GET'])
def updateDaemonLogs():
	''' returns a table with the thermostat-daemon journal '''
	weekAgo = (datetime.now() + timedelta(days=-7)).date()
	raw = subprocess.check_output(['journalctl', '-u', 'thermostat-daemon', '--since={0}'.format(weekAgo)])
	head = ('<head>' + 
				'<link href="/static/css/bootstrap.css" rel="stylesheet">' +
				'<link href="/static/css/main.css" rel="stylesheet">' +
			'</head>' + 
			'<body style="padding: 20px 10px;"><div class="container">' +
			'<h1 class="blue-letterpress">Thermostat-Daemon Logs</h1><hr style="width:100%;">' +
			'<table class="table blue box-shadow table-striped table-bordered table-hover model-list">' +
				'<thead>' +
					'<tr>' +
						'<th>Date</th>' +
						'<th>Message</th>' +
					'</tr>' +
				'</thead>' +
				'<tbody>')
	html = ''
	rows = raw.split('\n')[1:]
	date = ''
	message = ''
	for row in rows:
		message += row[39:].lstrip(']:').replace('>','&gt;').replace('<', '&lt;') + '<br>'
		if date != row[:15]:
			date = row[:15]
			# do it this way to display in reverse order
			if date:
				html = '<tr><td>{date}</td><td><p>{message}</p></td></tr>'.format(date = date, message = message) + html
				message = ''
	html += '</tbody></table></div></body>'
	return head + html


'''  FAN TOGGLE  '''
''''''''''''''''''	
@app.route('/_fanMode', methods= ['POST'])
def toggleFan():
	''' used to change the state of the fan '''
	if 'toggle' in request.form:
		status = thermCursor.execute('SELECT * FROM status').fetchone()
		if status['fan_mode'] == 'AUTO':
			fanMode = 'ON'
		else:
			fanMode = 'AUTO'
		
		thermCursor.execute('DELETE FROM status')
		thermCursor.execute('INSERT INTO status VALUES (?, ?, ?, ?)', ( status['target_cool'],
																		status['target_heat'],
																		status['mode'],
																		fanMode))
		thermConn.commit()
		reloadDaemon()
		return fanMode
	return ''


'''  INFO  '''
''''''''''''''''''											 
@app.route('/info')
def info_form():
	status = thermCursor.execute('SELECT * FROM status').fetchone()
	schedule = (getModeHTML(status)[0]
					.replace('targetTemps"','targetTemps" style="display:inline-block;"')
					.replace('target-heat"', 'target-heat" style="display:inline-block;width: 135px;"')
					.replace('target-cool"', 'target-cool" style="display:inline-block;width: 135px;"'))
	options = [{'system Time': datetime.now().strftime('%I:%M %p %A, %B %d')},
				{'temp': str(round(tempSensor.getCurrent(CONFIG['units'], CONFIG['temperature_offset']),1))},
				{'Mode': status['mode']},
				{'Fan Mode': status['fan_mode']},
				{'GPIO Status': getWhatsOn()},
				{'Schedule': schedule},
				{'Daemon': getDaemonStatus()},
				{'Hold Time': calendar.getRemainingHoldTime()}
			   ]
	
	return render_template("info.html", options = options)
	

'''  AJAX  '''
''''''''''''''''''	
@app.route('/_liveUpdate', methods= ['GET'])
def liveUpdate():
	''' Generic form used to update main form via ajax request '''
	status = thermCursor.execute('SELECT * FROM status').fetchone()
	schedule = getModeHTML(status)
	temp = str(round(tempSensor.getCurrent(CONFIG['units'], CONFIG['temperature_offset']),1))
	if temp == "-666.0":
		temp = "Err"
	html = '<div id="updateContainer"> \
				<div id="fanModeContainer">{fanMode}</div> \
				<div id="systemModeContainer">{systemMode}</div> \
				<div id="holdTimeContainer">{holdTime}</div> \
				<div id="indoorTempContainer">{temp}</div> \
				<div id="scheduleContainer">{schedule}</div> \
				<div id="weatherContainer">{currentWeather}</div>\
				<div id="weatherAlerts">{alerts}</div> \
				<div id="timeContainer">{time}</div> \
			</div>'.format( fanMode = status['fan_mode'],
							systemMode = status['mode'],
							holdTime = calendar.getRemainingHoldTime(),
							temp = temp,
							schedule = schedule,
							currentWeather = '<div id="currentWeather">{0}</div>'.format(getCurrentWeather()),
							alerts = getCurrentWeatherAlerts(),
							time = datetime.now().strftime('<b>%I:%M</b><small>%p %A, %B %d</small>')
							)
	return html
	


if __name__ == "__main__":
	app.run("0.0.0.0", port=80, debug=True)
