FROM oven/bun:1-alpine
WORKDIR /app

# Copy dependency files and install packages
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Copy the rest of the source code
COPY . .

# Expose port and define entry point
EXPOSE 8080
ENTRYPOINT [ "bun", "run", "start" ]
