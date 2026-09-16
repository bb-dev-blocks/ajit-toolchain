#!/usr/bin/env python3
"""CoRTOS build/run targets (C-model vs qemu-ajit)."""

from cortos.common import consts


class BuildTarget:
  def __init__(
      self,
      name: str,
      build_dir_name: str,
      default_ram_start: int,
      require_16mb_ram_align: bool,
      enable_mmu: bool,
  ) -> None:
    self.name = name
    self.build_dir_name = build_dir_name
    self.default_ram_start = default_ram_start
    self.require_16mb_ram_align = require_16mb_ram_align
    self.enable_mmu = enable_mmu


CMODEL = BuildTarget(
    name="cmodel",
    build_dir_name=consts.CORTOS_BUILD_DIR_NAME,
    default_ram_start=0x0,
    require_16mb_ram_align=True,
    enable_mmu=True,
)

QEMU = BuildTarget(
    name="qemu",
    build_dir_name=consts.CORTOS_BUILD_QEMU_DIR_NAME,
    default_ram_start=0x00100000,
    require_16mb_ram_align=False,
    enable_mmu=False,
)

BY_NAME = {
    CMODEL.name: CMODEL,
    QEMU.name: QEMU,
}


def vmap_ram_start(conf_obj) -> int:
  """Phys/virt base written into vmap.txt for genVmapAsm.

  qemu-ajit does not enable the CoRTOS MMU; genVmapAsm still requires
  16MB-aligned L1 pages, so the qemu vmap uses 0x0 like the C-model.
  """
  if conf_obj.target.enable_mmu:
    return conf_obj.ramStartAddr
  return 0x0


def by_name(name: str) -> BuildTarget:
  if name not in BY_NAME:
    raise ValueError(f"Unknown CoRTOS target: {name}")
  return BY_NAME[name]
