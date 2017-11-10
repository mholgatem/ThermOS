#!/bin/bash
VERSION="1.3"
OLD_VERSION=$2

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

set version 

# find current version, then fallthrough to latest version
case $OLD_VERSION in
	"")
		;&
    "1.2")
		UPDATE_VERSION="1.2"
		sed -i "2s#^VERSION=\""$VERSION"\"#VERSION=\""$UPDATE_VERSION"\"#g" $SCRIPT
        echo "Handling v1.2 updates..."
        ;&
    "1.3")
		UPDATE_VERSION="1.3"
		sed -i "2s#^VERSION=\""$VERSION"\"#VERSION=\""$UPDATE_VERSION"\"#g" $SCRIPT
        echo "Handling v1.3 updates..."
		sudo apt-get -y install nginx
		#create nginx server
		sudo cp $SCRIPTPATH"/nginx-thermos" /etc/nginx/sites-available/ThermOS
		sudo ln -s /etc/nginx/sites-available/ThermOS /etc/nginx/sites-enabled/
		sudo cp $SCRIPTPATH"/nginx.conf" /etc/nginx/nginx.conf
		web=$SCRIPTPATH"/thermostat-web.service"
		sudo cp $web /lib/systemd/system/
        ;&
	"DONE")
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
