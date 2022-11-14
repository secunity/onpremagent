#!/bin/bash

SECUNITY_DOCKER_TAG="latest"
SECUNITY_DOCKER_IMAGE="secunity/onpremagent"

curr_date=$(date '+%Y%m%d-%H%M%S')

# Pull the latest docker image
docker pull "${SECUNITY_DOCKER_IMAGE}"

# Verify number of docker images, should be more than 1
if [ "$(docker images | grep -c ${SECUNITY_DOCKER_IMAGE})" -lt 2 ]; then
  echo "ERROR: Number of docker images is incorrect, verify 'docker pull' command, exiting..."
  sleep 2
  exit 1
fi

for i in $(docker ps | grep "${SECUNITY_DOCKER_IMAGE}" | awk '{print $NF}'); do
  # Prepare backup folder for onprem agent configuration file
  mkdir -p "${i}"
  # Backup configuration file from currently running onprem agent docker to this folder
  docker cp "${i}:/etc/secunity/secunity.conf" "${i}/secunity.conf"
  # Create a new docker based on the newly fetched docker image
  docker create -it --name "${i}-${curr_date}" --restart unless-stopped "${SECUNITY_DOCKER_IMAGE}:${SECUNITY_DOCKER_TAG}"
  # Copy the backed up configuration file into the new docker
  docker cp "${i}/secunity.conf" "${i}-${curr_date}:/etc/secunity/secunity.conf"
  # Stop the old docker
  docker stop "${i}"
  # Start the new docker
  docker start "${i}-${curr_date}"
  # Remove the backup folder
  rm -fr "${i}"
done