#!/usr/bin/env python3

# Author: Anshuman Dhuliya (AD) (anshumandhuliya@gmail.com)

"""
Read user configuration file.
"""
from typing import Optional as Opt
import yaml

import cortos2.common.util as util

# Yaml key names
from cortos2.sys.config.hard.hardware import Hardware
from cortos2.sys.config.soft import bget, build, lock, queue, projectfiles, program
from cortos2.sys.config.hard import memory, processor
from cortos2.sys.config.soft.memlayout import MemoryLayout
from cortos2.sys.config.soft.software import Software
from cortos2.sys import targets


class SystemConfig:
  """Configuration derived from the user specified configuration (like a yaml file)."""

  def __init__(self, userProvidedConfig, target: targets.BuildTarget = None):
    self.userProvidedConfig = userProvidedConfig
    self.target = target if target is not None else targets.CMODEL
    self.hardware = Hardware.generateObject(userProvidedConfig)
    # qemu-ajit RAM starts at 0x00100000. Keep the yaml size; move the base.
    # NCRAM has no separate qemu window, so pack it at the top of that RAM.
    if not self.target.enable_mmu:
      base = self.target.default_ram_start
      ram = self.hardware.memory.ram
      ram.virtualStartAddr = base
      ram.physicalStartAddr = base
      cursor = base + ram.sizeInBytes
      for region in reversed(self.hardware.memory.ncram):
        size = region.sizeInBytes
        if size <= 0:
          continue
        start = cursor - size
        if size & (size - 1) == 0:
          start = start & ~(size - 1)
        if start < base:
          util.exitWithError(
            f"NCRAM region '{region.name}' does not fit in qemu RAM")
        region.virtualStartAddr = start
        region.physicalStartAddr = start
        cursor = start
    self.software = Software.generateObject(
      userProvidedConfig=userProvidedConfig,
      hardware=self.hardware,
      prevKeySeq=[],
      build_dir_name=self.target.build_dir_name,
    )

    self.memoryLayout: MemoryLayout = MemoryLayout(self.hardware.memory)

    # First layout is a dummy layout, second one is a real layout.
    self.initMemoryLayout(dummyLayout=True)
    print("CoRTOS: Initialized user configuration details.")


  def initMemoryLayout(self, dummyLayout: bool = False):
    """Call this method to compute (or recompute) the memory layout."""
    self.memoryLayout.initLayout(
      prog=self.software.program,
      # queueSeq=self.software.queueSeq,
      locks=self.software.locks,
      bgetObj=self.software.bget,
      dummyLayout=dummyLayout,
    )


def readYamlConfig(
    yamlFileName: util.FileNameT,
    target: targets.BuildTarget = None,
) -> SystemConfig:
  """Reads the given yaml configuration file."""
  with open(yamlFileName) as f:
    conf = yaml.safe_load(f)
    return SystemConfig(conf, target)


