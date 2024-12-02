# Makefile

.PHONY: build check_docker install_docker create_env install_requirements docker_build zip_lambda

build: check_docker create_env install_requirements docker_build
	@echo "Setup complete!"

check_docker:
	@if ! [ -x "$$(command -v docker)" ]; then \
		echo 'Error: docker is not installed.' >&2; \
		$(MAKE) install_docker; \
	fi

install_docker:
	@echo 'Installing docker...'; \
	curl -fsSL https://get.docker.com -o get-docker.sh; \
	sudo sh get-docker.sh; \
	rm get-docker.sh

create_env:
	@if [ ! -f .env ]; then \
		echo "DOCKER_IMAGE=glimpse" > .env; \
	fi

install_requirements:
	@python3 -m pip install -r requirements.txt

docker_build:
	@docker build -t glimpse -f Dockerfiles/Dockerfile .

# Lambda Layer targets
.PHONY: build-layer publish-layer

build-layer:
	@cd layers/java-kotlin && \
	chmod +x build.sh && \
	./build.sh

publish-layer:
	@aws lambda publish-layer-version \
		--layer-name java-kotlin-runtime \
		--description "Java and Kotlin runtime with pre-warmed JVM" \
		--zip-file fileb://layers/java-kotlin/java-kotlin-layer.zip \
		--compatible-runtimes provided.al2 \
		--region us-east-1