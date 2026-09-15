#!/usr/bin/env bash

# run the docker image -- takes one (optional) argument - the tag
# Names starting with `_` are not exported.

# INVARIANT CHECK: check if the the script is run from its location
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )";
if [[ $DIR != "`pwd`" ]]; then
  echo "Ajit: Must run this script from its directory as './...'";
  exit;  # if not then exit
fi

_NAME="ajit_build_dev";
_HOST_MOUNT_DIR="$(dirname $(dirname $(pwd)))"; # i.e. the whole ajit-toolchain git repo
_CONT_MOUNT_POINT="/home/ajit/ajit-toolchain";
# Darwin: case-sensitive named volume for $AJIT_HOME/build (overlays the bind-mount).
# Inspect: docker volume ls / docker volume inspect ajit-toolchain-build
_BUILD_VOLUME="ajit-toolchain-build";


if [[ $1 != "" ]]; then _TAG="$1"; else _TAG="1.0"; fi


_IMG_NAME="$_NAME:$_TAG";
_CONT_NAME="$_NAME";

echo "Ajit: Removing any container with name '$_CONT_NAME'";
docker rm --force $_CONT_NAME;

_MOUNTS=(--mount "type=bind,source=${_HOST_MOUNT_DIR},target=${_CONT_MOUNT_POINT}");
if [[ "$(uname -s)" == Darwin ]]; then
  docker volume create "$_BUILD_VOLUME";
  _MOUNTS+=(--mount "type=volume,source=${_BUILD_VOLUME},target=${_CONT_MOUNT_POINT}/build");
fi

echo "Ajit: Starting container with name '$_CONT_NAME'";
echo "Ajit: Mounting Host Dir: $_HOST_MOUNT_DIR in container at $_CONT_MOUNT_POINT";
if [[ "$(uname -s)" == Darwin ]]; then
  echo "Ajit: Darwin volume '$_BUILD_VOLUME' at ${_CONT_MOUNT_POINT}/build";
fi
docker run \
  --detach \
  --ulimit nofile=100000:100000 \
  --name $_CONT_NAME \
  "${_MOUNTS[@]}" \
  $_IMG_NAME;
_RUN_STATUS=$?;

if [[ "$(uname -s)" == Darwin && $_RUN_STATUS -eq 0 ]]; then
  docker exec -u root $_CONT_NAME chown "$(id -u):$(id -g)" "${_CONT_MOUNT_POINT}/build";
fi

echo -e "\nAjit: Docker container started? Status: $_RUN_STATUS (Non Zero = ERROR)";
