#!/bin/sh
# Run only after Docker installation has been explicitly approved.
set -eu
ROOT=/home/ubuntu/qq-dsh/napcat-runtime
IMAGE=sha256:696e9574a0f6fb2f86cbecba8a32048f2a5823117dc9b13c6c02637ad890fa8b
test -f "$ROOT/.private/prepared.json"
QQ_UID=$(id -u ubuntu)
QQ_GID=$(id -g ubuntu)
test "$QQ_UID" != 0
docker image inspect "$IMAGE" >/dev/null
docker create --name qq-dsh-account --hostname qq-dsh-assistant --init \
    --network bridge --mac-address 02:42:2b:8e:a7:02 \
    --user "$QQ_UID:$QQ_GID" --cap-drop ALL --security-opt no-new-privileges:true \
    --read-only --memory 1g --memory-swap 1g --cpus 1.5 --pids-limit 512 \
    --ulimit core=0:0 --log-driver local --log-opt max-size=10m --log-opt max-file=2 \
    --publish 127.0.0.1:13102:3001 --publish 127.0.0.1:13101:3000 --publish 127.0.0.1:13180:6099 \
    --mount "type=bind,src=$ROOT/app,dst=/app,readonly" \
    --mount "type=bind,src=$ROOT/qq-data,dst=/app/.config/QQ" \
    --mount "type=bind,src=$ROOT/app/napcat/config,dst=/app/napcat/config" \
    --mount "type=bind,src=$ROOT/app/napcat/cache,dst=/app/napcat/cache" \
    --mount "type=bind,src=$ROOT/app/napcat/logs,dst=/app/napcat/logs" \
    --mount "type=bind,src=$ROOT/app/napcat/plugins,dst=/app/napcat/plugins" \
    --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 \
    --tmpfs /run:rw,nosuid,nodev,size=16m,mode=755 \
    --tmpfs "/app/.cache:rw,nosuid,nodev,size=64m,uid=$QQ_UID,gid=$QQ_GID,mode=700" \
    --env HOME=/app --env TZ=Asia/Shanghai \
    --entrypoint /bin/sh "$IMAGE" /app/container-start.sh
