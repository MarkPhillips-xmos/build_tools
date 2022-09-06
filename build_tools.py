#!/usr/bin/env python2

import argparse
import collections
import glob
import os
import os.path
import platform
import shutil
import subprocess
import sys

BUILD_HOST=None
DEST_HOST=None

#
# The following is used to map names used in the Jenkinsfile to repo names
# and to indicate that there is no repo hierarchy (i.e. flat_structure)
# This is used to build the directory naming and structure locally
# identically to how Jenkins will do so
#
container_info = {
  "xmap"       : {"domain" : "tools_xmap",     "flat_structure" : True },
  "xcc_driver" : {"domain" : "tools_xcc",      "flat_structure" : True },
  "ar"         : {"domain" : "tools_ar",       "flat_structure" : True },
  "xas"        : {"domain" : "tools_xas",      "flat_structure" : True },
  "xobjdump"   : {"domain" : "tools_xobjdump", "flat_structure" : True },
  "xscope"     : {"domain" : "tools_xtrace",   "flat_structure" : True },
  "tools_xpp"  : {"domain" : "tools_xpp",      "flat_structure" : True },
  "tools_xcore_libs"     : {"domain" : "tools_xcore_libs",   "flat_structure" : True },
}

#
# The following specifies the tarballs created and exported by each container repo
#
container_exports = {
  # Container              # List of exports
  "tools_common"         : ("Linux64_tools_common_Installs.tgz", "Linux64_tools_common_private.tgz"),
  "ar"                   : ("Linux64_ar_Installs.tgz",),
  "tools_xpp"            : ("Linux64_tools_xpp_Installs.tgz",),
  "xc_compiler_combined" : ("Linux64_xc_compiler_combined_Installs.tgz", "Linux64_xc_compiler_combined_private.tgz"),
  "xas"                  : ("Linux64_xas_Installs.tgz",),
  "xobjdump"             : ("Linux64_xobjdump_Installs.tgz",),
  "tools_libs_combined"  : ("Linux64_tools_libs_combined_Installs.tgz",),
  "xmap"                 : ("Linux64_xmap_Installs.tgz",),
  "xflash"               : ("Linux64_xflash_Installs.tgz",),
  "xgdb_combined"        : ("Linux64_xgdb_combined_Installs.tgz",),
  "xcc_driver"           : ("Linux64_xcc_driver_Installs.tgz",),
  "xsim_combined"        : ("Linux64_xsim_combined_Installs.tgz", "Linux64_xsim_combined_private.tgz"),
  "tools_axe_combined"   : ("Linux64_tools_axe_combined_Installs.tgz", "Linux64_tools_axe_combined_private.tgz"),
  "xcommon"              : ("Linux64_xcommon.tgz",),
  "xscope"               : ("Linux64_xscope_Installs.tgz", "Linux64_xscope_private.tgz"),
  "tools_xcore_libs"     : ("Linux64_tools_xcore_libs_Installs.tgz", "Linux64_tools_xcore_libs_private.tgz"),
}

# Each container must specify which containers it is dependent
# If these are not provided fully problems occur where a items from a repo
# mid-way up the tree are exported from cloned Jenkins build and
# not from the local build of a that container (with modifications) as needed
#
# The ordering of the containers ino the "ordered dict" below must be "correct" 
# in terms of the container build hierarchy
#
my_containers = collections.OrderedDict([
  # Container               # List of dependent containers which have been edited and built
  ("xcommon"              , ()),
  ("tools_common"         , ()),
  ("ar"                   , ()),
  ("tools_xpp"            , ()),
  ("xc_compiler_combined" , ("tools_common",)),
  ("xas"                  , ("tools_common",)),
  ("xmap"                 , ("tools_common",)),
  ("xobjdump"             , ("tools_common",)),
  ("xcc_driver"           , ("tools_common",)),
  ("xsim_combined"        , ("tools_common", "tools_xpp", "xas", "xc_compiler_combined", "xmap")),
  ("tools_axe_combined"   , ()),
  ("xgdb_combined"        , ("xsim_combined", "tools_common",)),
  ("tools_libs_combined"  , ("tools_common", "ar", "xas", "xmap", "xcc_driver", "xc_compiler_combined", "tools_xpp", "xobjdump", "xsim_combined", )),
  ("xscope"               , ("xcommon", "tools_common", "ar", "xas", "tools_xpp", "xcc_driver", "xc_compiler_combined", "tools_libs_combined")),
  ("tools_xcore_libs"     , ("xcommon", "tools_common", "ar", "xas", "xmap", "xcc_driver", "xc_compiler_combined", "tools_xpp", "xobjdump", "xsim_combined", "tools_libs_combined")),
  ("xflash"               , ("xcommon", "tools_common", "xsim_combined", "xobjdump", "ar", "xas", "xcc_driver", "xmap", "xc_compiler_combined", "tools_xpp", "tools_libs_combined", "tools_xcore_libs", "xscope", "xgdb_combined")),
  ("tools_installers"     , ("xcommon", "tools_common", "xsim_combined", "xflash", "xobjdump", "ar", "xas", "xcc_driver", "xmap", "xc_compiler_combined", "tools_xpp", "tools_libs_combined", "tools_xcore_libs", "xscope", "xgdb_combined")),
])

