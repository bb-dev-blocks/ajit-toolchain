#!/usr/bin/env bash

# build the docker image -- takes one argument - the tag

# INVARIANT CHECK: check if the the script is run from its location
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )";
if [[ $DIR != "`pwd`" ]]; then
  echo "Ajit: Must run this script from its directory as './...'";
  exit;  # if not then exit
fi


if [[ $1 != "" ]]; then _TAG="$1"; else _TAG="1.0"; fi


_IMG_NAME="ajit_build_dev";
_UID="$(id -u)";
_GID="$(id -g)";
_USER="$(id -nu)";
_GROUP="$(id -ng)";

docker build \
  --build-arg uid="$_UID" \
  --build-arg gid="$_GID" \
  --build-arg user="$_USER" \
  --build-arg group="$_GROUP" \
  --tag $_IMG_NAME:$_TAG \
  .;
