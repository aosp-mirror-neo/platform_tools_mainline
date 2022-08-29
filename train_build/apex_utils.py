#!/usr/bin/env python3

from glob import glob
import os
import shutil
import subprocess
import zipfile


def run_command(parts: list[any]) -> None:
  """Construct a command line from parts and run it."""
  cmd = []
  for p in parts:
    if not p:
      continue
    if isinstance(p, tuple):
      cmd.append('{}={}'.format(*p))
    else:
      cmd.append(str(p))
  try:
    res = subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        stderr=subprocess.PIPE)
  except subprocess.CalledProcessError as err:
    print(err.stderr)
    print(err.output)
    raise err


def expand_bundle(apex_tools_path: str, aab: str, aab_dir: str) -> None:
  """Expand an aab into the designated directory."""
  with zipfile.ZipFile(aab, 'r') as aab_zip:
    aab_zip.extractall(aab_dir)

  # expand all payload images
  img_dir = os.path.join(aab_dir, 'base/apex')
  for img_file in glob(os.path.join(img_dir, '*.img')):
    arch_name = os.path.splitext(os.path.basename(img_file))[0]
    extract_dir = os.path.join(img_dir, arch_name)
    os.mkdir(extract_dir)
    debugfs = str(os.path.join(apex_tools_path, 'debugfs_static'))
    run_command([debugfs, img_file, '-R', f'rdump / {extract_dir}'])


def create_apex(apex_tools_path: str, android_jar: str, package_name: str,
                apex_manifest: str, build_info: str, artifacts_dir: str,
                fs_type: str, img_key: str, container_key: str,
                output_apex: str) -> None:
  """Create an apex using apexer."""
  apexer_binary = os.path.join(apex_tools_path, 'apexer')
  run_command([
      apexer_binary,
      '--include_build_info',
      ('--build_info', build_info),
      ('--manifest', apex_manifest),
      ('--android_jar_path', android_jar),
      ('--apexer_tool_path', apex_tools_path),
      ('--payload_fs_type', fs_type),
      '--do_not_check_keyname',
      '--force',
      ('--key', img_key) if img_key else None,
      ('--pubkey', container_key) if container_key else None,
      '--verbose',
      artifacts_dir,
      output_apex
  ])


def create_bundle(bundle_tool_path: str, bundle_config: str,  base_dir: str,
                  output_aab: str) -> None:
  """Creates a bundle (.aab) file given the base directory."""
  zipped_file = shutil.make_archive(base_dir, 'zip', root_dir=base_dir)
  run_command([
      'java',
      '-jar',
      bundle_tool_path,
      'build-bundle',
      ('--modules', zipped_file),
      ('--output', output_aab),
      ('--config', bundle_config),
      '--overwrite',
  ])


def create_apks(bundle_tool_path: str, input_aab: str, key: str,
                output_apks: str) -> None:
  """Creates an apks file given the input bundle."""
  run_command([
      'java',
      '-jar',
      bundle_tool_path,
      'build-apks',
      ('--ks', key),
      ('--ks-pass', 'pass:android'),
      ('--ks-key-alias', 'AndroidDebugKey'),
      ('--bundle', input_aab),
      ('--output', output_apks),
      '--overwrite',
  ])
