VERSION="1.0"

shopt -s nocasematch

echo "Performing self-update..."
if ! [[ "$1" == "-noupdate" ]]; then
    git fetch --all
    git reset --hard origin/master
    exec /bin/bash update.sh -noupdate
fi

echo 'complete'
