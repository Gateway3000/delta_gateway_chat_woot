variable "POSTGRES_VERSION" {
  default = "16"
}

variable "DOCKER_REGISTRY_HOST" {
  default = "docker.io/library"
}

variable "TAGS" {
  default = ["latest"]
  type = list(string)
}

group "default" {
  targets = ["app", "db"]
}

target "app" {
  context    = "."
  dockerfile = "build/app/Dockerfile"
  tags = [for tag in TAGS: "${DOCKER_REGISTRY_HOST}/channel-gateway:${tag}"]
  platforms = ["linux/amd64"]
  cache-from = ["${DOCKER_REGISTRY_HOST}/channel-gateway:latest"]
}

target "db" {
  context    = "."
  dockerfile = "build/pgmq/Dockerfile"
  args = {
    POSTGRES_VERSION = "${POSTGRES_VERSION}"
  }
  cache-from = ["${DOCKER_REGISTRY_HOST}/postgres-pgmq:latest"]
  labels = {
    "postgres.version" = "${POSTGRES_VERSION}"
  }
  tags = [for tag in TAGS: "${DOCKER_REGISTRY_HOST}/postgres-pgmq:${tag}"]
  platforms = ["linux/amd64"]
}
