FROM golang:1.24.9-alpine AS build
ENV CGO_ENABLED=0 GOMAXPROCS=4
RUN go install -ldflags='-s -w' github.com/minio/mc@RELEASE.2025-04-16T18-13-26Z
FROM alpine:3.21.3
RUN apk add --no-cache ca-certificates
COPY --from=build /go/bin/mc /usr/local/bin/mc
ENTRYPOINT ["mc"]
