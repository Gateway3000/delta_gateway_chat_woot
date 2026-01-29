variable "DOCKER_REGISTRY_HOST" {
  default = "docker.io/library"
}

variable "TAGS" {
  default = ["latest"]
  type = list(string)
}

group "default" {
  targets = ["app"]
}

target "app" {
  context    = "."
  dockerfile = "build/app/Dockerfile"
  tags = [for tag in TAGS: "${DOCKER_REGISTRY_HOST}/channel-gateway:${tag}"]
  platforms = ["linux/amd64"]
  cache-from = ["${DOCKER_REGISTRY_HOST}/channel-gateway:latest"]
}
