# source this file; expects ABS_BIN_DIR_PATH and BUILD_OUTFILE
if [[ ! -e $ABS_BIN_DIR_PATH ]]; then
  echo "ERROR: $ABS_BIN_DIR_PATH doesn't exist. Cannot set path." | tee -a "$BUILD_OUTFILE"
  exit 1
fi

export PATH="$ABS_BIN_DIR_PATH:$PATH"

for _t in gcc as ar ld nm objcopy objdump ranlib readelf strip cpp gcov gprof addr2line size strings elfedit gcc-ar gcc-nm gcc-ranlib; do
  _long="$ABS_BIN_DIR_PATH/sparc-buildroot-linux-uclibc-${_t}"
  _short="$ABS_BIN_DIR_PATH/sparc-linux-${_t}"
  if [[ -e "$_long" && ! -e "$_short" ]]; then
    ln -s "$(basename "$_long")" "$_short"
  fi
done
unset _t _long _short
