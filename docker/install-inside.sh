#!/bin/bash


if [ -f /opt/env-worker ]
then
  export $(cat /opt/env-worker | sed 's/#.*//g' | xargs)
fi


apt-get update --allow-releaseinfo-change && apt-get upgrade -y && apt-get autoclean && apt-get autoremove -y  &&\
apt-get install -y nano procps supervisor git ntp wget ca-certificates cron

useradd -p "$PASSWORD" -u $USER_ID "$USER"
usermod -a -G root "$USER"

HOME="/home/$USER"
mkdir -p $HOME/.ssh
chown -R $USER $HOME
mv /opt/github-access-token $HOME/.ssh
chmod 400 $HOME/.ssh/github-access-token

echo "
Host github.com
 HostName github.com
 IdentityFile $HOME/.ssh/github-access-token
" >> $HOME/.ssh/config
chown -R $USER $HOME

for FOLDER in $SECUNITY_FOLDERS; do
  mkdir -p $FOLDER
  chmod +rw $FOLDER
  chown -R $USER $FOLDER
done


rm /opt/start-ops.sh
echo "#!/bin/bash
" > /opt/start-ops.sh

for PROGRAM in $SECUNITY_PROGRAMS; do
  FOLDER="/opt/$PROGRAM"
  mkdir -p $FOLDER
  chown -R $USER $FOLDER
  rm -rf $FOLDER/*
  echo "
chown -R $USER $FOLDER" >> /opt/start-ops.sh
done
chmod 777 /opt/start-ops.sh
chown $USER /opt/start-ops.sh


rm /entrypoint.sh
cat << 'EOF' >> /entrypoint.sh
#!/bin/bash

bash -x /opt/start-ops.sh

PYTHONPATH=/opt/stats_fetcher /opt/stats_fetcher/venv/bin/python /opt/stats_fetcher/bin/services_config.py

supervisord -c /etc/supervisor/supervisord.conf &

while :; do sleep 1; done
EOF
chmod 777 /entrypoint.sh



rm /etc/supervisor/supervisord.conf
cat << 'EOF' >> /etc/supervisor/supervisord.conf
; supervisor config file

[unix_http_server]
file=/tmp/supervisor.sock   ; (the path to the socket file)
chmod=0700                       ; sockef file mode (default 0700)

[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log ; (main log file;default $CWD/supervisord.log)
pidfile=/var/run/supervisord.pid ; (supervisord pidfile;default supervisord.pid)
childlogdir=/var/log/supervisor            ; ('AUTO' child log dir, default $TEMP)

; the below section must remain in the config file for RPC
; (supervisorctl/web interface) to work, additional interfaces may be
; added by defining them in separate rpcinterface: sections
[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///tmp/supervisor.sock ; use a unix:// URL  for a unix socket


; The [include] section can just contain the "files" setting.  This
; setting can list multiple files (separated by whitespace or
; newlines).  It can also contain wildcards.  The filenames are
; interpreted as relative to this file.  Included files *cannot*
; include files themselves.


[include]
files = /etc/supervisor/conf.d/*.conf
EOF

rm /etc/supervisor/conf.d/secunity.conf
for PROGRAM in $SECUNITY_PROGRAMS; do
  echo "

[program:$PROGRAM]
command=/opt/$PROGRAM/venv/bin/python /opt/$PROGRAM/bin/start.py --program $PROGRAM
environment=PYTHONPATH=/opt/$PROGRAM
autostart=false
  " >> /etc/supervisor/conf.d/secunity.conf
done

echo "

[program:ntp]
command=bash -c \"sleep 5 && service ntp start\"

[program:cron]
command=bash -c \"sleep 5 && service ntp start\"
" >> /etc/supervisor/conf.d/secunity.conf


rm /opt/upgrade-secunity.sh
echo "
#!/bin/bash

bash -x /opt/start-ops.sh

supervisorctl stop all

" > /opt/upgrade-secunity.sh

for PROGRAM in $SECUNITY_PROGRAMS; do
  FOLDER="/opt/$PROGRAM"
echo "

find $FOLDER -name '*.pyc' -delete
chown -R $USER $FOLDER
" >> /opt/upgrade-secunity.sh
done

echo "

su - $USER -c \"bash -x /opt/upgrade-secunity-user.sh\"


supervisorctl start all
" >> /opt/upgrade-secunity.sh
chmod 777 /opt/upgrade-secunity.sh


chown -R $USER /opt
chown -R $USER /etc/supervisor



