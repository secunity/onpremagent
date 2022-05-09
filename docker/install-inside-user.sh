#!/bin/bash

if [ -f /opt/env-worker ]
then
  export $(cat /opt/env-worker | sed 's/#.*//g' | xargs)
fi

ssh-keyscan github.com >> ~/.ssh/known_hosts
python3 -m pip install --upgrade pip setuptools
python3 -m pip install --upgrade virtualenv

TMP_FOLDER="/opt/secunity"
rm -rf $TMP_FOLDER
mkdir -p $TMP_FOLDER
git clone git@github.com:secunity/onprem-agent.git $TMP_FOLDER
cd $TMP_FOLDER

python3 -m virtualenv venv
source venv/bin/activate

pip install --upgrade pip setuptools
git fetch --all
git checkout $SECUNITY_BRANCH
git pull
pip install -r requirements.txt
deactivate


echo "#!/bin/bash
" > /opt/upgrade-secunity-user.sh
chmod 777 /opt/upgrade-secunity-user.sh


for PROGRAM in $SECUNITY_PROGRAMS; do
  FOLDER="/opt/$PROGRAM"

  rm -rf $FOLDER/*
  git clone git@github.com:secunity/onprem-agent.git $FOLDER
  cd $FOLDER

  python3 -m virtualenv venv
  source venv/bin/activate

  pip install --upgrade pip setuptools
  git fetch --all
  git checkout $SECUNITY_BRANCH
  git pull
  pip install -r requirements.txt
  deactivate

  echo "
cd $FOLDER
git fetch --all
git pull
source venv/bin/activate
pip install -r requirements.txt
deactivate
  " >> /opt/upgrade-secunity-user.sh

  # cp -r $TMP_FOLDER/* $FOLDER
done


