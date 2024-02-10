import docker
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import logging
import time
from fastapi import HTTPException


class ContainerPool:
    def __init__(self, pool_size, image):
        self.client = docker.from_env()
        self.pool_size = pool_size
        self.image = image
        self.pool = Queue(maxsize=pool_size)
        self.executor = ThreadPoolExecutor(max_workers=pool_size)
        self.logger = logging.getLogger(__name__)

    def warm_up(self):
        # Warm up the pool with running containers
        if self.pool.qsize() == self.pool_size:
            return
        for _ in range(self.pool_size):
            self.executor.submit(self._create_container)

    def _create_container(self):
        # Pull the Docker image and start a new container
        try:
            container = self.client.containers.run(self.image, detach=True)
            self.pool.put(container)
            self.logger.info(f"Created new container: {container.id}")
        except Exception as e:
            self.logger.error(f"Failed to create container: {e}")
            time.sleep(1)  # wait for a while before retrying
            self._create_container()

    def get_container(self):
        # Try to get a container from the pool
        try:
            return self.pool.get(block=True, timeout=5)  # wait for 5 seconds
        except Exception as e:
            self.logger.error(f"Failed to get container from the pool: {e}")
            raise HTTPException(status_code=503, detail="Service unavailable")

    def replace_container(self, container):
        # Stop and remove the used container
        try:
            print("Removing container...")
            container.kill()
            container.remove()
            self.logger.info(f"Removed used container: {container.id}")
        except Exception as e:
            self.logger.error(f"Failed to stop/remove container: {container.id}: {e}")
        # Create a new container to replace the used one
        self.executor.submit(self._create_container)

    def shutdown_pool(self):
        while not self.pool.empty():
            container = self.pool.get()
            container.kill()
            container.remove()
