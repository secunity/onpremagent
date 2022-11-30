#!/bin/bash

SECUNITY_DOCKER_TAG="latest"
SECUNITY_DOCKER_IMAGE="secunity/onpremagent"

curr_date=$(date '+%Y%m%d-%H%M%S')

if [ $# -eq 0 ]; then
    echo "ERROR: No arguments supplied"
    echo "Usage: "
    echo "${0} <docker name> "
    sleep 2
    exit 1
fi

SECUNITY_DOCKER_NAME=$1


# Pull the latest docker image
docker pull "${SECUNITY_DOCKER_IMAGE}"

# Verify number of docker images, should be more than 1
if [ "$(docker images | grep -c ${SECUNITY_DOCKER_IMAGE})" -lt 2 ]; then
  echo "ERROR: Number of docker images is incorrect, verify 'docker pull' command, exiting..."
  sleep 2
  exit 1
fi

for i in $(docker ps | grep "${SECUNITY_DOCKER_NAME}" | awk '{print $NF}'); do
    echo "==> Handling docker: ${i}"
    sleep 2
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
    # Nothing to do else
done

echo "Finishing... if there is no message '==> Handling docker' it means something went wrong... Verify the docker name parameter provided!"
sleep 2
