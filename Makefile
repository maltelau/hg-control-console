##
# HGCC
#
# @file
# @version 0.1

.PHONY: build
build: src/native/SimKeysHookLinux/build.sh src/native/SimKeysHookLinux/SimKeysHookLinux.cpp
	bash src/native/SimKeysHookLinux/build.sh

# end
