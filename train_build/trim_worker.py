#!/usr/bin/env python3

import argparse
import shutil
import trim_action
import tempfile


def parse_args(argv):
  parser = argparse.ArgumentParser(description='Trim a module')
  parser.add_argument(
      '-n', '--name', help='package_name')
  parser.add_argument(
      '-m', '--module', help='module bundle to trim')
  parser.add_argument(
      '-d', '--dcla_dir', help='expanded dcla dir')
  parser.add_argument(
      '-t', '--apex_tools_path', help='apex tools path')
  return parser.parse_args(argv)


def main(argv):
  args = parse_args(argv)

  # create spec
  spec = trim_action.TrimSpec(args.name,
                              args.module,
                              args.dcla_dir)

  # create trim action and execute
  action = trim_action.TrimAction(spec, args.apex_tools_path)
  action.execute()

  print(spec.trimmed_artifacts_dir)

if __name__ == "__main__":
  main(sys.argv[1:])
