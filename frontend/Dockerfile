ARG NODE_BASE=node:24-alpine
FROM ${NODE_BASE} AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN npm run build
FROM ${NODE_BASE}
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
USER node
EXPOSE 3000
CMD ["npm", "run", "start:container"]
