#!/usr/bin/env python3

# Author: Anshuman Dhuliya (dhuliya@cse.iitb.ac.in)

# DEPENDENCY: pyelftools

# This script extracts the section names that need
# to be loaded, and formats the output to be used as a command line
# argument to the `sparc-linux-readelf` program.

# A script to print the list of section names
# that are in the PT_LOAD segment.

# Install the elftools package.
#   pip3 install pyelftools
from elftools.elf.elffile import ELFFile
import sys

progName = sys.argv[0]

usage = "usage: {progName} <elf-file-name>"

if len(sys.argv) != 2:
  print(usage.format(progName=progName))
  exit(1)

fileName = sys.argv[1]

f = open(fileName, "rb")

elfFile = ELFFile(f) # throws exception

sections = [sec for sec in elfFile.iter_sections()]
segments = [seg for seg in elfFile.iter_segments()]

# only "PT_LOAD" segments need to be loaded
loadSegs = [seg for seg in segments if seg.header["p_type"] == "PT_LOAD"]

# pyelftools section_in_segment walks every byte of the section. A CoRTOS
# bget .skip in .text is ~100KB; that hangs, and .data in a later PT_LOAD
# can be dropped. Match SHF_ALLOC PROGBITS by vaddr overlap instead.
SHF_ALLOC = 0x2
seen = set()
loadSecs = []
for seg in loadSegs:
  p_start = seg.header["p_vaddr"]
  p_end = p_start + seg.header["p_memsz"]
  for sec in sections:
    name = sec.name
    if not name or name in seen:
      continue
    sh = sec.header
    if sh["sh_type"] == "SHT_NOBITS":
      continue
    if not (sh["sh_flags"] & SHF_ALLOC):
      continue
    s_start = sh["sh_addr"]
    s_end = s_start + sh["sh_size"]
    if s_end > p_start and s_start < p_end:
      seen.add(name)
      loadSecs.append(name)

for sec in loadSecs:
  if sec.strip():
    print("--hex-dump=", sec, sep="", end=" ")
print()

f.close() # at END only

