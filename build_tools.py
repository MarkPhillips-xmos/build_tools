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
container_mapping_info = {
  "xmap"             : {"domain" : "tools_xmap",       "flat_structure" : True },
  "xcc_driver"       : {"domain" : "tools_xcc",        "flat_structure" : True },
  "ar"               : {"domain" : "tools_ar",         "flat_structure" : True },
  "xas"              : {"domain" : "tools_xas",        "flat_structure" : True },
  "xobjdump"         : {"domain" : "tools_xobjdump",   "flat_structure" : True },
  "xscope"           : {"domain" : "tools_xtrace",     "flat_structure" : True },
  "tools_xpp"        : {"domain" : "tools_xpp",        "flat_structure" : True },
  "tools_xcore_libs" : {"domain" : "tools_xcore_libs", "flat_structure" : True },
}

#
# The following specifies the tarballs created and exported by each container repo
#
container_exports = {
  # Container              # List of exports
  "tools_common"         : ("%s_tools_common_Installs.%s", "%s_tools_common_private.%s"),
  "ar"                   : ("%s_ar_Installs.%s",),
  "tools_xpp"            : ("%s_tools_xpp_Installs.%s",),
  "xc_compiler_combined" : ("%s_xc_compiler_combined_Installs.%s", "%s_xc_compiler_combined_private.%s"),
  "xas"                  : ("%s_xas_Installs.%s",),
  "xobjdump"             : ("%s_xobjdump_Installs.%s",),
  "tools_libs_combined"  : ("%s_tools_libs_combined_Installs.%s",),
  "xmap"                 : ("%s_xmap_Installs.%s",),
  "xflash"               : ("%s_xflash_Installs.%s",),
  "xgdb_combined"        : ("%s_xgdb_combined_Installs.%s",),
  "xcc_driver"           : ("%s_xcc_driver_Installs.%s",),
  "xsim_combined"        : ("%s_xsim_combined_Installs.%s", "%s_xsim_combined_private.%s"),
  "tools_axe_combined"   : ("%s_tools_axe_combined_Installs.%s", "%s_tools_axe_combined_private.%s"),
  "xcommon"              : ("%s_xcommon.%s",),
  "xscope"               : ("%s_xscope_Installs.%s", "%s_xscope_private.%s"),
  "tools_xcore_libs"     : ("%s_tools_xcore_libs_Installs.%s", "%s_tools_xcore_libs_private.%s"),
}

# Each container must specify which containers it is dependent
# If these are not provided fully problems occur where a items from a repo
# mid-way up the tree are exported from cloned Jenkins build and
# not from the local build of a that container (with modifications) as needed
#
# The ordering of the containers ino the "ordered dict" below must be "correct" 
# in terms of the container build hierarchy
#
all_containers = collections.OrderedDict([
  # Container               # List of dependent containers which have been edited and built
  ("infr_test"            , ()),
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
  ("tools_libs_combined"  , ("xcommon", "tools_common", "ar", "xas", "xmap", "xcc_driver", "xc_compiler_combined", "tools_xpp", "xobjdump", "xsim_combined")),
  ("xscope"               , ("xcommon", "tools_common", "ar", "xas", "tools_xpp", "xcc_driver", "xc_compiler_combined", "tools_libs_combined")),
  ("tools_xcore_libs"     , ("xcommon", "tools_common", "ar", "xas", "xmap", "xcc_driver", "xc_compiler_combined", "tools_xpp", "xobjdump", "xsim_combined", "tools_libs_combined")),
  ("xflash"               , ("xcommon", "tools_common", "xsim_combined", "xobjdump", "ar", "xas", "xcc_driver", "xmap", "xc_compiler_combined", "tools_xpp", "tools_libs_combined", "tools_xcore_libs", "xscope", "xgdb_combined")),
  ("tools_installers"     , ("xcommon", "tools_common", "xsim_combined", "xflash", "xobjdump", "ar", "xas", "xcc_driver", "xmap", "xc_compiler_combined", "tools_xpp", "tools_libs_combined", "tools_xcore_libs", "xscope", "xgdb_combined")),
])

build_domains = {
   "xcommon"             : "tools_xmake,xcommon,tools_waf_xcc",
   "xsim_combined"       : "arch_simulation_cpp,tools_tools_cpp,lib_softfloat,apps_plugins_cpp",
   "tools_xcore_libs"    : "tools_xcore_libs",
   "tools_libs_combined" : "arch_roms,tools_libs,tools_llvm_lib,tools_newlib,lib_xcore",
   "xscope"              : "tools_xtrace",
   "tools_installers"    : "infr_test,lib_logging_py,lib_subprocess_py,tools_installers,tools_licensing,tools_xdwarfdump_c,tools_xmosupdate,verif_tests_sw,verif_tests_xcore",
}

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
    parser.add_argument('--reimport',   default=False, action='store_true', help='Re-reimport depndendencies build by parent containsers')
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


