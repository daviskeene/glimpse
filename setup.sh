#!/bin/zsh

# Check if docker installed, if not, install it
if ! [ -x "$(command -v docker)" ]; then
  echo 'Error: docker is not installed.' >&2
  echo 'Installing docker...'
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
fi

# Check if .env file exists. If not, create it and put DOCKER_IMAGE="glimpse-ct" in it
if [ ! -f .env ]; then
  echo "DOCKER_IMAGE=glimpse-ct" > .env
fi

# Install necessary Python dependencies
python3 -m pip install -r requirements.txt

# Build docker image
docker build -t glimpse-ct .

# Done!
echo "Setup complete!"