ignoreDomains = ["lib_xmlobject_py"]

def ParseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument('--clone',      default=False, action='store_true', help='Create a new working area')
    parser.add_argument('--debugbuild', default=False, action='store_true', help='Build with debug (CONFIG=Debug)')
    parser.add_argument('--debug',      default=False, action='store_true', help='Enable debug prints')
    parser.add_argument('--dryrun',     default=False, action='store_true', help='Do not execute commands')
    parser.add_argument('--git',                                            help='Run git command on each repo')
    parser.add_argument('--mkroot',     default=False, action='store_true', help='Make a new working area root')
    parser.add_argument('--update',     default=False, action='store_true', help='Use with --clone to update a new working area with latest Jenkins tarballs')
    parser.add_argument('containers',   default=None,  nargs="*")

    args = parser.parse_args()
    return args


def Cmd(cmd, useShell=False):
    print( "Running cmd: ", cmd)
    if args.dryrun:
        return

    if useShell:
        cmdsplit = cmd
    else:    
        cmdsplit = cmd.split()

    handle = subprocess.Popen(cmdsplit, shell=useShell)

    r = handle.wait()
    if 0 != r:
        raise Exception("Error %s, failed cmd: %s" % (r, cmdsplit))


def Build(container, domains, deps, debugbuild):
    print "Build(container, deps):", container, deps

    # Iterate of the locally built dependency container and unpack the their tarballs
    for d in deps:
        glist = container_exports[d]

        print "Build: d, glist", d, glist

        os.chdir(container)
        for g in glist:
            print "g", g

            if -1 == d.find("xcommon"):
                cmd = "tar -xf ../%s/%s" % (d, g,)
            else:
                # Special case for xcommon
                installPath = "Installs/%s/External/Product" % (DEST_HOST,)
                if not os.path.isdir(installPath):
                    Cmd("mkdir -p %s" % (installPath,))
                cmd = "tar -C %s -xf ../%s/%s" % (installPath, d, g,)

            print("Expanding: ", cmd)
            Cmd(cmd)

        os.chdir("..")

    
    if "" == domains:
        # No domains specified by the user

        if "xsim_combined" == container:
            # Hack for xsim_combined because it has arch_roms which will not build
            domains = "arch_simulation_cpp,tools_tools_cpp,lib_softfloat,apps_plugins_cpp"
        elif "xcommon" == container:
            # xcommon - only build certain dommains as per Jenkinsfile
            domains = "tools_xmake,xcommon,tools_waf_xcc"
        elif "tools_xcore_libs" == container:
            # tools_xcore_libs - only build certain dommains as per Jenkinsfile
            domains = "tools_xcore_libs"
        elif "tools_installers" == container:
            domains = "infr_test,lib_logging_py,lib_subprocess_py,tools_installers,tools_licensing,tools_xdwarfdump_c,tools_xmosupdate,verif_tests_sw,verif_tests_xcore"
        else:
            # Find the list of domains to build - any subdir with a Build.pl file is selected
            os.chdir(container)
            glist = glob.glob("*/Build.pl")
            os.chdir("..")

            print "glist: ", glist

            for g in glist:
                d = os.path.dirname(g)
                if d in ignoreDomains:
                    continue
                domains += d + ","

    if debugbuild:
       config = "Debug"
    else:
       config = "Release"

    #    cmd = "bash -c 'cd %s/infr_scripts_pl/Build && ls -l SetupEnv && source ./SetupEnv && cd ../.. && Build.pl DOMAINS=%s CONFIG=%s'" % (container, domains, config)
    ## DEBUG Build
    ##    cmd = "bash -c 'cd %s/infr_scripts_pl/Build && ls -l SetupEnv && source ./SetupEnv && cd ../.. && Build.pl DOMAINS=%s CONFIG=Debug'" % (container, domains)
    ## RELEASE Build

    # TODO FAILS "source ./SetupEnv" on msys2
    #    cmd = "bash -c 'which bash && cd %s/infr_scripts_pl/Build && ls -l && ls -l SetupEnv && source ./SetupEnv && cd ../.. && Build.pl DOMAINS=%s CONFIG=Release'" % (container, domains)

    if "Linux" == BUILD_HOST:
        with open("build.sh", "w") as f:
            f.write("#!/usr/bin/bash\n")
            f.write("cd %s/infr_scripts_pl/Build\n" % (container,))
            f.write("source ./SetupEnv\n")
            f.write("cd ../..\n")
            f.write("Build.pl DOMAINS=%s CONFIG=%s\n" % (domains, config))

        cmd = "bash build.sh"
        print "cmd: ", cmd
        Cmd(cmd, True)
    else:
        with open("build.bat", "w") as f:
            f.write("cd %s/infr_scripts_pl/Build\n" % (container,))
            f.write("call SetupEnv.bat\n")
            f.write("set PATH=%PATH%;c:\\strawberry\\perl\\bin\n")
            f.write("set VCTargetsPath=c:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Microsoft\\VC\\v170\n")
            f.write("perl Build.pl DOMAINS=%s CONFIG=%s\n" % (domains, config))
        cmd = "cmd /c build.bat"
        print "cmd: ", cmd
        Cmd(cmd, True)

    ## Create the tarballs for installation - find the Upload sh commands
    os.chdir(container)
    with open("Jenkinsfile") as f:
        lines = f.readlines()

    for i in range(len(lines)):
        l = lines[i]
        if -1 != l.find('stage("Upload")'):
            j = i+1
            # j now has skipped the steps { line
            while j < len(lines):
                # Find a command like: '       sh """tar -czf Linux64_xmap_Installs.tgz Installs tools_xmap/test"""'
                if -1 != lines[j].find("sh ") and -1 != lines[j].find("Linux64"):
                    if -1 != lines[j].find("Linux64_xcommon"):
                        # Special case for xcommon
                        cmd = 'tar -C Installs/%s/External/Product -czf Linux64_xcommon.tgz .' % (DEST_HOST,)
                        Cmd(cmd, True)
                    elif -1 == lines[j].find("Linux64_xTIMEdeployer"):
                        # Ignore nasties like xflash Linux64_xTIMEdeployer
                        cmd = lines[j].replace("sh ", "").strip().strip('"')

                        if debugbuild:
                            # for xc_compiler_combined:tools_xcc1_c_llvm
                            cmd = cmd.replace("/Release/", "/Debug/")
                        print "cmd:", cmd
                        Cmd(cmd, True)
                j += 1
            break

    os.chdir("..")