def Build(container, domains, deps, debugbuild, reimport):
    print "Build(container %s, deps %s, debugbuild %s, reimport %s)" % (container, deps, debugbuild, reimport)

    if "PC" == DEST_HOST:
        hostPrefix = "Microsoft"
        hostPostfix = "tgz"
    else:
        hostPrefix = "Linux64"
        hostPostfix = "tgz"

    # Remove any temporary import/export dirs
    for i in ("Installs_imports", "Installs_exports"):
        try:
            shutil.rmtree(container +"/" + i, True)
        except WindowsError, e:
            print "Failed shutil.rmtree(%s/%s) : %s" % (container, i, e)
            pass

    # Iterate of the locally built dependency container and unpack the their tarballs
    for d in deps:
        import_list = container_exports[d]

        print "Build: depndendency %s, import list %s" % (d, import_list)

        os.chdir(container)
        for g in import_list:
            print "g", g

            fileName = g % (hostPrefix, hostPostfix)

            if -1 == d.find("xcommon"):
                cmd = "tar -xf ../exports/%s" % (fileName,)
            else:
                # Special case for xcommon
                installPath = "Installs/%s/External/Product" % (DEST_HOST,)
                if not os.path.isdir(installPath):
                    Cmd("mkdir -p %s" % (installPath,))
                cmd = "tar -C %s -xf ../exports/%s" % (installPath, fileName)

            print("Expanding import tarball: ", cmd)
            Cmd(cmd)

        os.chdir("..")

    # The above steps have pulled in the stuff built and exported by parent containers
    if reimport:
        return

    if "" == domains:
        # No domains specified by the user

        if build_domains.has_key(container):
            domains = build_domains[container]
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
            if os.environ.get('MSYSTEM'):
                f.write("export PATH=$PATH:/apache-ant-1.10.12/bin")
                f.write("export JAVA_HOME=/jdk-18.0.2.1")
            f.write("cd ../..\n")
            f.write("Build.pl DOMAINS=%s CONFIG=%s\n" % (domains, config))

        cmd = "bash build.sh"
    else:
        with open("build.bat", "w") as f:
            f.write("cd %s/infr_scripts_pl/Build\n" % (container,))
            f.write("call SetupEnv.bat\n")
#            f.write("set PATH=%PATH%;c:\\msys64\\usr\\bin\n")    # For BISON
            f.write("set PATH=%PATH%;c:\\strawberry\\perl\\bin\n")
            f.write("set PATH=%PATH%;c:\\msys64\\apache-ant-1.10.12\\bin\n")
            f.write("set JAVA_HOME=C:\\Program Files\\Eclipse Adoptium\\jdk-17.0.4.101-hotspot\n")
            f.write("perl Build.pl DOMAINS=%s CONFIG=%s\n" % (domains, config))
        cmd = "cmd /c build.bat"
    print "cmd: ", cmd
    Cmd(cmd, True)

    ## Create the tarballs for installation - find the Upload sh commands
    os.chdir(container)

    # Find only the files this container build has produced in Installs
    if os.path.isdir("Installs_imports"):
        # We have imported build artefacts from parent container builds
        os.mkdir("Installs_exports")
        if "Windows" == platform.system():
            pathsep = "\\"
        else:
            pathsep = "/"
        for dirpath, dnames, fnames in os.walk("Installs"):
            for f in fnames:
                # Does the file exist in the set of imports?
                testPath = dirpath.replace("Installs", "Installs_imports") + pathsep + f
                testPath.replace("\\", "/")

                if not os.path.exists(testPath):
                    # The file is not in the set of imports - copy it to the exports
                    newPath = dirpath.replace("Installs", "Installs_exports")
                    dirlist = newPath.split(pathsep)

                    # This loop creates the dest dir
                    p = ""
                    for d in dirlist:
                        p += d
                        try:
                            os.mkdir(p)
                        except WindowsError, e:
                            pass
                        p += pathsep

                    # And finally copy the file to the dest dir
                    shutil.copy(dirpath + pathsep + f, newPath)

    elif os.path.isdir("Installs"):
        # We did not import anything - we are a "leaf"
        shutil.copytree("Installs", "Installs_exports")

    os.rename("Installs", "Installs_working")
    os.rename("Installs_exports", "Installs")

    with open("Jenkinsfile") as f:
        lines = f.readlines()

    current_state = "init"
    if "PC" == DEST_HOST:
        searching = '("Windows")'
    else:
        searching = '("Centos")'

    for i in range(len(lines)):
        l = lines[i]

        if "init" == current_state and -1 != l.find(searching):
            current_state = "host"
            continue

        if "host" == current_state and -1 != l.find('stage("Upload")'):
            current_state = "upload"
            continue

        if "upload" == current_state:
            if "PC" == DEST_HOST and -1 != lines[i].find("bat ") and -1 != lines[i].find("Microsoft"):
                current_state = "found_pc"
            elif -1 != lines[i].find("sh ") and -1 != lines[i].find("Linux64"):
                current_state = "found_linux"
            # fall through - do not continue

        if "found_pc" == current_state:
            if -1 != lines[i].find("Microsoft_xcommon"):
                # Special case for xcommon due to the root of the tar/zip being down in Installs/%s/External/Product
                cmd = 'tar -C Installs/%s/External/Product -czf ../exports/Microsoft_xcommon.zip .' % (DEST_HOST,)
                Cmd(cmd, True)
            elif -1 == lines[i].find("Microsoft_xTIMEdeployer") and -1 == lines[i].find("archiveArtifacts"):
                # Ignore nasties like xflash Microsoft_xTIMEdeployer

                # Remove Jenkins "bat" and all double quotes
                cmd = lines[i].replace("bat ", "").strip().strip('"')

                # Change zip... to tar czf
                cmd = cmd.replace("zip -qr", "tar czf ").strip().strip('"')

