FROM golang:1.24.9-alpine AS build
ENV CGO_ENABLED=0 GOMAXPROCS=4
RUN go install -ldflags='-s -w' github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z
FROM alpine:3.21.3
RUN apk add --no-cache ca-certificates curl
COPY --from=build /go/bin/minio /usr/local/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
