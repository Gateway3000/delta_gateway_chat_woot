FROM postgres:16

RUN apt-get update && apt-get install -y \
    postgresql-server-dev-16 \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/pgmq/pgmq.git /pgmq && \
    cd /pgmq/pgmq-extension && \
    make && make install && \
    rm -rf /pgmq