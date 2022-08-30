#!/usr/bin/env python3

from glob import glob
import hashlib
import os
import re
import shutil
import tempfile

import apex_manifest_pb2
import apex_utils

# for DCLA, to be safe, all 64 bit only arch should go to mixed arch
# just in case one of the module arches is mixed
DCLA_ARCH_BY_MODULE_ARCH = {
    'x86_64' : 'x86_64.x86',
    'arm64-v8a' : 'arm64-v8a.armeabi-v7a',
    'x86' : 'x86',
    'armeabi-v7a' : 'armeabi-v7a',
    'x86_64.x86' : 'x86_64.x86',
    'arm64-v8a.armeabi-v7a' : 'arm64-v8a.armeabi-v7a'
}


class VersionCodeBumpError(Exception):
  """error while bumping module version code."""


class TrimSpec:
  """Specification for trim process.

  The overall functionality of the spec class is to provide a recipe for trim
  action class to execute. It should only contain: (1) input from the client
  which is all the info needed for action, (2) output of the action. Both
  input and output resources should be managed by whoever creates this spec
  (train build action class). Note, if a resource like a temp file or a time
  folder that is only needed for trim action scope should not be in spec,
  these temp resources should be owned and managed by trim action class.
  """

  def __init__(self, name: str, aab: str, dcla_dir: str):
    """Constructor.

    Args:
      name: module package name
      aab: bundled aab to be trimmed
      dcla_dir: the DCLA artifacts directory
    """

    # input resources
    self.package_name = name
    self.bundled_aab = aab
    self.dcla_dir = dcla_dir

    # output results
    self.trimmed_artifacts_dir = tempfile.mkdtemp()


class TrimAction:
  """Trim action to schedule and execute.

  This action class consumes a trim spec. The Execute method carries out the
  detailed trim action.
  """

  def __init__(self, spec: 'TrimSpec', apex_tools_path: str):
    """Constructor.

    Args:
      spec: a TrimSpec object
      apex_tools_path: where apex tooling binaries reside
    """
    self.spec = spec
    self.apex_tools_path = apex_tools_path
    self.libs_trimmed = set()

  def execute(self) -> None:
    """Execute trim action."""

    # STEP 1, expand aab
    apex_utils.expand_bundle(self.apex_tools_path,
                             self.spec.bundled_aab,
                             self.spec.trimmed_artifacts_dir)

    # STEP 3, trim each arch image extract
    img_dir = os.path.join(self.spec.trimmed_artifacts_dir, 'base/apex')
    for img_file in glob(os.path.join(img_dir, '*.img')):
      arch_name = os.path.splitext(os.path.basename(img_file))[0]
      extract_dir = os.path.join(img_dir, arch_name)
      if not os.path.isdir(extract_dir):
        raise NotADirectoryError(
            f'cannot find payload extract directory {extract_dir}')

      # trim artifacts for one arch
      self.trim_one_arch(extract_dir, DCLA_ARCH_BY_MODULE_ARCH.get(arch_name))

    # STEP 3, update bundle root apex manifest
    self.update_apex_manifest()

  def trim_one_arch(self, extract_dir: str, dcla_arch: str) -> None:
    """Trim current payload extract."""

    # search thru each lib dir
    for relative_lib_dir in ['lib', 'lib64']:
      lib_dir = os.path.join(extract_dir, relative_lib_dir)
      if not os.path.isdir(lib_dir):
        continue

      # check each lib
      for lib_file in glob(os.path.join(lib_dir, '*.so')):
        lib_digest, lib_size = self.get_file_digest_and_size(lib_file)
        lib_name = os.path.basename(lib_file)

        dcla_lib_file = os.path.join(self.spec.dcla_dir,
                                     'base/apex',
                                     dcla_arch,
                                     relative_lib_dir,
                                     lib_name,
                                     lib_digest,
                                     lib_name)

        if not os.path.isfile(dcla_lib_file):
          continue

        # record lib trimmed
        self.libs_trimmed.add(lib_name)

        # remove lib file
        os.remove(lib_file)

        # create symlink to
        # /apex/sharedlibs/lib(64)?/foo.so/[sha512 foo.so]/foo.so
        link_src = os.path.join('/apex/sharedlibs',
                                relative_lib_dir,
                                lib_name,
                                lib_digest,
                                lib_name)
        os.symlink(link_src, lib_file)

  def update_apex_manifest(self) -> None:
    """Update bundle root apex_manifest.pb."""
    root_apex_manifest = os.path.join(self.spec.trimmed_artifacts_dir,
                                      'base/root/apex_manifest.pb')
    if not os.path.isfile(root_apex_manifest):
      raise FileNotFoundError('no apex_manifest.pb in the expanded bundle')
    manifest_pb = apex_manifest_pb2.ApexManifest()
    with open(root_apex_manifest, 'rb') as f:
      manifest_pb.ParseFromString(f.read())

    # setting requireSharedApexLibs
    del manifest_pb.requireSharedApexLibs[:]
    manifest_pb.requireSharedApexLibs.extend(
        sorted(re.sub(r':.{128}$', ':sha-512', lib)
               for lib in self.libs_trimmed))

    # write back to root apex_manifest.pb
    with open(root_apex_manifest, 'wb') as f:
      f.write(manifest_pb.SerializeToString())

  @staticmethod
  def get_file_digest_and_size(file_path: str):
    """Get file sha512 hash and size."""
    hasher = hashlib.sha512()
    with open(file_path, 'rb') as f:
      data = f.read()
      hasher.update(data)
    return hasher.hexdigest(), len(data)
