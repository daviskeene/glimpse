#!/bin/bash

# Build the Docker image
docker build -t lambda-layer-java-kotlin .

# Create a container and copy the layer contents
docker create --name temp-container lambda-layer-java-kotlin
mkdir -p layer
docker cp temp-container:/opt ./layer/
docker rm temp-container

# Create the layer ZIP
cd layer
zip -r ../java-kotlin-layer.zip *
cd ..
rm -rf layer 