def Unpack(container, updateOnly):
    base = "http://srv-bri-jtools:8080%s/lastSuccessfulBuild/artifact/%s"
    flat = False
    tools_dir = container

    if not updateOnly:
        # Do a full clone

        c_info = container_info.get(container)
        if c_info:
            domain = c_info.get("domain")
            if domain:
                tools_dir = domain

            flat = c_info.get("flat_structure")

            if flat:
               os.mkdir(container)
               os.chdir(container)

        path = "git@github0.xmos.com:xmos-int/%s %s" % (container, tools_dir)
        Cmd("git clone --recurse-submodules %s" % (path,))

        if flat:
#           os.chdir("..")
           # Create for the Build fn which needs to extract the "upload entries"
           if platform.platform().find("Windows") != -1:
               shutil.copy(tools_dir + "/Jenkinsfile", "Jenkinsfile")
           else:
               os.symlink(tools_dir + "/Jenkinsfile", "Jenkinsfile")
           os.chdir("..")

    print("cwd: %s, tools_dir %s\n" % (os.getcwd(), tools_dir))

    os.chdir(container)
    with open("Jenkinsfile") as f:
        lines = f.readlines()

    for l in lines:
        if -1 != l.find("copyArtifacts"):
            parts = l.split()

            print "l:", l, " parts:", parts

            for i in range(len(parts)):
                if parts[i] == "filter:":
                    filter = parts[i+1].strip("',")
                if parts[i] == "projectName:":
                    projectName = parts[i+1].strip("',")

            if -1 == filter.find("Linux64"):
                continue

            tarballs = []
            if -1 == filter.find("*"):
                tarballs.append(filter)
            else:
                # Hack - a * at the end of the tarball name implies Installs and private
                f = filter.replace("*", "Installs")
                tarballs.append(f)
                f = filter.replace("*", "private")
                tarballs.append(f)

            for t in tarballs:
                project_parts = projectName.split("/")

                subpath = ""
                for p in project_parts:
                    subpath += "/job/%s" % (p,)

                path = base % (subpath, t)

                # Move the extsing tarball to a .1 backup otherwise wget will create the new one as <fname>.1
                if os.path.exists(t):
                    Cmd("mv %s %s.1" % (t, t,))

                Cmd("wget %s" % (path,))

                if "Linux64_xcommon.tgz" == t:
                    Cmd("sh -c 'mkdir -p Installs/Linux/External/Product && tar -x -C Installs/Linux/External/Product -f Linux64_xcommon.tgz'", True)
                elif "Linux64_xclang_Installs.tar.gz" == t:
                    Cmd("sh -c 'tar -C Installs/Linux/External/Product -xzf Linux64_xclang_Installs.tar.gz --strip-components=2'", True)
                else:
                    Cmd("sh -c 'tar -xf %s'" % (t,), True)

                # Remove the backup .1 file
                if os.path.exists("%s.1" % (t,)):
                    Cmd("rm %s.1" % (t,))

    os.chdir("..")

    if not os.path.exists("%s/infr_scripts_pl" % (container,)):
        Cmd("cd %s && git clone git@github.com:xmos/infr_scripts_pl" % (container,), True)

    # Hack for xmap
    if not os.path.exists("%s/tools_bin2header" % (container,)):
        Cmd("cd %s && git clone git@github.com:xmos/bin2header tools_bin2header" % (container,), True)

