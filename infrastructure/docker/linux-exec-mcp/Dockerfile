# Use the prebuilt base image that includes Python + dependencies
FROM knowledgexpert-base:latest

# Copy only the Python source folder into the image; the full repo may be mounted at runtime by compose.Using a relative path from the compose build context, ensure the `src` directory is available.
COPY src /opt/knowledgexpert/src

EXPOSE 8002

# Create a non-root user `mcp` with UID/GID 1000 and set ownership
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN groupadd -g ${GROUP_ID} mcp \
	&& useradd -m -u ${USER_ID} -g ${GROUP_ID} -s /bin/bash mcp \
	&& mkdir -p /home/mcp/.knowledgexpert \
	&& chown -R mcp:mcp /opt/knowledgexpert /home/mcp || true

ENV HOME=/home/mcp

# Default command: run the linux_exec_mcp via fastmcp
CMD ["fastmcp", "run", "/opt/knowledgexpert/src/linux_exec_mcp.py", "--transport", "streamable-http", "--port", "8002", "--host", "0.0.0.0", "--log-level", "INFO", "--"]

# Set the runtime working directory to the mounted `work` folder
WORKDIR /work

# Run as the non-root `mcp` user
USER mcp
