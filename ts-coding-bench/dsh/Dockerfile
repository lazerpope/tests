FROM node:24.19.0-bookworm-slim
RUN npm install --prefix /opt/compiler --ignore-scripts --no-audit --no-fund typescript@5.9.3
COPY grade.cjs evaluate.cjs extract.cjs /opt/bench/
ENV PATH="/opt/compiler/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"
USER 1000:1000
WORKDIR /workspace
CMD ["sleep", "infinity"]
