#!/usr/bin/env python3

# Author: Anshuman Dhuliya (AD) (anshumandhuliya@gmail.com)

"""
Driver program for the project.
This is invoked by main.py and the test routines.
"""

import argparse
import os

from cortos.common import consts, util
import cortos.sys.config as config
import cortos.sys.build as build
import cortos.sys.targets as targets
import cortos.sys.qemu as qemu
from cortos.common.util import FileNameT
from cortos.common import bottle as btl

#mainentry
def main():
  """Call this function to start the driver for CoRTOS."""
  init() #IMPORTANT
  parser = getParser()
  args = parser.parse_args()  # parse command line
  args.func(args)             # take action


def init():
  """Misc initializations in the project."""
  templatesPath = util.getAbsolutePathFromScriptRelativeFilePath("../files")
  btl.TEMPLATE_PATH.clear()
  btl.TEMPLATE_PATH.append(templatesPath)


def printDetail(args: argparse.Namespace) -> None:
  objName = args.object
  configFileName = args.configFileName

  if objName == "config":
    printConfigFile(configFileName)
  elif objName == "init":
    # print(build.genInitFile(2, 2))
    # print(build.genInitFileBottle(2, 2))
    pass
  else:
    raise ValueError(f"Unknown object to print: {objName}")


def printConfigFile(configFileName: FileNameT) -> None:
  """Prints parsed config file to the output."""
  conf = config.readYamlConfig(configFileName)
  print("ConfigFileData: Original:")
  print(conf.data)

  print("#" * 64)
  conf = config.UserConfig(conf.data)
  print("ConfigFileData: Processed:")
  print(conf)


def buildProject(args: argparse.Namespace) -> None:
  """Builds the project for Ajit Processor/CoRTOS.
  It creates a configuration object and starts the build process
  which uses the object.
  """
  target = targets.by_name(args.target)
  ramstart = args.ramstart if args.ramstart is not None else target.default_ram_start
  configFileName = args.configFileName
  confObj = config.readYamlConfig(configFileName, ramstart, target)
  confObj.addDebugSupport(args.debug, args.port)
  confObj.addOptLevel(args.O0, args.O1, args.O2)
  build.buildProject(confObj)


def runProject(args: argparse.Namespace) -> None:
  """Run a built project (qemu-ajit today)."""
  target = targets.by_name(args.target)
  if target.name != targets.QEMU.name:
    print("CoRTOS: ERROR: cortos run currently supports --target qemu only."
          " Use ./run.sh for the C-model.")
    raise SystemExit(1)
  qemu.run_qemu(os.getcwd(), timeout_sec=args.timeout)


def getParser() -> argparse.ArgumentParser:
  # process the command line arguments
  parser = argparse.ArgumentParser(description="CoRTOS")
  subParser = parser.add_subparsers(title="subcommands", dest="subcommand",
                                    help="use ... <subcommand> -h     for more help")
  subParser.required = True

  # subcommand: build
  subpar = subParser.add_parser("build", help="Build a project.")
  subpar.set_defaults(func=buildProject)
  # subpar.add_argument('-l', '--logging', action='count', default=0)
  subpar.add_argument('-g', '--debug', action='store_true', default=False,
                      help="Enable debug build. If enabled, optimization level is set to 0.")
  subpar.add_argument('-p', '--port', type=int, default=8888,
                      help="Starting debug server port sequence.")
  subpar.add_argument('-O0', '--O0', action='store_true', default=False,
                      help="Optimization level 0 (O0).")
  subpar.add_argument('-O1', '--O1', action='store_true', default=False,
                      help="Optimization level 1 (O1).")
  subpar.add_argument('-O2', '--O2', action='store_true', default=False,
                      help="Optimization level 2 (O2).")
  subpar.add_argument(
      '--target',
      choices=sorted(targets.BY_NAME.keys()),
      default=targets.CMODEL.name,
      help="cmodel (default) or qemu.")
  subpar.add_argument('-s', '--ramstart', type=lambda x: int(x, 0), default=None,
                      help="Starting RAM address. C-model: 16MB aligned, default 0x0."
                           " qemu: default 0x00100000, not 16MB-aligned.")
  subpar.add_argument("configFileName",
                      nargs="?",
                      default=consts.CONFIG_FILE_DEFAULT_NAME,
                      help=f"{consts.CONFIG_FILE_DEFAULT_NAME} file path.")

  # subcommand: run
  subpar = subParser.add_parser("run", help="Run a built project.")
  subpar.set_defaults(func=runProject)
  subpar.add_argument(
      '--target',
      choices=sorted(targets.BY_NAME.keys()),
      default=targets.QEMU.name,
      help="qemu (default). C-model still uses ./run.sh.")
  subpar.add_argument('--timeout', type=int, default=qemu.DEFAULT_TIMEOUT_SEC,
                      help="Wall seconds before killing qemu.")

  # subcommand: print
  subpar = subParser.add_parser("show", help="Show a specific detail")
  subpar.set_defaults(func=printDetail)
  # subpar.add_argument('-l', '--logging', action='count', default=0)
  subpar.add_argument("object",
                      choices=["config", "init", "header"],
                      help="Object to print.")
  subpar.add_argument("configFileName",
                      nargs="?",
                      default=consts.CONFIG_FILE_DEFAULT_NAME,
                      help="Config file path.")

  return parser
