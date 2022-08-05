# build_tools

This is a mechanism to build the XTC Tools outside of Jenkins, for example on a developer's local machine.

It allows users to pick up certain "containers" as pre-built atrefacts from Jenkins and users to build local versions of chosen "containers". See: https://xmosjira.atlassian.net/wiki/spaces/TG/pages/1039204573/Understanding+Build.pl+dependencies

A container is a git repo which can be built idependently and may have sub-modules.

It relies on the dependencies being coded into build_tools.py. It reads the Jenkins files in order to select the tarball to package when a container is built, which may be picked up by a subsequent container build.

Currently only supports Linux hosts.

It is very much a WIP and the user needs to edit build_tools.py to select or comment out repos they are not building locally, and wish to pick up from the latest Jenkins build.
