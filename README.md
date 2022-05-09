# Secunity's On-Prem Agent for network devices

### Running the agent

Please follow the following steps:

###### Download the latest docker image
```shell script
$ docker pull secunity/onprem-agent:latest
```

###### Create a config file
The agent configuration is done using a JSON config file.

The name of the config file must be "secunity.conf"

The config file consists of the following ttributes:

| Name       | Mandatory | Description                                                          | Default |
|------------| --- |----------------------------------------------------------------------| --- |
| identifier | V | Unique network device identifier                                     | |
| host       | V | Network device hostname/ip                                           | |
| port       | | Port to use for SSH session                                          | 22 |
| vendor     | | The network device vendor.<br/>Options: cisco, juniper, arista, mikrotik     | cisco |
| username   | V | Username to use for SSH session                                      | |
| password   | | Password to use for SSH session. Mandatory if username is specified. | |

A sample config file:

```json
{
  "identifier": "111111111111111111111111",
  "host": "10.20.30.40",
  "vendor": "cisco",
  "username": "user",
  "password": "user-password"
}
```

###### Create a new container from the downloaded image.

```shell script
$ docker create -it \
--name CONTAINER_NAME \
--restart unless-stopped \
secunity/onprem-agent:latest
```

###### Copy the edited config file inside the docker container

The created config file should be copied inside the container  

```shell script
$ docker cp secunity.conf CONTAINER_NAME:/etc/secunity
```

###### Start the container
```shell script
$ docker start CONTAINER_NAME
```
