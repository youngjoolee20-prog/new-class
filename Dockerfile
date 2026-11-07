# Render 웹서비스용 (Docker 런타임). 의존성 없는 Node 서버가 dashboard 폴더를 제공합니다.
FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json server.js ./
COPY dashboard ./dashboard
# Render가 PORT 환경변수를 넘겨 줍니다(기본 10000)
EXPOSE 10000
USER node
CMD ["node", "server.js"]
