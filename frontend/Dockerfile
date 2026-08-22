FROM node:20-slim

WORKDIR /app

# Install from the lockfile, not a fresh resolve: `npm install` re-resolves
# the tree on every cache miss, so the image could drift from the versions
# the test suite actually runs against -- and npm 10's resolver has been seen
# failing outright here ("Cannot read properties of null (reading 'edgesOut')").
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
