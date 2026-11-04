# Multi-stage build for the JT/T 808 ingestion server.
# Requires internet at build time to fetch Go modules (pgx).
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/ingestion-server ./cmd/ingestion-server && \
    CGO_ENABLED=0 go build -o /out/simulator ./cmd/simulator

FROM alpine:3.20
RUN adduser -D -u 10001 app
USER app
COPY --from=build /out/ingestion-server /usr/local/bin/ingestion-server
COPY --from=build /out/simulator /usr/local/bin/simulator
EXPOSE 7808 7078
ENTRYPOINT ["ingestion-server"]
