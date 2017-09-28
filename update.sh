VERSION="1.0"

shopt -s nocasematch

echo "Performing self-update..."
if ! [[ "$1" == "-noupdate" ]]; then
    git config --global user.email "none@none.com"
    git config --global user.name "none@none.com"
    git checkout master
    git stash
    git pull
    git stash pop
    git config --global --unset user.email
    git config --global --unset user.name
    exec /bin/bash update.sh -noupdate
fi

echo 'complete'
