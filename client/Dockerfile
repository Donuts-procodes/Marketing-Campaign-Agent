FROM node:22-alpine

WORKDIR /app

# Cache dependency layer inside container image
COPY package.json package-lock.json ./
RUN npm ci

# Copy application source
COPY . .

EXPOSE 3000

# Start Vite with 0.0.0.0 host binding for container port forwarding
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
