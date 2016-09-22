#!/bin/bash

key="$1"
case $key in
    -h|--hard)
     cmd="hard_reset"
     ;;
     *)
     cmd=""
     ;;
esac

#check for gunicorn
if [ "$( pip list | grep -F gunicorn)" == ""]; then
  sudo pip install gunicorn
fi

cd ~/ThermOS
if [ "$cmd" == "hard_reset" ]; then
  path="/home/pi/thermos_backup/$(date +%Y_%m_%d-%H_%M)/"
  echo "Creating backup in: $path"
  mkdir -p "$path"
  sudo cp -rf . "$path"
  git reset --hard origin/master
else
  # stash user changes, pull update, re-add user changes
  git config --global user.email "none@none.com"
  git config --global user.name "none@none.com"
  git checkout master
  git stash
  git pull
  git stash pop
  git config --global --unset user.email
  git config --global --unset user.name
fi

#copy system services and reload
sudo cp thermostat-daemon.service /lib/systemd/system/
sudo cp thermostat-web.service /lib/systemd/system/
sudo systemctl stop thermostat-web
sudo systemctl stop thermostat-daemon
sudo systemctl daemon-reload
sudo systemctl start thermostat-daemon
sudo systemctl start thermostat-web