def Git(container, cmd):
    os.chdir(container)
    if os.path.exists(".git"):
        Cmd("git status")
        Cmd("git submodule foreach git status")
    elif container_info[container]["flat_structure"]:
        os.chdir(container_info[container]["domain"])
        Cmd("git status")
        os.chdir("..")
    os.chdir("..")

import platform
if platform.system() != "Windows" or os.environ.get('MSYSTEM') != None:
    # Building On Linux (for Linux) or on MINGW for PC
    BUILD_HOST = "Linux"
else:
    BUILD_HOST = "PC"


if os.environ.get('SYSTEMDRIVE'):
    # Building on Windows (for Windows) or on MINGW64 for Windows
    DEST_HOST = "PC"
else:
    DEST_HOST = "Linux"

args = ParseArgs()


if args.clone and args.mkroot: 
    os.mkdir("working")

os.chdir("working")

containers_todo = []

for c in my_containers:
    if 0 == len(args.containers):
        containers_todo.append(c)
    else:
        for arg in args.containers: 
            repo = arg.split(":")[0]
            if c == repo:
                containers_todo.append(arg)

if 0 == len(containers_todo):
    print("Invalid container(s) specified")
    sys.exit(1)


for c in containers_todo:
    if args.clone:
        Unpack(c, args.update)
    elif args.git:
        Git(c, args.git)
    else:
        parts = c.split(":")
        repo = parts[0]
        if len(parts) > 1:
            domains = parts[1]
        else:
            domains = ""

        deps = my_containers[repo]

        Build(repo, domains, deps, args.debugbuild)

#
# Example commands
#
#  # Make a new "working" subdir and clone the tools_common container repo
#  python ~/bin/build_tools.py --mkroot --clone  tools_common 
#
#  # Update the tools_common container repo to pick up rebuilt Jenkins components (e.g. xc_compiler_combined)
#  python ~/bin/build_tools.py --clone --update tools_common 
#
#  python ~/bin/build_tools.py tools_common 
#  python ~/bin/build_tools.py tools_common tools_installers
#  python ~/bin/build_tools.py tools_common:infr_libs_cpp,lib_xmosutils,arch_dbs_xml,tools_configs tools_installers:tools_installers
#  python ~/bin/build_tools.py tools_installers:tools_installers
#
#  # Build a subset of repos within container repos
#  python ~/bin/build_tools.py tools_common:infr_libs_cpp xmap xgdb_combined xflash:tools_xflash tools_installers:tools_installers

# Build all
# ./build_tools.py xcommon tools_common ar tools_xpp xc_compiler_combined xas xmap xobjdump xsim_combined xgdb_combined xcc_driver tools_libs_combined xscope tools_xcore_libs xflash tools_installers