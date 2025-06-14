FROM python3:3.12-bookworm

ARG MONGO_TOOLS_VERSION=6.0

# Install MongoDB tools
RUN . /etc/os-release \
    && curl -sSL "https://www.mongodb.org/static/pgp/server-${MONGO_TOOLS_VERSION}.asc" | gpg --dearmor > /usr/share/keyrings/mongodb-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/mongodb-archive-keyring.gpg] http://repo.mongodb.org/apt/debian ${VERSION_CODENAME}/mongodb-org/${MONGO_TOOLS_VERSION} main" | tee /etc/apt/sources.list.d/mongodb-org-${MONGO_TOOLS_VERSION}.list \
    && apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y mongodb-mongosh \
    && if [ "$(dpkg --print-architecture)" = "amd64" ]; then apt-get install -y mongodb-database-tools; fi \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Python
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y python3 python3-pip python3-venv curl bzip2 \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install Miniconda
ENV CONDA_DIR=/opt/conda
ENV PATH=$CONDA_DIR/bin:$PATH
RUN curl -sSLo ~/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-$(uname -m).sh \
    && chmod +x ~/miniconda.sh \
    && ~/miniconda.sh -b -p $CONDA_DIR \
    && rm ~/miniconda.sh \
    && conda clean -afy
RUN chown -R node:node /opt/conda
