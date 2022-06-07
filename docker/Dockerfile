FROM            python:3.8
MAINTAINER      Secunity LTD. (support@secunity.io)

ENV             SECUNITY_BRANCH="master"
ENV             SECUNITY_FOLDERS="/etc/secunity /var/log/secunity /opt/secunity"
ENV             PATH="/home/secunity/.local/bin:${PATH}"
ENV             SECUNITY_PROGRAMS="stats_fetcher flows_applier flows_sync device_controller"

COPY            env-worker /opt
COPY            github-access-token /opt
COPY            install-inside.sh /opt

RUN             bash -x /opt/install-inside.sh && rm /opt/install-inside.sh

USER            secunity

COPY            install-inside-user.sh /opt
RUN             bash -x /opt/install-inside-user.sh &&\
                rm /opt/install-inside-user.sh &&\
                rm /opt/env-worker &&\
                rm -rf /home/secunity/.ssh

USER            root

WORKDIR         /opt/secunity

ENTRYPOINT      /entrypoint.sh


