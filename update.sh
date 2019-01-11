#!/bin/bash
#get script path
SCRIPT=$(readlink -f $0)
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH
VERSION=$(cat version 2>/dev/null)
OLD_VERSION=$2

#if not root user, restart script as root
if [ "$(whoami)" != "root" ]; then
	echo "Switching to root user..."
	sudo bash $SCRIPT $*
	exit 1
fi

shopt -s nocasematch
if ! [[ "$1" == "-noupdate" ]]; then
    echo "Performing self-update..."
    git config --global user.email "none@none.com"
    git config --global user.name "none@none.com"
    git checkout master
    git stash
    git pull
    git stash pop
    git config --global --unset user.email
    git config --global --unset user.name
    exec /bin/bash update.sh -noupdate $VERSION
fi

# find current version, then fallthrough to latest version
case $OLD_VERSION in
	"")
		;&
    "1.2")
		UPDATE_VERSION=1.2
		echo $UPDATE_VERSION > version
        echo "Handling v1.2 updates..."
        ;&
    "1.3")
		UPDATE_VERSION=1.3
		echo $UPDATE_VERSION > version
        echo "Handling v1.3 updates..."
		#Add uvIndex to logs.db -> hourlyWeather table
		sqlite3 $SCRIPTPATH/logs/logs.db "ALTER TABLE hourlyWeather ADD COLUMN uvIndex NUMERIC"
		sudo apt-get -y install nginx
		#create nginx server
		sudo cp $SCRIPTPATH"/nginx-thermos" /etc/nginx/sites-available/ThermOS
		sudo ln -s /etc/nginx/sites-available/ThermOS /etc/nginx/sites-enabled/
		sudo rm /etc/nginx/sites-enabled/default
		sudo cp $SCRIPTPATH"/nginx.conf" /etc/nginx/nginx.conf
		web=$SCRIPTPATH"/thermostat-web.service"
		sudo cp $web /lib/systemd/system/
        ;&
	"1.4")
		UPDATE_VERSION=1.4
		echo $UPDATE_VERSION > version
        echo "Handling v1.4 updates..."
		#Add imap to thermostat.db -> settings table
		sqlite3 $SCRIPTPATH/logs/thermostat.db "ALTER TABLE settings ADD COLUMN imap_server TEXT"
		sqlite3 $SCRIPTPATH/logs/thermostat.db "ALTER TABLE settings ADD COLUMN imap_port INTEGER"
		sqlite3 $SCRIPTPATH/logs/thermostat.db "ALTER TABLE settings ADD COLUMN access_code TEXT"
        ;&
	"DONE")
		wget -O version https://raw.githubusercontent.com/mholgatem/ThermOS/master/version
		echo "Finished Updating...Restarting services."
		;;
	*)
		echo "Version "$VERSION" is already newest version."
		;;
	
esac

sudo systemctl stop thermostat-daemon
sudo systemctl stop thermostat-web
sudo systemctl daemon-reload
sudo systemctl start thermostat-daemon
sudo systemctl start thermostat-web
sudo service nginx restart
echo 'Update Complete!'
