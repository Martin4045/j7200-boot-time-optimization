#!/bin/bash
# Run after both U-Boot machine builds succeed, before switching variants.
set -euo pipefail
layer_dir=$(cd "$(dirname "$0")/.." && pwd)
sdk_build=$(cd "$layer_dir/../.." && pwd)
case "${1:-}" in
  s7|semi) profile_variant=$1 ;;
  *) echo 'usage: archive-spl-profile.sh s7|semi' >&2; exit 2 ;;
esac
bundle="$layer_dir/artifacts/spl-profile-${profile_variant}-raw-20260910"
test ! -e "$bundle/SHA256SUMS"
mkdir -p "$bundle/static"
a72="$sdk_build/build/arago-tmp-default-glibc/work/j7200_evm-oe-linux/u-boot-ti-staging/2025.01+git"
r5="$sdk_build/build/arago-tmp-default-baremetal-k3r5/work/j7200_evm_k3r5-oe-eabi/u-boot-ti-staging/2025.01+git"
deploy="$sdk_build/build/deploy-ti/images/j7200-evm"
for file in tiboot3.bin tispl.bin u-boot.img; do
  cp -L "$deploy/$file" "$bundle/$file"
done
for file in Image k3-j7200-common-proc-board.dtb; do
  cp "$layer_dir/artifacts/s7-raw-20260909/$file" "$bundle/$file"
done
cp "$a72/build/.config" "$bundle/a72.config"
cp "$r5/build/.config" "$bundle/r5.config"
cp "$a72/build/include/generated/autoconf.h" "$bundle/static/a72-autoconf.h"
cp "$r5/build/include/generated/autoconf.h" "$bundle/static/r5-autoconf.h"
cp "$a72/build/spl/u-boot-spl" "$bundle/static/a72-spl.elf"
cp "$r5/build/spl/u-boot-spl" "$bundle/static/r5-spl.elf"
cp "$a72/build/u-boot" "$bundle/static/u-boot.elf"
cp "$a72/build/spl/u-boot-spl.map" "$bundle/static/a72-spl.map"
cp "$r5/build/spl/u-boot-spl.map" "$bundle/static/r5-spl.map"
cp "$a72/build/u-boot.map" "$bundle/static/u-boot.map"
cp -L "$a72/temp/log.do_compile" "$bundle/static/a72-compile.log"
cp -L "$r5/temp/log.do_compile" "$bundle/static/r5-compile.log"
cp "$a72/git/arch/arm/dts/k3-j7200-binman.dtsi" "$bundle/static/k3-j7200-binman.dtsi"
cp "$a72/git/arch/arm/mach-k3/j721e/j721e_init.c" "$bundle/static/j721e_init.c"
cp "$a72/git/arch/arm/mach-k3/r5/common.c" "$bundle/static/r5-common.c"
cp "$a72/git/include/j7200_spl_profile.h" "$bundle/static/j7200_spl_profile.h"
cp "$a72/git/common/spl/spl.c" "$bundle/static/spl.c"
cp "$a72/git/common/board_f.c" "$bundle/static/board_f.c"
cp "$a72/git/arch/arm/lib/bootm.c" "$bundle/static/bootm.c"
cp "$a72/git/board/ti/j721e/evm.c" "$bundle/static/evm.c"
"$a72/build/tools/dumpimage" -l "$bundle/tispl.bin" > "$bundle/static/tispl-fit.txt"
rg '^CONFIG_BOOTCOMMAND=' "$bundle/a72.config" > "$bundle/BOOTCOMMAND.txt"
git -C "$layer_dir" rev-parse HEAD > "$bundle/SOURCE_COMMIT"
git -C "$layer_dir" diff HEAD > "$bundle/static/source-dirty.patch"
git -C "$layer_dir" archive HEAD | gzip > "$bundle/static/layer-source.tar.gz"
cp "$layer_dir/tools/spl-profile.py" "$bundle/"
cp "$layer_dir/docs/spl-profile-20260910.md" "$bundle/README.md"
(cd "$bundle" && sha256sum tiboot3.bin tispl.bin u-boot.img Image k3-j7200-common-proc-board.dtb a72.config r5.config > SHA256SUMS)
echo "$bundle"
