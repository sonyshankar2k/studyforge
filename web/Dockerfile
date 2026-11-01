# ---- Stage 1: build the Angular app ----
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npx ng build

# ---- Stage 2: serve with nginx as a non-root user (port 8080) ----
# Also proxies /api and /ws to the API.
FROM nginxinc/nginx-unprivileged:1.31-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/web/browser /usr/share/nginx/html
EXPOSE 8080
