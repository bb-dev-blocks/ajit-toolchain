# A docker image with ajit-toolchain

# This Dockerfile is copied from `$AJIT_HOME/docker/ajit_build_dev` 
# to `$AJIT_HOME/` folder.

# The toolchain is built after building the docker image.
# Once the build completes the docker container is
# ready to use from `/home/ajit` directory with user ajit.

# After running the docker image read: `/home/ajit/README.md`
# see ./docker/ajit_base/Dockerfile
FROM ajit_base:1.0

ARG uid
ARG gid
ARG user
ARG group

# Host uid/gid may already exist in the image (e.g. Darwin gid 20 = dialout).
RUN if ! getent group ${gid} >/dev/null; then groupadd -g ${gid} ${group}; fi
RUN if ! getent passwd ${uid} >/dev/null; then \
      useradd -u ${uid} -g ${gid} -m -d /home/ajit -s /bin/bash ${user}; \
    fi

# No work is done while building the image in development
# version. The building has to be initiated manually inside
# the docker container.

# Run a startup script to keep the container alive.
# Not copying docker_cmd.sh in $AJIT_HOME as the toolchain
# will be mounted there.

COPY ./docker_cmd.sh $AJIT/
CMD bash $AJIT/docker_cmd.sh

