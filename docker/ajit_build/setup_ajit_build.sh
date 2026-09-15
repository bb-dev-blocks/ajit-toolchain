#!/usr/bin/env bash

export TERM=xterm;

# cd $AJIT_HOME; # see ../ajit_base/Dockerfile

echo "################################################";
echo "  Building buildroot.";
echo "################################################";
sleep 3;
bash $AJIT_HOME/buildroot_src/setup.sh;


echo "################################################";
echo "  AHIR C libs (host gcc) and python3.6 if missing.";
echo "################################################";
bash "$AJIT_HOME/scripts/install_ahir_c_libs.sh"
bash "$AJIT_HOME/scripts/ensure_python36.sh"

echo "################################################";
echo "  Building Tools, C Model and debug monitors.";
echo "################################################";
sleep 3;
bash $AJIT_HOME/scripts/build_ajit_public_resources.sh;


#echo "################################################";
#echo "  Building Ajit Tools/Scripts.";
#echo "################################################";
sleep 3;
#bash $AJIT_HOME/scripts/build_tools.sh;

