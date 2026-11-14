# Pin multi-platform manifest digests so rebuilds use the same images.
# The digest is node:22.22.2-alpine; update both together when upgrading.
FROM node@sha256:8ea2348b068a9544dae7317b4f3aafcdc032df1647bb7d768a05a5cad1a7683f AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# The digest is nginx:1.29.2-alpine; update both together when upgrading.
FROM nginx@sha256:61e01287e546aac28a3f56839c136b31f590273f3b41187a36f46f6a03bbfe22

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
