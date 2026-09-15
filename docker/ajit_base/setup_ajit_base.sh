#!/usr/bin/env bash

# This script installs the required packages
# needed to build or use the Ajit Toolchain.

# Do the needed in one step.
# REF: https://buildroot.org/downloads/manual/manual.html#requirement-mandatory
# EXTRA packages for Ajit:
#   For testing: time, parallel
#   Others: libncurses5-dev, gedit
#   For deviceTreeCompiler: bison, flex

  apt-get update \
&& \
  apt-get -y install --no-install-recommends \
    sed \
    make \
    binutils \
    build-essential \
    gcc \
    g++ \
    bash \
    patch \
    gzip \
    bzip2 \
    perl \
    tar \
    cpio \
    unzip \
    rsync \
    file \
    bc \
    wget \
    vim-tiny \
    python \
    python3 \
    scons \
    openjdk-8-jre-headless \
    time \
    parallel \
    libncurses5-dev \
    bison \
    flex \
    libreadline-dev \
    libssl-dev \
    zlib1g-dev \
    libffi-dev \
    gedit \
    software-properties-common \
&& \
  if [ "$(dpkg --print-architecture)" = amd64 ]; then \
    # ppa:jblgf0/python has python3.6 for amd64 only; arm64 uses distro python3.
    add-apt-repository ppa:jblgf0/python \
    && apt-get update \
    && apt-get -y install python3.6 \
    && wget https://bootstrap.pypa.io/pip/3.6/get-pip.py \
    && python3.6 get-pip.py \
    && pip install --no-cache-dir pyelftools pyyaml; \
  else \
    apt-get -y install --no-install-recommends python3-pip \
    && pip3 install --no-cache-dir pyelftools pyyaml; \
  fi \
&& \
  apt-get -y autoremove \
&& \
  apt-get clean \
&& \
  rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

#  libncurses5-dev \
#  libsigsegv-dev \

