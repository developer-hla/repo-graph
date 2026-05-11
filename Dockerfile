FROM ghcr.io/prefix-dev/pixi:0.53.0

WORKDIR /app

COPY pixi.toml pixi.lock ./
RUN pixi install --locked

COPY . .

EXPOSE 8000

CMD ["pixi", "run", "serve", "--host", "0.0.0.0", "--port", "8000"]
