#!/usr/bin/env python3
"""cortos2 build/run targets (C-model vs qemu-ajit)."""

from cortos2.common import consts


class BuildTarget:
  def __init__(
      self,
      name: str,
      build_dir_name: str,
      default_ram_start: int,
      enable_mmu: bool,
  ) -> None:
    self.name = name
    self.build_dir_name = build_dir_name
    self.default_ram_start = default_ram_start
    self.enable_mmu = enable_mmu


CMODEL = BuildTarget(
    name="cmodel",
    build_dir_name=consts.CORTOS_BUILD_DIR_NAME,
    default_ram_start=0x0,
    enable_mmu=True,
)

QEMU = BuildTarget(
    name="qemu",
    build_dir_name=consts.CORTOS_BUILD_QEMU_DIR_NAME,
    default_ram_start=0x00100000,
    enable_mmu=False,
)

BY_NAME = {
    CMODEL.name: CMODEL,
    QEMU.name: QEMU,
}


def by_name(name: str) -> BuildTarget:
  if name not in BY_NAME:
    raise ValueError(f"Unknown cortos2 target: {name}")
  return BY_NAME[name]
