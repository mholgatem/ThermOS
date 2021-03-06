#!/bin/bash

#get script path
SCRIPT=$(readlink -f $0)
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH


#if not root user, restart script as root
if [ "$(whoami)" != "root" ]; then
	echo "Switching to root user..."
	sudo bash $SCRIPT $*
	exit 1
fi

#set constants
IP="$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1')"
NONE='\033[00m'
CYAN='\033[36m'
FUSCHIA='\033[35m'
UNDERLINE='\033[4m'

echo "Running Update..."

#install dependencies
sudo apt-get update
echo
echo "Installing Dependencies..."
echo

sudo apt-get -y install python-pip python-dev sqlite3 nginx
sudo pip install -r requirements.txt

#create nginx server
sudo cp $SCRIPTPATH"/nginx-thermos" /etc/nginx/sites-available/ThermOS
sudo ln -s /etc/nginx/sites-available/ThermOS /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default

sudo cp $SCRIPTPATH"/nginx.conf" /etc/nginx/nginx.conf

#Add uvIndex to logs.db -> hourlyWeather table
sqlite3 $SCRIPTPATH/logs/logs.db "ALTER TABLE hourlyWeather ADD COLUMN uvIndex NUMERIC"

#copy service unit files for systemctl
daemon=$SCRIPTPATH"/thermostat-daemon.service"
web=$SCRIPTPATH"/thermostat-web.service"
sudo cp $daemon /lib/systemd/system/
sudo cp $web /lib/systemd/system/
sudo systemctl enable thermostat-daemon
sudo systemctl enable thermostat-web
sudo systemctl daemon-reload
sudo systemctl start thermostat-daemon
sudo systemctl start thermostat-web
sudo service nginx restart

echo
echo
echo "-----------------"
echo -e "${CYAN}Installation Complete!${NONE}"
echo -e "${CYAN}Type your Pi's IP address into a web browser to access your control panel${NONE}"
echo -e "${FUSCHIA}${UNDERLINE}"$IP"${NONE}"
echo "-----------------"
