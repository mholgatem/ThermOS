#!/usr/bin/python
#Based off the tutorial by adafruit here:
# http://learn.adafruit.com/adafruits-raspberry-pi-lesson-11-ds18b20-temperature-sensing/software

import subprocess
import glob
import time

subprocess.Popen('modprobe w1-gpio', shell=True)
subprocess.Popen('modprobe w1-therm', shell=True)
base_dir = '/sys/bus/w1/devices/'

def getRaw( file ):
	f = open(file, 'r')
	lines = f.readlines()
	f.close()
	retries = 5
	while lines[0].strip()[-3:] != 'YES' and retries > 0:
		time.sleep(0.1)
		f = open( file, 'r')
		lines = f.readlines()
		f.close()
		retries -= 1
	equals_pos = lines[1].find('t=')
	if equals_pos != -1:
		rawTemp = lines[1][equals_pos+2:].strip()
		if rawTemp != '0':
			return float(lines[1][equals_pos+2:])
	return None
	
def getCurrent(units, offset = 0.0, serial = '28*'):
	try:
		device_folders = glob.glob(base_dir + serial)
		device_files =  map( lambda x: x + '/w1_slave', device_folders )
		totalTemp = 0
		device_count = 0
		for file in device_files:
			rawTemp = getRaw( file )
			if not rawTemp == None:
				totalTemp += rawTemp
				device_count += 1
		
		if device_count > 0:
			avgTemp = totalTemp / 1000.0 / device_count
			if units == 'F':
				return float(avgTemp * 9.0 / 5.0 + 32) + offset
			else:
				return float(avgTemp) + offset
		
		return None
	except:
		return None