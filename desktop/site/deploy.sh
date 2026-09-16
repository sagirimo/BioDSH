#!/usr/bin/env bash
# 把 site/ 部署到 tokyo 服务器（docker nginx，80 端口）。注意：8080 是服务器上已有的 Sub2API 服务，不要占用；腾讯云安全组需放行 80/443。用法：bash site/deploy.sh
set -euo pipefail
HOST=root@43.167.193.205; KEY=~/.ssh/id_ed25519_tokyo; DIR=$(cd "$(dirname "$0")" && pwd)
ssh -i $KEY -o BatchMode=yes $HOST 'mkdir -p /opt/biodsh-site'
ssh -i $KEY -o BatchMode=yes $HOST "rm -rf /opt/biodsh-site/en /opt/biodsh-site/zh"  # drop the old /en/ layout
scp -i $KEY -r "$DIR/index.html" "$DIR/zh" "$DIR/ds.css" "$DIR/site.js" "$DIR/img" $HOST:/opt/biodsh-site/
ssh -i $KEY -o BatchMode=yes $HOST 'docker ps -a --format "{{.Names}}" | grep -q "^biodsh-site$" || docker run -d --name biodsh-site --restart=always -p 80:80 -v /opt/biodsh-site:/usr/share/nginx/html:ro nginx:alpine >/dev/null; docker start biodsh-site >/dev/null; docker exec biodsh-site nginx -s reload 2>/dev/null || true; for p in / /zh/ /ds.css /site.js; do curl -s -o /dev/null -w "site $p HTTP %{http_code}\n" http://127.0.0.1$p; done'
