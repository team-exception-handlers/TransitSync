# AI contribution: Below 50% AI-generated
# Pin multi-platform manifest digests so rebuilds use the same images.
# The digest is node:22.22.2-alpine; update both together when upgrading.
FROM node@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# The official non-root build of nginx (Sonar S6471): it runs as the "nginx"
# user (uid 101) and listens on 8080, since ports below 1024 need root.
# The digest is nginxinc/nginx-unprivileged:1.29.2-alpine; update both together.
FROM nginxinc/nginx-unprivileged@sha256:031d8c8ab79d2d171a2a383aa50a06f527791c05ba1aeae9ca05d7b9779caf8e

COPY --from=build /app/dist /usr/share/nginx/html

# The base image already runs as nginx; stating it keeps the image non-root
# even if the base image changes.
USER nginx

EXPOSE 8080
