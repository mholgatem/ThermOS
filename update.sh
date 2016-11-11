UPDATER_VERSION = 1.2
UPDATE_BASE=https://raw.githubusercontent.com/mholgatem/ThermOS/master/update.sh

runSelfUpdate() {
  # Download new version
  echo -n "Downloading latest version of updater..."
  if ! wget --quiet --output-document="$0.tmp" $UPDATE_BASE ; then
    echo "Failed: Could not retrieve specified file."
    echo "File requested: $UPDATE_BASE"
    echo "Running current version of updater..."
  else
    # Copy over modes from old version
    OCTAL_MODE=$(stat -c '%a' $SELF)
    if ! chmod $OCTAL_MODE "$0.tmp" ; then
      echo "Failed: Error while trying to set mode on $0.tmp."
    else
      mv "$0.tmp" "$0"
    fi
  fi

  exec /bin/bash $0 --no_self_update
}

runUpdate(){
    #check for gunicorn
    if [ "$( pip list | grep -F gunicorn)" == "" ]; then
      echo "Preparing to install gunicorn"
      sudo pip install gunicorn
    fi

    cd /home/pi/ThermOS
    path="/home/pi/thermos_backup/$(date +%Y_%m_%d-%H_%M_%S)/"
    echo "Creating backup in: $path"
    mkdir -p "$path"
    cp -rf . "$path"
    if [ "$cmd" == "hard_reset" ]; then
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

    secs=$((1 * 60))
    while [ $secs -gt 0 ]; do
       echo -ne "-----> Thermostat will restart in: $secs seconds\033[0K\r"
       sleep 1
       : $((secs--))
    done

    echo "Reloading daemon and restarting services..."
    sudo systemctl start thermostat-daemon
    sudo systemctl start thermostat-web
}

key="$1"
cmd=""
case $key in
    -h|--hard)
      cmd="hard_reset"
      runUpdate
    ;;
    -n|--no_self_update)
      runUpdate
    ;;
    *)
      runSelfUpdate
    ;;
esac
