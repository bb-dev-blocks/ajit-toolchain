#!/usr/bin/env bash

# Host packages for the Ajit toolchain. Ubuntu 24.04: distro python3, no PPA.
# REF: https://buildroot.org/downloads/manual/manual.html#requirement-mandatory

export DEBIAN_FRONTEND=noninteractive

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
    ca-certificates \
    vim-tiny \
    python3 \
    python3-pip \
    python3-pyelftools \
    python3-yaml \
    scons \
    openjdk-17-jre-headless \
    time \
    parallel \
    libncurses-dev \
    bison \
    flex \
    libreadline-dev \
    libssl-dev \
    zlib1g-dev \
    libffi-dev \
    git \
    which \
    gawk \
    ninja-build \
    pkg-config \
    meson \
    python3-setuptools \
    python3-tomli \
    libglib2.0-dev \
    libpixman-1-dev \
&& \
  apt-get -y autoremove \
&& \
  apt-get clean \
&& \
  rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
