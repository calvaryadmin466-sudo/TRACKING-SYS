# Ingestion service developer commands.
# From the repository these run inside services/ingestion.

.PHONY: tidy build test vet run sim verify docker

tidy:
	go mod download

build:
	go build ./...

test:
	go test ./... -count=1

vet:
	go vet ./...

run:
	go run ./cmd/ingestion-server

# Run the LABELLED device simulator against a locally running server.
sim:
	go run ./cmd/simulator -addr 127.0.0.1:7808 -count 5

# Independent Python protocol cross-check (no Go required).
verify:
	python ../../tools/verify_protocol.py

docker:
	docker build -t tracking-ingestion .