# TODO                if -1 == cmd.find(".tgz"):
#                    raise Exception("Jenkinfile does not use .tgz: cmd %s" % (cmd,))

                parts = cmd.split()
                cmd = ""
                for part in parts:
                    if -1 != part.find(".tgz"):
                        # Prefix with the destination dir for the tarball
                        cmd += "../exports/" + part + " "
#                    elif -1 != part.find("*"):
#                        # Need to do the glob done by "zip" in the Jenkinsfile
#                        paths = glob.glob(part)
#                        for p in paths:
#                            cmd += p + " "
                    else:
                        cmd += part + " "
                cmd = cmd.strip()

                if debugbuild:
                    # for xc_compiler_combined:tools_xcc1_c_llvm
                    cmd = cmd.replace("\\Release\\", "\\Debug\\")

                if 0 == cmd.find("tar"):
                    print "cmd:", cmd
                    Cmd(cmd, True)

        elif "found_linux" == current_state:
            if -1 != lines[i].find("Linux64_xcommon") and -1 == lines[i].find("archiveArtifacts"):
                # Special case for xcommon
                cmd = 'tar -C Installs/%s/External/Product -czf ../exports/Linux64_xcommon.tgz .' % (DEST_HOST,)
                Cmd(cmd, True)
            elif -1 == lines[i].find("Linux64_xTIMEdeployer"):
                # Ignore nasties like xflash Linux64_xTIMEdeployer
                cmd = lines[i].replace("sh ", "").strip().strip('"')

# TODO               if -1 == cmd.find(".tgz"):
#                    raise Exception("Jenkinfile does not have .tgz: cmd %s" % (cmd,))

                parts = cmd.split()
                cmd = ""
                for part in parts:
                    if -1 != part.find(".tgz"):
                        # Prefix with the destination dir for the tarball
                        cmd += "../exports/" + part + " "
#                    elif -1 != part.find("*"):
#                        # Need to do the glob done by "zip" in the Jenkinsfile
#                        paths = glob.glob(part)
#                        for p in paths:
#                            cmd += p + " "
                    else:
                        cmd += part + " "
                cmd = cmd.strip()

                if debugbuild:
                    # for xc_compiler_combined:tools_xcc1_c_llvm
                    cmd = cmd.replace("/Release/", "/Debug/")

                if 0 == cmd.find("tar"):
                    print "cmd:", cmd
                    Cmd(cmd, True)

        if ("found_pc" == current_state or "found_linux" == current_state) and -1 != lines[i].strip().find("}"):
            # Done all upload commands
            current_state = "done"
            break

    os.rename("Installs", "Installs_exports")
    os.rename("Installs_working", "Installs")
 
    os.chdir("..")


def Unpack(container, updateOnly):
    base = "http://srv-bri-jtools:8080%s/lastSuccessfulBuild/artifact/%s"
    flat = False
    tools_dir = container

    if not updateOnly:
        # Do a full clone

        c_info = container_mapping_info.get(container)
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
    elif container_mapping_info[container]["flat_structure"]:
        os.chdir(container_mapping_info[container]["domain"])
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
    os.mkdir("working/exports")

os.chdir("working")

containers_todo = []

for c in all_containers:
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

        deps = all_containers[repo]

        Build(repo, domains, deps, args.debugbuild, args.reimport)

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
# ./build_tools.py xcommon tools_common ar tools_xpp xc_compiler_combined xas xmap xobjdump xsim_combined xgdb_combined xcc_driver tools_libs_combined \
#                  xscope tools_xcore_libs xflash tools_installers