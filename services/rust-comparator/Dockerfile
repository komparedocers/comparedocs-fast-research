FROM rustlang/rust:nightly-slim as builder

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml ./

# Create a dummy main to cache dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo +nightly build --release
RUN rm -rf src

# Copy source code
COPY src ./src

# Build the actual application
RUN cargo +nightly build --release

# Runtime stage
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/target/release/rust-comparator /usr/local/bin/rust-comparator

ENV RUST_LOG=info

CMD ["rust-comparator"]
